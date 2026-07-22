=========
Changelog
=========

All notable changes to this project are documented here. The format is based on
`Keep a Changelog <https://keepachangelog.com/en/1.1.0/>`_ and this project aims
to follow `Semantic Versioning <https://semver.org/>`_ once it is published.

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

- ``bootstrap/sitecustomize.py``: the injector bootstrap script that triggers
  loading of the distribution now lives here, alongside its unit tests. It is
  prepended to ``PYTHONPATH`` by the OpenTelemetry injector, checks the Python
  version, guards against double instrumentation, self-deactivates for child
  processes, and bridges ``OTEL_EXPORTER_OTLP_ENDPOINT`` to
  ``DASH0_OTEL_COLLECTOR_BASE_URL``. Kept as a standalone, valid-Python-2.7+
  file (never imported by the 3.10+ distribution package) so it can detect and
  bail out gracefully on legacy interpreters; consumers copy it out of the
  distribution rather than maintaining their own.
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
