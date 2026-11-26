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

0.4.1 - 2026-11-26
========================================

Bug Fixes
---------

- ``distro``: Percent-decode headers_list in a declarative configuration file, so Authorization=Bearer%20<token> sends Bearer <token> as it does from OTEL_EXPORTER_OTLP_HEADERS (`#125 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/125>`__, `#126 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/126>`__)
- ``distro``: Instrument applications where wrapt 2.x is installed (`#124 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/124>`__)

  ``all-dependencies.txt`` carried ``wrapt<3.0.0,>=1.0.0,>=1.11.2,>=1.12.1,~=1.0``,
  the ``~=1.0`` term made the bootstrap deactivate the whole distribution for
  any application on wrapt 2.x.
  
  ``opentelemetry-instrumentation-asyncclick`` 0.66b2 is the component with ~=1.0.
  
  This change vendors the asyncclick instrumentation to avoid affecting customers
  who use this instrumentation.
  

0.4.0 - 2026-11-24
========================================

Breaking Changes
----------------

- ``distro``: Move to opentelemetry-api and opentelemetry-sdk 1.45.2 and contrib 0.66b2, which fix two ReDoS vulnerabilities in trace context parsing (`#118 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/118>`__)

  ``opentelemetry-api`` 1.44.0 parses ``tracestate`` and ``traceparent`` with
  regular expressions that take quadratic time on crafted input
  (CVE-2026-114603, fixed in 1.45.1, and CVE-2026-126360, fixed in 1.45.2).
  ``opentelemetry-sdk`` and ``opentelemetry-semantic-conventions`` each
  require ``opentelemetry-api`` at one exact version, the one they are released
  alongside, so the injected distribution only activates in an application
  whose ``opentelemetry-api``
  is the one it ships.
  Until now that was 1.44.0, so an application that depends on the API for
  manual instrumentation had to keep a vulnerable version to stay
  instrumented.
  Applications that declare ``opentelemetry-api`` should move to 1.45.2.
  An application that keeps 1.44.0 now trips the dependency conflict check,
  and the distribution deactivates itself for that process.
  ``service.name`` now defaults to ``unknown_service:<executable>``, such as
  ``unknown_service:python3``, instead of ``unknown_service``, as the
  specification requires. The ``opentelemetry-instrument`` path and declarative
  configuration both produce it, each from its own copy of the rule, and it is
  what a process gets whenever nothing names the service:
  no ``OTEL_SERVICE_NAME``, no ``service.name`` in
  ``OTEL_RESOURCE_ATTRIBUTES``, and a generic runner such as ``gunicorn`` that
  the Dash0 service-name detector declines to name. Anything matching the
  literal ``unknown_service`` has to match the prefix instead.
  A ``${VAR}`` reference in a configuration file that has no default and whose
  variable is unset now substitutes an empty value, which the parser reads as
  null, as the specification requires and as the Java and Node.js
  implementations already do. It used to fail the load, and under injection the
  distribution deactivated itself naming the variable. A file that relied on
  that failure now starts with the setting left at its fallback, wherever the
  schema admits a null there. Where it does not, as for ``log_level``, an
  exporter's ``encoding`` and a resource attribute's ``name``, the load still
  fails, but with a schema message such as ``data.log_level must be one of
  [...]`` that does not name the variable that was unset.
  An ``otlp_http`` ``endpoint`` left null falls back to
  ``OTEL_EXPORTER_OTLP_<SIGNAL>_ENDPOINT``, then to
  ``OTEL_EXPORTER_OTLP_ENDPOINT``, which the distribution sets from
  ``DASH0_OTEL_COLLECTOR_BASE_URL``, so the spans the file meant to send
  elsewhere go to the Dash0 collector instead, and nothing is logged. Only one
  of these settings reports itself: an entry under ``resource.attributes``
  whose value is null is skipped with the warning ``Ignoring resource attribute
  '<name>' with empty value``. Give every reference a default that is a real
  value, as in ``${COLLECTOR_ENDPOINT:-http://collector:4318}``, so a missing
  variable
  cannot reach a fallback. An empty default does not do it: ``${VAR:-}``
  resolves to null exactly as ``${VAR}`` does. No default of any kind covers a
  variable the environment has but holds empty, since a default applies only
  to a name the environment does not have at all.
  ``EnvSubstitutionError`` is gone from ``opentelemetry.configuration.file``,
  because nothing raises it any more.
  Several parts of a configuration file now behave differently: some the
  previous release parsed and then ignored, some it refused outright. A file
  nobody has edited can change what the process exports, and a file that used
  to fail the load can start succeeding. Read any file you already ship before
  upgrading.
  A key written with an empty value is read as an empty object rather than as
  absent, which the specification requires: ``host:`` means ``host: {}``. A
  detector written that way used to be skipped and now runs. A sampler, an
  exporter, an ``id_generator`` and a view's
  ``aggregation`` written that way used to fail the whole file with a
  ``ConfigurationError`` such as ``No exporter type specified in span exporter
  config``, so under injection the distribution deactivated itself for that
  process; each now builds the component it names. A ``detection/development``
  list containing ``- host:`` and ``- process:`` starts adding the twelve
  ``host.*`` and ``process.*`` attributes those detectors produce, among them
  ``process.command`` and ``process.owner``. A ``propagator.composite`` list
  written as ``- tracecontext:`` and ``- baggage:`` used to leave the process
  with a no-op propagator that read and wrote no trace context at all, and now
  installs the propagators it names, so the process starts taking part in
  distributed traces.
  A top-level ``attribute_limits`` block applies to spans and to log records,
  for every attribute limit the signal's own ``limits`` block leaves unset. A
  ``tracer_provider.limits`` block that sets only ``link_count_limit`` still
  takes both attribute limits from the top-level block. A file carrying
  ``attribute_count_limit: 2`` used to leave the SDK defaults of 128 attributes
  and no length limit in place. It now keeps two attributes per span and per
  log record, and because the SDK evicts the oldest when the limit is reached,
  the two that survive are the two recorded last.
  A per-signal ``logger_provider.limits`` block used to be refused with the log
  line ``log_record_limits are specified in config but are not supported by the
  Python SDK LoggerProvider constructor; limits will be ignored.`` and now
  truncates log-record attributes.
  A ``cardinality_limits`` block on a metric reader, and
  ``aggregation_cardinality_limit`` on a view's stream, used to be ignored, the
  pull-reader case with a log line and the rest in silence. Both now cap the
  number of series per instrument, collapsing the excess into a single series
  carrying ``otel.metric.overflow: true``. A pull reader whose exporter is a
  plugin is the exception: it still logs that the limits are not supported and
  still ignores them.
  A ``tracer_configurator/development``, ``logger_configurator/development`` or
  ``meter_configurator/development`` block now applies, and ``enabled: false``
  in one of them stops that signal for every tracer, logger or meter it
  matches.
  A top-level ``log_level`` is applied to the ``opentelemetry`` logger. The
  OTLP exporter reports a failed export at ERROR, so a ``log_level`` of
  ``fatal`` or above silences that report, and ``log_level: error`` drops
  everything below ERROR.
  Several things that worked under a configuration file stop working.
  The attribute-limit environment variables no longer reach a process
  configured from a file: the loader now passes explicit span and log-record
  limits whether or not the file declares any, so
  ``OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT``,
  ``OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT``,
  ``OTEL_LOGRECORD_ATTRIBUTE_VALUE_LENGTH_LIMIT`` and
  ``OTEL_LOGRECORD_ATTRIBUTE_COUNT_LIMIT`` are all ignored, and
  ``OTEL_ATTRIBUTE_COUNT_LIMIT`` stops reaching log records. It never reached
  span attributes under a configuration file, since the previous release
  already passed the default count of 128 explicitly, and neither did
  ``OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT``. Move a value that applied to both
  signals into a top-level ``attribute_limits`` block, and a per-signal value
  into ``tracer_provider.limits`` or ``logger_provider.limits``: the top-level
  block applies to spans and to log records alike, so it cannot express a
  limit that applied to only one of them.
  A ``${VAR}`` reference in a JSON configuration file must now stand where JSON
  accepts a string, because substitution runs on the parsed document rather
  than on the file text. ``"attribute_count_limit": ${LIMIT}`` used to load and
  now fails the file with ``Failed to parse JSON``, and quoting it does not
  help, because the substituted value stays a string.
  A ``${VAR}`` written as a mapping key is left alone for the same reason,
  since a key is not a value. ``${EXPORTER_NAME}: {}`` under an exporter used
  to name whatever the variable held and now parses as the literal key
  ``${EXPORTER_NAME}``, which the entry-point lookup then fails on at startup.
  A plugin exporter, a plugin sampler, a plugin propagator, a plugin
  ``id_generator``, a plugin resource detector and an instrumentation name
  under ``instrumentation/development.python`` all take an arbitrary key, so
  write the key out. The resource detector is the position the Dash0 package's
  own
  ``otel-config.yaml`` uses, for ``dash0_distribution``, ``dash0_service_name``
  and ``dash0_kubernetes``.
  A ``${VAR}`` whose value supplied YAML structure stops supplying it, for the
  same reason: substitution now writes into the parsed document, so the value
  stays a string instead of being re-parsed. ``composite: ${PROPAGATORS}`` with
  ``PROPAGATORS`` holding ``[{tracecontext: {}}, {baggage: {}}]`` used to load
  and now fails the file with ``data.propagator.composite must be array``.
  A scalar value taken from the environment no longer carries YAML syntax with
  it. The previous release substituted into the file text and let the parser
  read the result, so a value could be cut short at a ``#``, rejected as an
  undefined YAML alias, stripped of quote characters, or trimmed of the spaces
  around it. Now it arrives exactly as the environment holds it. Check every
  variable a configuration file reads for surrounding quotes and surrounding
  whitespace: the quotes now reach the exporter, so an endpoint written that
  way names a host nobody can resolve, and the whitespace now fails the file
  wherever the schema wants a number or one of a fixed set of words, as at
  ``log_level`` or an exporter's ``encoding``.
  A reference that is only part of a value is no longer typed either, so a
  numeric field built from a reference and literal text, as in
  ``export_timeout: ${SECS}000``, used to load and now fails the file with
  ``must be integer or null``: write the whole value as one reference instead.
  A reference that is the whole value is still typed as before, so ``${LIMIT}``
  holding ``100`` still reaches an integer field as the integer 100, and
  quoting it as ``"${LIMIT}"`` fails the file in this release and in the
  previous one alike.
  
- ``distro``: Default OTEL_PROPAGATORS to tracecontext,baggage,xray, so traces stay connected across AWS load balancers and X-Ray services (`#117 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/117>`__)

  The default propagators change from ``tracecontext,baggage`` to
  ``tracecontext,baggage,xray``. When an incoming request carries both
  ``traceparent`` and ``X-Amzn-Trace-Id``, the X-Ray context wins. Set
  ``OTEL_PROPAGATORS=tracecontext,baggage`` to restore the previous behavior.
  

Enhancements
------------

- ``distro``: Default OTEL_TRACES_SAMPLER to always_on, so an incoming trace context can no longer decide whether this process is traced (`#110 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/110>`__)

  The distribution set no sampler and inherited the OpenTelemetry default,
  ``parentbased_always_on``. ``ParentBased`` holds five sub-samplers, and the
  ``root`` one applies only to a span with no parent. A span whose parent
  arrived in a ``traceparent`` header is decided by ``remote_parent_sampled``
  or ``remote_parent_not_sampled`` instead, which default to ``AlwaysOn`` and
  ``AlwaysOff``.
  A caller that sends a ``traceparent`` with the sampled flag off therefore
  silenced every span in the service receiving the request, and in every
  service that one called. That caller is often outside the organization
  operating the service, so the clients of an API decided whether its owner
  got to trace it.
  ``always_on`` takes the incoming trace context out of the decision. Dash0
  samples traces after ingestion with Signal Control, which evaluates a whole
  trace at once, and a span dropped by a sampler inside the process never
  reaches that evaluation.
  Nothing stops working and no setting becomes invalid, but an existing
  deployment is affected without changing its configuration. Expect more spans
  to leave the application, costing CPU in the process and bandwidth to the
  collector, and reduce the volume with Signal Control or a collector-side
  processor rather than in the SDK. Set ``OTEL_TRACES_SAMPLER`` on the workload
  to keep the previous behaviour; the distribution applies the default with
  ``setdefault`` and never overrides a value you provide.
  Declarative configuration is unaffected, because it never reads
  ``OTEL_TRACES_SAMPLER``. A configuration file that omits ``sampler`` keeps
  the OpenTelemetry default; see ``docs/configuration.md`` for the sampler
  declaration that matches this default.
  
- ``distro``: Use /etc/opentelemetry/python/otel-config.yaml as the declarative configuration file when OTEL_CONFIG_FILE is unset (`#119 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/119>`__)

  At startup the distribution now picks its configuration in this order:
  ``OTEL_CONFIG_FILE`` when it is set and not empty, then
  ``/etc/opentelemetry/python/otel-config.yaml`` when that file exists, then
  the environment variables, as before.
  A host with a Dash0 language package installed therefore runs in
  declarative-configuration mode from the file that package ships, without
  anyone setting ``OTEL_CONFIG_FILE``. Hosts and containers without the file
  are unaffected.
  An ``OTEL_CONFIG_FILE`` that names a missing file is still honored: the SDK
  reports the error and the distribution does not fall back to the default
  file.
  In file mode the SDK ignores ``OTEL_*`` variables unless the file
  interpolates them, so a variable set for one service only takes effect when
  the shipped file references it.
  
- ``distro``: Declare support for Python 3.14 and 3.15, and run the unit tests on both (`#120 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/120>`__)

  The package metadata now lists Python 3.14 and 3.15 alongside 3.10 to 3.13,
  and CI runs the distribution and declarative-configuration unit tests on
  every one of those versions. The end-to-end images already run on
  Python 3.15.
  

0.3.3 - 2026-10-28
========================================

Bug Fixes
---------

- ``deps``: Require pyyaml >= 5.1, because 3.10 through 3.13 cannot parse a configuration file on any supported interpreter (`#100 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/100>`__)

  ``pyyaml`` was declared with no version specifier on purpose: it is common in
  applications and has no dependencies of its own, so an unbounded requirement
  keeps the distribution from standing itself down over a disagreement that
  does not matter.
  
  Four releases make that wrong. ``pyyaml`` 3.10, 3.11, 3.12 and 3.13 call
  ``collections.Hashable`` in ``yaml/constructor.py``, an alias Python 3.10
  removed, so ``safe_load`` raises ``AttributeError`` while constructing a
  mapping. A scalar document still loads, which is why the breakage is easy to
  miss, and every ``OTEL_CONFIG_FILE`` worth loading is a mapping.
  
  Nothing excluded those four from an interpreter this distribution supports.
  Three of them publish no ``requires-python`` and the fourth publishes the
  empty string, and their classifiers stop at Python 3.5, so pip installs them
  anywhere without a word.
  
  5.1 is the first stable release after 3.13, with only prereleases in
  between. The requirement stays unbounded above, so an application running a
  newer ``pyyaml`` than the one a release was tested against keeps its
  telemetry.
  
  The floor reaches the injector because
  ``scripts/generate_all_dependencies.py`` keeps the ranges the
  distribution's own packages declare and drops only their exact pins, so the
  ``all-dependencies.txt`` line is now ``pyyaml>=5.1``. An application on a
  broken release is now stood down at startup with a reason, instead of
  failing inside ``pyyaml`` when the configuration file is read.
  
  ``UNPINNED_BY_DESIGN`` in ``scripts/check_pinned_dependencies.py`` becomes
  ``EXEMPT_FROM_EXACT_PIN`` and maps a name to the specifier it must carry
  rather than only forbidding one.
  

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
