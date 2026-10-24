=========
Changelog
=========

All notable changes to this project are documented here. The format is based on
`Keep a Changelog <https://keepachangelog.com/en/1.1.0/>`_ and this project aims
to follow `Semantic Versioning <https://semver.org/>`_ once it is published.

Unreleased changes are recorded as individual entry files in ``.chloggen/`` and
compiled into a new version section here at release time by `chloggen
<https://github.com/open-telemetry/opentelemetry-go-build-tools/tree/main/chloggen>`_;
released sections are generated — do not edit them by hand. See
``CONTRIBUTING.rst`` for how to add an entry and ``RELEASING.rst`` for how they
are compiled.

.. <!-- next version -->

0.3.2 - 2026-10-24
========================================

New Components
--------------

- ``configuration``: Ship declarative configuration (OTEL_CONFIG_FILE) support in the distribution (`#5 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/5>`__)

  ``OTEL_CONFIG_FILE`` used to fail out of the box, because the SDK defers to
  ``opentelemetry.configuration`` and that package was not installed. The
  distribution now depends on ``dash0-opentelemetry-configuration``.
  
  The code is not maintained in this repository. It lives on the ``dash0``
  branch of https://github.com/dash0hq/opentelemetry-python, which carries the
  Dash0 patches as commits on top of an upstream commit so they can be rebased
  when upstream moves. ``scripts/vendor_configuration.py`` is the only thing
  that turns that branch into a package here, and a ``vendored-configuration``
  job in CI fails if the checked-in tree is not what the script produces, so
  the two cannot drift apart silently.
  
  The patch on the fork replaces ``jsonschema`` validation with a validator
  compiled from the schema by ``fastjsonschema`` at development time. That
  keeps ``attrs``, ``referencing``, ``jsonschema-specifications`` and the
  compiled ``rpds-py`` out of the tree the injector adds to an application's
  ``sys.path``, which would otherwise stop being pure Python. The generated
  validator imports ``decimal`` and nothing else, and the fork's test suite
  checks it against ``jsonschema`` document by document.
  
  ``pyyaml`` is the one remaining runtime dependency and is declared with no
  version specifier on purpose. It is common in applications and has no
  dependencies of its own, so an unbounded requirement keeps the injector from
  self-deactivating for every application that pins a different version.
  ``UNPINNED_BY_DESIGN`` in ``scripts/check_pinned_dependencies.py`` records
  that decision and fails the build if a specifier is ever added.
  
  Resource detectors still run only when the configuration file names them
  under ``detection/development``, so issue #6 is unaffected by this change.
  

Enhancements
------------

- ``distro``: Name the offending package and version when reporting double instrumentation (`#68 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/68>`__)

  A double-instrumentation deactivation used to list a bare ``.dist-info``
  path, leaving the operator to work out which package to remove. It now reads
  ``opentelemetry-sdk 1.0.0 (/app/site-packages)``. The location comes from the
  public ``Distribution.locate_file()`` rather than the private ``_path``,
  which exists only on the path-based finder and raised ``AttributeError`` for
  any other one.
  
  Also tidies the script internally, with no behavior change: the helper that
  logs the warning is named for what it does rather than for printing,
  ``from x import y`` replaces the mixed ``import os`` usage per the project
  convention, and the redundant ``IOError`` alias is dropped from an
  ``except`` clause.
  
- ``distro``: Stop importing ``packaging`` in the injector bootstrap script (`#48 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/48>`__)

  ``sitecustomize.py``'s dependency-conflict check now uses a small vendored,
  dependency-free PEP 440/508 implementation instead of ``packaging``, so the
  distribution's own code no longer relies on ``packaging`` being importable in
  the injected process. ``packaging`` currently still ships transitively via
  ``opentelemetry-instrumentation``; the vendored copy can be dropped once that
  package no longer requires it.
  
- ``distro``: Ship all-dependencies.txt in the wheel so consumers copy it instead of deriving it (`#48 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/48>`__)

  ``scripts/generate_all_dependencies.py`` decides what a line of
  ``all-dependencies.txt`` means, but nothing produced the file. Each consumer
  building an injectable tree still wrote its own, which is how the exact-pin
  manifest got there in the first place.
  
  The wheel now ships the file at
  ``dash0/opentelemetry/injector/all-dependencies.txt``, beside the
  ``sitecustomize.py`` that reads it.
  ``scripts/refresh_injector_manifest.py`` installs this package into a scratch
  directory, generates the manifest from that tree and writes it into the
  source tree. Building an injectable tree is now two copies and no
  derivation, and every consumer gets the same manifest.
  
  Two CI jobs keep it honest. One re-runs the generator with ``--check`` and
  fails when the checked-in file is not what the current pins produce. The
  other opens the built wheel and fails when either injector file is missing
  from it.
  
