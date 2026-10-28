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
application under ``opentelemetry-instrument``, and asserts on the spans and
log records that reach an OTLP sink. A case cannot pass unless the
distribution really produced the telemetry.

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

Four cases run today, one per distinct telemetry shape rather than one per
shipped package:

.. list-table::
   :header-rows: 1

   * - Case
     - What it covers
   * - ``flask``
     - a web framework producing a ``SERVER`` span named after the route template
   * - ``requests``
     - an HTTP client producing a ``CLIENT`` span
   * - ``sqlite3``
     - the ``opentelemetry-instrumentation-dbapi`` machinery every SQL driver in the distribution goes through
   * - ``logging``
     - the log pipeline, and the trace context a record picks up from the span it was emitted inside

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

Why the container does not start the application directly
=========================================================

``CMD`` runs ``run_case.py``, not the case. The sink listens on the host, and
the container reaches it over a reverse SSH tunnel that testcontainers only
establishes in a ``PostReadies`` hook, meaning after the container reports
ready. An application that exported at startup would export into a tunnel that
does not exist yet, the connection would be refused, and the test would time
out waiting for telemetry that was emitted and dropped.

So ``run_case.py`` writes a marker line, which is the wait strategy the harness
uses, then blocks until the sink's port accepts a connection, then replaces
itself with ``opentelemetry-instrument python /app/app.py``. The harness waits
for the container to exit separately, with ``wait.ForExit``.

The marker string is duplicated: ``READY_MARKER`` in ``run_case.py`` and
``readyMarker`` in ``harness/harness.go``. They have to stay equal.

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

Adding a case
=============

Write ``cases/<name>/app.py`` and ``cases/<name>/requirements.txt``, then add a
function to ``instrumentations_test.go`` that calls ``harness.Run`` with
``<name>`` and asserts on what the sink received. Nothing else needs changing.

Keep the application deterministic and short. It has to exit on its own, since
a clean interpreter exit is what flushes the batch processors, and a case that
does not exit fails on ``harness.RunTimeout``.
