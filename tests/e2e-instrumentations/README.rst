===================================
Instrumentation end-to-end tests
===================================

What this proves that no unit test can
======================================

``packages/dash0-opentelemetry/tests`` checks that the shipped set of
``opentelemetry-instrumentation-*`` packages matches upstream and that every
pin resolves. Nothing in this repository checks what an instrumented library
actually emits, so an upstream release that renames a span, drops an attribute
or stops wiring up a handler passes every test that runs today.

Each test here installs the distribution into a container, runs a real
application against it, and asserts on the spans and log records that reach an
OTLP sink. A case cannot pass unless the distribution really produced the
telemetry.

The suite is Go because the sink and its query API come from
``github.com/open-telemetry/opentelemetry-packaging/testutil/otelsink``, which
is what the DEB and RPM packaging tests already use.

What a case is
==============

A case is a directory under ``cases/`` holding two files.

``app.py`` exercises exactly one instrumented library and then exits. It
imports nothing from the distribution and attaches no exporter, so everything
that reaches the sink got there through auto-instrumentation.

``requirements.txt`` names the library to install, pinned. It is empty for a
case that exercises the standard library.

Six cases run today, one per distinct telemetry shape rather than one per
shipped package:

.. list-table::
   :header-rows: 1

   * - Case
     - Started as
     - What it covers
   * - ``flask``
     - ``opentelemetry-instrument``
     - a web framework producing a ``SERVER`` span named after the route template
   * - ``requests``
     - ``opentelemetry-instrument``
     - an HTTP client producing a ``CLIENT`` span
   * - ``sqlite3``
     - ``opentelemetry-instrument``
     - the ``opentelemetry-instrumentation-dbapi`` machinery every SQL driver in the distribution goes through
   * - ``logging``
     - ``opentelemetry-instrument``
     - the log pipeline, and the trace context a record picks up from the span it was emitted inside
   * - ``asyncclick``
     - ``opentelemetry-instrument``
     - the one instrumentor the distribution carries as source instead of installing
   * - ``injected-wrapt2``
     - injected
     - an application holding wrapt 2.x, instrumented through the injected tree

How a case runs
===============

``harness.Run`` starts an ``otelsink`` sink, builds ``Dockerfile`` with the
repository root as the build context and the case name as a build argument,
and starts the container.

The build context has to be the repository root because the image builds the
workspace wheels from ``packages/`` with ``uv build --all-packages`` and then
installs every one of them by file path. That is also why the harness does
not use upstream's ``RunPackageTest``, which derives the build context from
the nearest ``go.mod`` and would make it this directory.

The install names the wheel files rather than the distribution. Passing
``--find-links`` and the name ``dash0-opentelemetry`` would leave the package
index enabled, so pip would weigh the locally built wheel against the released
one and take the release whenever it is the same version or newer, which is the
normal state of a development branch. The suite would then test the last
release on every branch and never the change under review. A file path admits
no such choice. Every distribution the workspace builds is installed from
``packages/``; the upstream ``opentelemetry-*`` dependencies and the per-case
pins in ``requirements.txt`` still resolve from the index, which is intended.

The two ways a case is started
==============================

``harness.Run`` builds ``Dockerfile`` and starts the case under
``opentelemetry-instrument``. That is how an application which installed the
distribution itself runs.

``harness.RunInjected`` builds ``Dockerfile.injected`` and starts the case with
plain ``python``, with the distribution on ``PYTHONPATH``. That is how the
dash0-operator runs an application it injected into. The image installs the
distribution with ``pip install --target /dash0`` and copies
``sitecustomize.py`` and ``all-dependencies.txt`` to the root of that tree,
which are the two copies a consumer makes. The case requirements go into the
ordinary site-packages instead, so the application's own dependencies sit
where an application's dependencies really sit.

Only the injected mode runs ``sitecustomize.py``, so only the injected mode
reaches the safety checks: the Python version gate, the double-instrumentation
check, and the dependency-conflict check against ``all-dependencies.txt``. A
case started under ``opentelemetry-instrument`` never reads that manifest.

``run_injected_case.py`` sets ``PYTHONPATH`` itself rather than the image
setting it, which keeps the runner process out of the tree. Set in the image,
``sitecustomize.py`` would run twice: once in the runner, initializing an SDK
that the following ``exec`` discards, and once in the application.

Why the injected case pins wrapt 2.5.2
======================================

``injected-wrapt2`` is the regression test for issue 189. The injected tree
ships ``wrapt == 1.17.3``, the application installs ``wrapt == 2.5.2``, and
``sitecustomize.py`` puts the tree last on ``sys.path``, so the wrapt the
instrumentations import is the application's.

Two things have to hold, and the case fails differently for each. The
dependency-conflict check has to accept 2.5.2, or the distribution deactivates
and nothing reaches the sink at all. The instrumentations then have to work
against wrapt 2.x at runtime, which is what the spans the test asserts show.
The ``CREATE``, ``INSERT`` and ``SELECT`` spans come from an instrumentation
installed as a dependency and the ``checkout`` span from the vendored one, and
both wrap through the application's wrapt.