- ``resource-detectors``: Derive ``service.name`` and ``service.version`` from installed package metadata (`#39 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/39>`__)

  ``service.name`` previously came from the entrypoint script basename whenever
  neither ``OTEL_SERVICE_NAME`` nor a ``service.name`` in
  ``OTEL_RESOURCE_ATTRIBUTES`` was set, so an application installed as a
  distribution reported the name of the file that happened to start it.
  
  Two steps now come first. A process started by a console script is attributed
  to the distribution that declared that script, and a process started with
  ``python -m package`` to the distribution that installed the package. Failing
  that, the nearest ``pyproject.toml`` is read, walking up from the directory
  holding the entrypoint script and stopping at a ``.git`` directory, so a
  monorepo yields the project that owns the entrypoint. The entrypoint basename
  remains the last resort, and ``DASH0_AUTOMATIC_SERVICE_NAME=false`` still
  turns all of it off.
  
  Both new steps also report ``service.version``, which the distribution did not
  set before. The entrypoint basename does not, because an absent version is
  more useful than a wrong one.
  
  A generic runner is never reported as the service. A console script such as
  ``gunicorn``, ``uvicorn``, ``celery`` or ``flask`` launches someone else's
  application, so neither its name nor its version describes the service. Every
  step that could name one declines: the console script, the ``python -m``
  module, and the entrypoint basename. The module is matched on its top-level
  package, so ``python -m flask run`` and ``python -m flask.cli`` are both
  covered. Detection falls through to ``pyproject.toml``, and when that finds
  nothing either the SDK's ``unknown_service`` stands. The Dash0 Ruby
  distribution skips ``puma``, ``unicorn`` and ``sidekiq`` the same way.
  
  Reading installed metadata rather than source mirrors the Java Spring Boot
  starter, which reads ``build-info.properties``, and the Node.js detector,
  which reads ``package.json``. A deployed container often ships no
  ``pyproject.toml``, while ``.dist-info/METADATA`` is derived from it at build
  time.
  
  The ``pyproject.toml`` step needs ``tomllib`` and is skipped on Python 3.10,
  which predates it. ``tomli`` is deliberately not taken as a dependency.
  

Bug Fixes
---------

- ``configuration``: Use a noop propagator when a configuration file configures none, instead of one that breaks every instrumented request (`#92 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/92>`__)

  A configuration file that omits ``propagator`` is meant to get a noop
  propagator. It got ``CompositePropagator([])`` instead, whose ``extract``
  returns the context it was handed rather than a root context, so a caller
  that passes none receives ``None``. Instrumentation attaches that ``None``
  as the current context, and every instrumented HTTP request then failed with
  ``AttributeError: 'NoneType' object has no attribute 'get'``.
  
  A real noop propagator is now used, both when ``propagator`` is absent and
  when it resolves to no propagators, such as ``composite_list: "none"``. It
  returns a root context, writes nothing, and declares no fields. Files that do
  configure propagators are unaffected.
  
  The root cause is upstream, where the same empty composite is built. This
  repository carries the fix until upstream ships the equivalent.
  
- ``distro``: Contain an unexpected error in the injector bootstrap script instead of letting it escape interpreter start-up (`#59 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/59>`__)

  ``sitecustomize.py`` now wraps its whole decision in a last-resort handler.
  An exception escaping ``import_distro()`` previously left the process in
  exactly the state the guards exist to prevent: the injected site still on
  ``PYTHONPATH`` and the injector prefix still set, so every child process
  retried the same failure, while the only report was the single line
  ``site.execsitecustomize()`` prints, which does not name the distribution and
  carries no traceback unless ``PYTHONVERBOSE`` is set. Such an error is now
  reported with its exception type and message and the distribution
  deactivates itself. Reporting runs before deactivating, and both steps are
  guarded independently, so a failure inside deactivation cannot silence the
  diagnostic.
  
