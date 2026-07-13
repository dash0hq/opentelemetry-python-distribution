========================
Dash0 OpenTelemetry Distro
========================

Prototype of the Dash0 OpenTelemetry distribution for Python.

A *distribution* ("distro") is a small package that OpenTelemetry
auto-instrumentation discovers through entry points and uses to decide how a
process is instrumented. This distribution is meant to be injected into customer
processes (for example by the `OpenTelemetry injector
<https://github.com/open-telemetry/opentelemetry-injector>`_), so it makes two
choices that matter in that context.

What it provides
================

``Dash0Distro`` (``opentelemetry_distro`` entry point)
    * Defaults all three signals to the pure-Python OTLP/HTTP exporter
      (``otlp_proto_http``) with protocol ``http/protobuf``. Because the
      pure-Python exporter has no native dependencies, it is safe to prepend to
      an arbitrary process' ``PYTHONPATH`` without risking ABI or version
      conflicts with the host application. Defaults are applied with
      ``setdefault`` so configuration coming from the injector, the operator or
      the user is never overridden.
    * Overrides ``load_instrumentor`` to activate each instrumentor defensively:
      a disabled instrumentor is skipped, and one that fails to load is logged
      and skipped instead of aborting auto-instrumentation of the host process.
      This override is also where fixed or forked instrumentors can be swapped in
      ahead of an upstream release.

``Dash0Configurator`` (``opentelemetry_configurator`` entry point)
    Configures the OpenTelemetry SDK. It currently reuses the SDK configurator
    unchanged and exists so the distribution owns a stable configurator symbol
    (the upstream ``opentelemetry-distro`` package is intentionally not shipped)
    and has a home for distribution-specific SDK defaults.

Layout
======

::

    src/dash0/opentelemetry/
        distro.py          Dash0Distro
        configurator.py    Dash0Configurator
        version.py
    tests/

Status and open items
======================

This is a prototype. Notably:

* ``opentelemetry-exporter-otlp-pyproto-http`` is not yet published to PyPI; it
  currently lives in the ``pyproto`` branch of the OpenTelemetry Python fork. The
  dependency is therefore not resolvable until that exporter is released or
  vendored into the injected tree.
* Packaging into the injector's per-``libc`` (``glibc``/``musl``) ``PYTHONPATH``
  trees, the curated instrumentation pin set, and the integration/injection test
  matrix are not implemented here yet.