The first of the two failed before the fix. ``all-dependencies.txt`` carried a
``wrapt ~= 1.0`` term that ``opentelemetry-instrumentation-asyncclick`` 0.66b2
contributed, the case exited zero having emitted nothing, and stderr carried
``cannot auto-instrument Python process: dependency conflicts: wrapt (requires
<3.0.0,>=1.0.0,>=1.11.2,>=1.12.1,~=1.0, found 2.5.2)``.

Why the container does not start the application directly
=========================================================

``CMD`` runs a runner script, not the case. The sink listens on the host, and
the container reaches it over a reverse SSH tunnel that testcontainers only
establishes in a ``PostReadies`` hook, meaning after the container reports
ready. An application that exported at startup would export into a tunnel that
does not exist yet, the connection would be refused, and the test would time
out waiting for telemetry that was emitted and dropped.

So ``sink_gate.py`` writes a marker line, which is the wait strategy the
harness uses, then blocks until the sink's port accepts a connection. Both
runners call it and then replace themselves with the case:
``run_case.py`` with ``opentelemetry-instrument python /app/app.py``, and
``run_injected_case.py`` with ``python /app/app.py``. The harness waits for
the container to exit separately, with ``wait.ForExit``.

The marker string is duplicated: ``READY_MARKER`` in ``sink_gate.py`` and
``readyMarker`` in ``harness/harness.go``. They have to stay equal.

Why every query is filtered by a resource attribute
===================================================

The sink scopes everything it answers to one attribute. ``sink.Env()`` sets
``OTEL_RESOURCE_ATTRIBUTES`` to a per-test id, and the query API drops any
resource that does not carry that exact attribute. ``harness.Run`` passes that
environment to the container unchanged, so every assertion in
``instrumentations_test.go`` depends on the value surviving the trip.

The distribution rewrites ``OTEL_RESOURCE_ATTRIBUTES`` when it adds its own
detected attributes, in ``_merge_into_resource_attributes`` in
``packages/dash0-opentelemetry/src/dash0/opentelemetry/resource.py``, and it
keeps whatever was already there. The suite relies on that.

The failure mode is worth knowing because it misdirects. If that preservation
regressed, the telemetry would still reach the sink, the filter would discard
all of it, and every case would fail with ``otelsink: timed out ... waiting for
traces``. That message points at telemetry never arriving, so the search starts
at the exporter, the tunnel and the container, none of which would be at fault.
Note also that the test id is not what isolates the four parallel cases from
each other: each gets its own sink on its own ports.

Running it
==========

From the repository root::

    make e2e-instrumentations

A Docker daemon and a Go toolchain are the only requirements. The first run
builds the workspace wheels and takes a few minutes; later runs reuse the
layer. To run one case::

    cd tests/e2e-instrumentations && go test -run TestFlask -v .

``.github/workflows/e2e-instrumentations.yml`` runs the same ``make`` target on
every push to ``main`` and on pull requests that touch ``packages/``,
``tests/e2e-instrumentations/``, ``pyproject.toml``, ``uv.lock``, the
``Makefile`` or the workflow itself.

The images are kept rather than deleted. ``harness.Run`` sets ``KeepImage:
true``, so each run leaves one image per case, around 215MB each, plus a
dangling intermediate of about 250MB. That is deliberate: keeping them is what
makes a second run take seconds instead of minutes. The cost is disk on a
development machine, since a continuous integration runner is discarded anyway.
Reclaim it with ``docker image prune`` for the intermediates, and by removing
the images testcontainers named with a UUID for the rest.

Adding a case
=============

Write ``cases/<name>/app.py`` and ``cases/<name>/requirements.txt``, then add a
function to ``instrumentations_test.go`` that calls ``harness.Run`` with
``<name>`` and asserts on what the sink received. Call ``harness.RunInjected``
instead for a case about the injected tree. Nothing else needs changing, as
long as the case runs self-contained.

Keep the application deterministic and short. It has to exit on its own, since
a clean interpreter exit is what flushes the batch processors, and a case that
does not exit fails on ``harness.RunTimeout``.

What a case cannot do yet
=========================

``harness.Run`` starts one container and nothing else. It creates no network,
starts no second container and waits for no second service, so a case that
needs a backing service cannot be added by writing those two files.

That rules out a large part of what the distribution ships. These need a daemon
the harness does not start: ``aiokafka``, ``aiopg``, ``aio-pika``, ``asyncpg``,
``cassandra``, ``celery``, ``confluent-kafka``, ``kafka-python``, ``mysql``,
``mysqlclient``, ``pika``, ``psycopg``, ``psycopg2``, ``pymemcache``,
``pymongo``, ``pymssql``, ``pymysql``, ``redis`` and ``remoulade``. These need a
stub for a remote API: ``boto3sqs``, ``botocore``, ``openai-v2`` and
``vertexai``. Covering any of them means teaching ``harness.Run`` to start a
second container, put both on one network, and pass the case its address.

Everything else can be added today with no change to the harness, which is most
of the remaining packages: ``django``, ``fastapi``, ``starlette``, ``tornado``,
``falcon`` and ``pyramid`` for server spans, ``httpx``, ``urllib``, ``urllib3``
and ``aiohttp-client`` for client spans, ``sqlalchemy`` and ``tortoiseorm`` over
sqlite, and ``asyncio``, ``threading``, ``click``, ``jinja2`` and ``structlog``
for the rest.