- ``distro``: Report every dependency conflict at once, in readable form (`#65 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/65>`__)

  The dependency-conflict check stopped at the first conflict it found, so an
  operator whose application conflicted with three of the injected packages
  fixed the one named, redeployed, waited for the process to start, and was
  told about the second: one deployment per conflict. Every requirement in
  ``all-dependencies.txt`` is now checked before the distribution deactivates.
  
  The conflicts are also rendered rather than interpolated as a Python dict
  repr. A deactivation now reads
  ``dependency conflicts: alpha (requires >=2.0, found 1.0); beta (required
  package not found)``, sorted by name so the same set always reads the same
  way.
  
- ``distro``: Generate all-dependencies.txt from what upstream declares, not from the installed versions (`#48 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/48>`__)

  The injector bootstrap stands the whole distribution down when any line of
  ``all-dependencies.txt`` is violated by the application. Consumers generated
  that file as one exact pin per installed package, so an application carrying
  ``wrapt`` 1.16 lost all telemetry even though
  ``opentelemetry-instrumentation`` declares ``<3.0.0,>=1.0.0``. The same held
  for ``asgiref``, ``packaging``, ``psutil`` and ``typing-extensions``, each of
  them common in applications.
  
  ``scripts/generate_all_dependencies.py`` now owns the format. A line carries
  the conjunction of what the packages of the tree declare about that package.
  The exact pins the distribution's own packages make are skipped: they record
  the set a release was validated against, rather than what the code supports.
  Every range they declare is kept, because a range is a compatibility
  statement whoever wrote it, so the vendored pyproto exporters still
  constrain ``opentelemetry-sdk`` to ``~=1.12``. A package that only the
  distribution pins comes out unconstrained, which is what finally makes the
  ``UNPINNED_BY_DESIGN`` table of ``scripts/check_pinned_dependencies.py``
  reach the bootstrap.
  
  Nothing in the bootstrap changed. It already evaluated whatever specifier it
  was handed.
  
- ``distro``: Report and deactivate when OpenTelemetry auto-instrumentation fails to initialize (`#61 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/61>`__)

  The injector bootstrap script now calls
  ``auto_instrumentation.initialize(swallow_exceptions=False)``. Previously a
  failure of the distro, a configurator, or an instrumentor was logged by the
  SDK and swallowed, so the script carried on as though instrumentation had
  started: the injected site stayed on ``sys.path`` and ``PYTHONPATH`` while no
  telemetry was produced, no ``cannot auto-instrument Python process`` warning
  was emitted, and every child process repeated it. Such a failure is now
  reported with its exception type and message, and the distribution
  deactivates itself for the current process and its children.
  
- ``distro``: Accept any standard level name in ``OTEL_INJECTOR_LOG_LEVEL`` (`#62 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/62>`__)

  ``OTEL_INJECTOR_LOG_LEVEL`` was compared against the exact lowercase string
  ``debug``, so ``DEBUG``, ``Debug``, ``info`` and every other spelling behaved
  exactly like leaving the variable unset: silence, with nothing to explain why.
  The variable now resolves to a level, accepting ``critical``, ``error``,
  ``warn``, ``warning``, ``info`` and ``debug`` case-insensitively and ignoring
  surrounding whitespace. A value that is not a level falls back to ``warning``
  and is reported once, naming the value and the supported levels, instead of
  being silently treated as "off". No configured level can suppress the warning
  a guard emits when it deactivates the distribution: a level above ``warning``
  is clamped to it.
  
- ``distro``: Emit each injector diagnostic as one valid JSON object on one line, and never on stdout (`#63 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/63>`__)

  The diagnostics ``sitecustomize.py`` writes keep their shape, but are now
  serialized with ``json.dumps`` instead of assembled by string formatting.
  The messages embed foreign text (a command line, an exception message, a
  package version), and a double quote or backslash in it produced a line no
  JSON parser accepts, so a pipeline reading stderr as JSON dropped the record
  and lost the deactivation reason exactly when something had gone wrong.
  Multi-line exception text no longer splits one diagnostic across several
  lines either.
  
  Writes are also guarded. ``sys.stderr`` is ``None`` under ``pythonw`` and in
  daemonized processes, where the previous ``print(file=stderr)`` fell through
  to ``sys.stdout`` and could corrupt the output of any program whose stdout is
  its actual output. A diagnostic that cannot be written is now dropped instead
  of being misdirected or raising on a closed descriptor.
  
