==========================
dash0-opentelemetry-distro
==========================

The Dash0 OpenTelemetry distribution for Python. It is the Python counterpart of
the Dash0 Node.js distribution (``@dash0/opentelemetry``), adapted to Python's
distro/configurator machinery, and is meant to be injected into a process (for
example by the OpenTelemetry injector) with no code changes.

Entry points
============

``Dash0Distro`` (``opentelemetry_distro``)
    Runs first, before the configurator. It:

    * **Gates** the distribution: does nothing if ``DASH0_DISABLE=true`` or if
      ``DASH0_OTEL_COLLECTOR_BASE_URL`` is unset (nowhere to send telemetry). In
      either case it sets ``OTEL_SDK_DISABLED=true`` and skips instrumentation.
    * Defaults all three signals to the pure-Python OTLP/HTTP exporter
      (``otlp_proto_http``, ``http/protobuf``) and points
      ``OTEL_EXPORTER_OTLP_ENDPOINT`` at ``DASH0_OTEL_COLLECTOR_BASE_URL``. The
      pure-Python exporter has no native dependencies, which is what makes the
      distribution safe to inject onto an arbitrary process' ``PYTHONPATH``.
      When a signal's OTLP protocol does not match the transport the shared
      endpoint targets — its port is the *other* protocol's conventional
      default (``4317`` gRPC / ``4318`` HTTP) — a per-signal
      ``OTEL_EXPORTER_OTLP_<SIGNAL>_ENDPOINT`` is derived by rewriting the
      port (appending the ``v1/<signal>`` path for HTTP), so mixed-protocol
      setups and a base URL on the "wrong" default port still export
      correctly. Custom ports and explicit per-signal endpoints are always
      left untouched.
    * Injects detected **resource attributes** into ``OTEL_RESOURCE_ATTRIBUTES``/
      ``OTEL_SERVICE_NAME`` (see below) so the SDK's Resource picks them up.
    * Overrides ``load_instrumentor`` to activate each instrumentor
      **defensively** — a disabled or failing instrumentor is skipped and logged
      rather than aborting auto-instrumentation of the host process.

``Dash0Configurator`` (``opentelemetry_configurator``)
    Runs after the distro. Delegates to the standard OpenTelemetry SDK
    configurator to build the providers/exporters/Resource from the environment,
    then adds two behaviors from the Node.js distribution:

    * an optional **bootstrap span** emitted once at startup
      (``DASH0_BOOTSTRAP_SPAN=<name>``);
    * optional **graceful flush** on ``SIGTERM``/``SIGINT``
      (``DASH0_FLUSH_ON_SIGTERM_SIGINT=true``) — normal-exit flushing is already
      handled by the SDK's ``atexit`` provider shutdown.

Resource detectors (``opentelemetry_resource_detector``)
    The detected resource attributes (see below) as standard SDK resource
    detectors, one per concern so each can be used (or omitted) independently:

    * ``dash0_distribution`` — ``telemetry.distro.name``/``telemetry.distro.version``;
    * ``dash0_kubernetes`` — ``k8s.pod.uid``;
    * ``dash0_service_name`` — wraps the upstream service detection (a
      process-stable ``service.instance.id`` and ``service.name`` from
      ``OTEL_SERVICE_NAME``) and adds the distro's entrypoint-derived
      ``service.name`` fallback, so there is no need to also list the built-in
      ``service`` detector.

    They can be referenced via ``OTEL_EXPERIMENTAL_RESOURCE_DETECTORS``, or
    explicitly in a declarative config file under
    ``resource.detection/development.detectors``.

Instrumentations
================

The distribution depends on the full upstream auto-instrumentation set — every
package enumerated by the ``bootstrap_gen`` module of
``opentelemetry-instrumentation`` (the list behind ``opentelemetry-bootstrap``)
— pinned to a single contrib version, so injected processes need no bootstrap
step. Instrumentations only activate when their target library is present,
which makes carrying all of them safe.

Deviations from the upstream list:

* ``opentelemetry-propagator-aws-xray`` is shipped although upstream's
  bootstrap list only covers instrumentations (the Dash0 operator's
  instrumentation image always carried it).
* ``opentelemetry-exporter-prometheus``,
  ``opentelemetry-propagator-ot-trace``, and
  ``opentelemetry-instrumentation-aws-lambda`` are deliberately not shipped.

``tests/test_instrumentations.py`` cross-checks the dependency block against
the installed upstream list, so a contrib version bump that adds or removes
instrumentations fails CI until the block is re-synced. Dependabot keeps the
pins themselves moving (all ``opentelemetry-*`` packages are grouped into one
update, since the contrib instrumentations only resolve when they share one
contrib version).

Resource detection
==================

Ported from the Node.js distribution's custom detectors:

* **Kubernetes pod UID** (``k8s.pod.uid``): confirms it is running in Kubernetes
  (via ``/etc/hosts``), then extracts the pod UID from cgroup v1
  (``/proc/self/mountinfo``) or cgroup v2 (``/proc/self/cgroup``).
* **Service-name fallback**: if ``OTEL_SERVICE_NAME`` / ``service.name`` are not
  set (and ``DASH0_AUTOMATIC_SERVICE_NAME`` is not ``false``), derives a name
  from the entrypoint script. (Node.js reads ``package.json``; Python has no
  universal equivalent, so this is a best-effort analog.)
* **Distribution attributes**: ``telemetry.distro.name=dash0-python`` and
  ``telemetry.distro.version``.

Existing attributes are never overridden.

Dependency policy
=================

The distribution ships a curated set of upstream OpenTelemetry packages, pinned
exactly in its ``pyproject.toml``: each release is validated against precisely
those versions, and the code assumes them. Version bumps are deliberate,
standalone changes. The pins cover the *entire* installed tree: every package
the distribution pulls in transitively is also declared directly with an exact
pin, so no version is left to transitive resolution. CI enforces both rules via
``scripts/check_pinned_dependencies.py`` (in-repo workspace members are exempt,
as their version is fixed by the checkout).

Environment variables
=====================

============================================  ====================================================
Variable                                      Effect
============================================  ====================================================
``DASH0_OTEL_COLLECTOR_BASE_URL`` (required)  Collector base URL; also sets the OTLP endpoint.
``DASH0_DISABLE``                             ``true`` disables the distribution entirely.
``DASH0_AUTOMATIC_SERVICE_NAME``              ``false`` opts out of the service-name fallback.
``DASH0_BOOTSTRAP_SPAN``                      Emit one span with this name at startup.
``DASH0_FLUSH_ON_SIGTERM_SIGINT``             ``true`` flushes telemetry on SIGTERM/SIGINT.
============================================  ====================================================

Status
======

Prototype. The ``otlp_proto_http`` exporter is resolved from the in-repo pyproto
workspace member (not yet on PyPI). Not yet done: the injector's per-``libc``
packaging and the integration/injection test matrix. Unit tests do not require
a running collector.
