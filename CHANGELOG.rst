=========
Changelog
=========

All notable changes to this project are documented here. The format is based on
`Keep a Changelog <https://keepachangelog.com/en/1.1.0/>`_ and this project aims
to follow `Semantic Versioning <https://semver.org/>`_ once it is published.

Unreleased
==========

Added
-----

- ``Dash0Distro`` and ``Dash0Configurator`` providing zero-code instrumentation,
  pure-Python OTLP/HTTP export by default, an enable/disable gate, a Kubernetes
  pod-UID resource detector, a service-name fallback, a ``telemetry.distro.name``
  marker, an optional startup span, and graceful flush on ``SIGTERM``/``SIGINT``.
- Vendored pure-Python (pyproto) OTLP exporter packages as workspace members.
- ``examples/dash0-distro-flask`` end-to-end demo (local collector and Dash0
  ingress).
- CI (lint, unit tests on Python 3.10–3.13, packaging build) and an end-to-end
  example workflow.
- Release workflow (PyPI Trusted Publishing), pending the decisions in
  ``RELEASING.rst``.
- The distribution now pins its upstream OpenTelemetry dependencies exactly
  (``opentelemetry-api``/``-sdk`` 1.43.0, ``opentelemetry-instrumentation``
  0.64b0): it ships a curated, validated set of versions rather than a range,
  and CI now fails if a non-exact constraint is reintroduced
  (`#7 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/7>`_).
- ``declarative-config`` extra installing the dependencies for declarative
  (file-based) configuration via ``OTEL_CONFIG_FILE``; when they are missing,
  the configurator now logs one actionable error naming the package to install
  instead of failing with a traceback and silently sending no telemetry
  (`#5 <https://github.com/dash0hq/opentelemetry-python-distribution/issues/5>`_).