- ``distro``: Recognise the injected directory on ``sys.path`` and ``PYTHONPATH`` regardless of a trailing separator (`#60 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/60>`__)

  ``sitecustomize.py`` compared the injected directory textually, while
  ``dirname(__file__)`` never carries a trailing separator and the entry the
  injector puts on ``PYTHONPATH`` is whatever string it was configured with.
  When the two differed, the exact-match ``path.remove()`` raised ``ValueError``
  and interpreter start-up printed a traceback instead of instrumenting, and
  self-deactivation left the directory on ``PYTHONPATH`` so child processes kept
  loading the injected tree. Both comparisons now normalise with
  ``os.path.normpath``, and the entries are filtered rather than removed, so a
  directory listed more than once is fully removed instead of staying
  half-active.
  
- ``distro``: Compare distribution names in their PEP 503 canonical form in the double-instrumentation check (`#64 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/64>`__)

  The check lowercased names but did not apply the rest of the PEP 503 rule,
  under which runs of ``-``, ``_`` and ``.`` all collapse to a single ``-``.
  Distributions report the name they declared, verbatim, and non-canonical
  spellings are ordinary, so an application shipping ``OpenTelemetry_SDK`` was
  not recognised as shipping ``opentelemetry-sdk``. The distribution then
  activated on top of an already instrumented application, which is exactly
  what the check exists to prevent. The same normalisation now applies to the
  excluded API-layer packages, so an application declaring
  ``opentelemetry_api`` is still correctly exempt.
  
- ``distro``: Skip packages and requirements that cannot be read, instead of deactivating or crashing (`#66 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/66>`__)

  Several reads of foreign data in ``sitecustomize.py`` were unguarded, so a
  problem in an unrelated package could deactivate auto-instrumentation or
  print a traceback at interpreter start-up.
  
  ``importlib.metadata`` decodes ``METADATA`` as UTF-8, and one distribution
  whose file is not valid UTF-8 (a Latin-1 author field written by older
  tooling is the usual cause) aborted the entire double-instrumentation scan.
  Such a distribution is now skipped, with a warning naming its install
  directory. ``all-dependencies.txt`` is read as UTF-8 explicitly rather than
  in the process locale, which otherwise made the same tree readable in one
  process and not in the next, and an undecodable manifest now produces the
  intended "cannot read all-dependencies.txt" deactivation instead of
  propagating. A manifest line that is not a parseable requirement, a package
  whose installed version cannot be read, and a version that does not parse as
  PEP 440 are each warned about and skipped: an unverifiable requirement is not
  a conflicting one.
  
- ``distro``: Detect the upstream OTLP packages that the shipped pyproto packages shadow as double instrumentation (`#67 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/67>`__)

  The double-instrumentation check matched on distribution name, but what
  breaks a process is two distributions owning the same import path. The
  pure-Python exporters ship as ``dash0-opentelemetry-exporter-otlp-pyproto-*``
  and ``dash0-opentelemetry-pyproto`` while deliberately keeping the upstream
  import paths and entry points, so an application with
  ``opentelemetry-exporter-otlp-proto-grpc`` installed was not detected: the
  names differ. The distribution then activated, leaving two providers of
  ``opentelemetry.exporter.otlp.proto.grpc`` and two entry points named
  ``otlp_proto_grpc`` in one process, with sys.path order deciding the winner.
  The check now also looks for the upstream distribution each shipped package
  stands in for, including the ``opentelemetry-exporter-otlp`` meta package.
  
- ``docs``: Describe both environment variable bridges, in the file each one is in, with the right direction (`#70 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/70>`__)

  The injection page described a bridge that copies
  ``DASH0_OTEL_COLLECTOR_BASE_URL`` into ``OTEL_EXPORTER_OTLP_ENDPOINT`` and
  attributed it to ``sitecustomize.py``. That bridge is real, but it is in
  ``distro.py``. The one in ``sitecustomize.py`` runs in the other direction:
  it copies ``OTEL_EXPORTER_OTLP_ENDPOINT`` into
  ``DASH0_OTEL_COLLECTOR_BASE_URL`` when the latter is unset.
  
  The difference is not academic. Only the ``sitecustomize.py`` bridge runs
  under injection before the distribution decides whether to activate, so a
  reader of the old text would conclude that a deployment setting only
  ``OTEL_EXPORTER_OTLP_ENDPOINT`` gets no telemetry, when that case is exactly
  what the bridge exists to serve.
  
  The page now describes both bridges, names the file each one is in, and the
  heading says what the section is about rather than naming ``PYTHONPATH``.
  
  It also says which of the two variables to set. ``DASH0_OTEL_COLLECTOR_BASE_URL``
  works under ``opentelemetry-instrument`` and under injection, while
  ``OTEL_EXPORTER_OTLP_ENDPOINT`` on its own works only under injection,
  because the bridge that reads it is in ``sitecustomize.py``.
  
- ``docs``: Document how to keep the distribution's resource attributes under declarative configuration (`#6 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/6>`__)

  Declarative configuration (``OTEL_CONFIG_FILE``) reads neither
  ``OTEL_RESOURCE_ATTRIBUTES`` nor ``OTEL_SERVICE_NAME``, and runs only the
  detectors a config file lists. Setting it therefore leaves out
  ``telemetry.distro.name``, ``telemetry.distro.version``, ``k8s.pod.uid`` and
  the entrypoint-derived ``service.name`` fallback unless the file names the
  ``dash0_*`` detectors, in which case ``service.name`` is reported as
  ``unknown_service``.
  
  The documentation previously said to set
  ``OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`` instead. Declarative configuration
  never reads that variable, so the advice produced no attributes. The pages
  now show the config-file block to write, and say that each detector is
  independent and that attributes declared under ``resource.attributes`` take
  precedence over detected ones.
  
  Listing the detectors explicitly, rather than having the distribution insert
  them, keeps the Python, Ruby and JavaScript distributions handling the
  ``dash0_*`` detectors the same way. The complete resource still differs
  between them, because the SDKs ship different built-in detectors.
  

0.3.1 - 2026-08-03
========================================

0.2.1 - 2026-07-23
========================================

Bug Fixes
---------

- ``distro``: Add the PEP-263 encoding declaration to the injector bootstrap script (sitecustomize.py), so that it parses on Python 2.7 and deactivates itself gracefully instead of failing with a SyntaxError. (`#36 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/36>`__)

  The script contains non-ASCII characters (em-dashes) in its header comments. Without an encoding
  declaration, Python 2.7 rejected the whole file at parse time, so the self-deactivation logic never
  ran and injected processes logged "'import sitecustomize' failed".
  

0.2.0 - 2026-07-23
========================================

Enhancements
------------

- ``distro``: Ship the OpenTelemetry-injector bootstrap script (``sitecustomize.py``) in the wheel, at ``dash0/opentelemetry/injector/sitecustomize.py`` (`#32 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/32>`__)

  The script was previously maintained in the dash0-operator repository. Consumers building an
  injectable tree (``pip install --target <dir> dash0-opentelemetry-distro``) copy it from its
  packaged location to ``<dir>/sitecustomize.py``, where the OpenTelemetry injector triggers it by
  prepending ``<dir>`` to ``PYTHONPATH``. Compared to the operator's copy: the script now splits
  ``PYTHONPATH`` on ``os.pathsep`` (previously ``,``), so self-deactivation also removes the
  injected site when ``PYTHONPATH`` has multiple entries; and the double-instrumentation check
  flags overlap between the application's packages and the OpenTelemetry packages actually
  installed in the injected tree (except the API layer, which applications legitimately use for
  manual instrumentation), instead of a hardcoded package list.
  

0.1.0 - 2026-07-22
==================

Final release of the changes rehearsed in 0.1.0rc1 below; no code changes.

0.1.0rc1 - 2026-07-22
=====================

Changed
-------

- The vendored pure-Python OTLP packages are renamed at the distribution level
  to Dash0-owned names — ``dash0-opentelemetry-pyproto`` and
  ``dash0-opentelemetry-exporter-otlp-pyproto-{common,http,grpc}`` — so they
  can be published without claiming ``opentelemetry-*`` names the upstream
  OpenTelemetry project intends to release itself. Import paths and entry-point
  names are unchanged; when upstream publishes the official packages, the
  distribution will switch its dependencies over and deprecate the renamed
  copies.
  The distribution now pins the renamed exporters exactly, like every other
  dependency, and package versions moved to release form (``1.44.0``; the
  distribution itself is ``0.1.0``).

Added
-----

- Resource detectors registered under the standard
  ``opentelemetry_resource_detector`` entry-point group, exposing the distro's
  detected resource attributes as regular SDK resource detectors:
  ``dash0_distribution`` (``telemetry.distro.*``), ``dash0_kubernetes``
  (``k8s.pod.uid``) and ``dash0_service_name`` (upstream service detection —
  ``service.instance.id`` and ``OTEL_SERVICE_NAME`` — plus the distro's
  service-name fallback).
- ``Dash0Distro`` and ``Dash0Configurator`` providing zero-code instrumentation,
  pure-Python OTLP/HTTP export by default, an enable/disable gate, a Kubernetes
  pod-UID resource detector, a service-name fallback, a ``telemetry.distro.name``
  marker, an optional startup span, and graceful flush on ``SIGTERM``/``SIGINT``.
- Vendored pure-Python (pyproto) OTLP exporter packages as workspace members.
- ``examples/dash0-distro-flask`` end-to-end demo (local collector and Dash0
  ingress).
- CI (lint, unit tests on Python 3.10–3.13, packaging build) and an end-to-end
  example workflow.
- Release pipeline publishing to the Dash0 package index: wheels and sdists
  are attached to immutable GitHub releases (draft-first, with provenance
  attestations), and a static PEP 503 simple index on GitHub Pages points at
  them with ``#sha256=`` fragments so consumers can install with
  ``--require-hashes``. A committed hash manifest guards that no published
  filename can ever change bytes; yanking and filename exclusion are
  git-audited metadata (see ``RELEASING.rst``). PyPI/TestPyPI publishing of
  the real packages is removed; the five ``dash0-opentelemetry-*`` names are
  defensively registered on public PyPI as inert stubs.
- The distribution now pins its upstream OpenTelemetry dependencies exactly
  (``opentelemetry-api``/``-sdk`` 1.43.0, ``opentelemetry-instrumentation``
  0.64b0): it ships a curated, validated set of versions rather than a range,
  and CI now fails if a non-exact constraint is reintroduced
  (`#7 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/7>`_).
  The pins now also cover the full transitive closure: every package the
  distribution pulls in is declared directly with an exact pin, and CI fails
  when the declared set drifts from the resolved closure.
- The curated instrumentation set: the distribution now depends on every
  upstream auto-instrumentation package (contrib 0.65b0, moving
  ``opentelemetry-api``/``-sdk`` to 1.44.0) plus
  ``opentelemetry-propagator-aws-xray``, kept in sync with upstream by a unit
  test and Dependabot (`#1 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/1>`_).

Changed
-------

- The distribution now depends on ``opentelemetry-exporter-otlp-pyproto-grpc``
  and selects it when ``OTEL_EXPORTER_OTLP_PROTOCOL=grpc`` (or a per-signal
  ``OTEL_EXPORTER_OTLP_<SIGNAL>_PROTOCOL``) is set; unsupported protocol values
  fall back to OTLP/HTTP with a warning.
- ``opentelemetry-exporter-otlp-pyproto-grpc`` no longer depends on ``grpcio``:
  the exporter now ships a vendored pure-Python HTTP/2 gRPC transport
  (``_pygrpc``, from `open-telemetry/opentelemetry-packaging
  <https://github.com/open-telemetry/opentelemetry-packaging>`_), so it installs
  and runs without any compiled extension (`#2
  <https://github.com/dash0hq/opentelemetry-python-distribution/issues/2>`_).

Fixed
-----

- When signals resolve to different OTLP protocols (via the per-signal
  ``OTEL_EXPORTER_OTLP_<SIGNAL>_PROTOCOL`` overrides), the distribution now
  derives a matching per-signal endpoint instead of pointing every signal at a
  single shared ``OTEL_EXPORTER_OTLP_ENDPOINT``. OTLP/gRPC (port 4317) and
  OTLP/HTTP (port 4318, signal path appended) cannot share one endpoint, so a
  gRPC signal against an HTTP-port base URL — or the reverse — was previously
  sent to the wrong port and silently failed. The port is rewritten to the
  protocol's default only when the base URL carries the other protocol's default
  port; custom ports and explicit per-signal endpoints are left untouched (`#14
  <https://github.com/dash0hq/opentelemetry-python-distribution/issues/14>`_).
