============
dash0_distro
============

Prototype monorepo for the Dash0 OpenTelemetry distribution for Python and the
pure-Python OTLP exporter packages it builds on.

It is a `uv <https://docs.astral.sh/uv/>`_ workspace. Each directory under
``packages/`` is an independent Python distribution; the workspace wires them
together so the distribution resolves the in-repo exporters rather than published
ones.

Packages
========

``packages/dash0-opentelemetry-distro``
    The Dash0 distribution: ``Dash0Distro`` (``opentelemetry_distro`` entry
    point) and ``Dash0Configurator`` (``opentelemetry_configurator`` entry
    point). Defaults every signal to the pure-Python OTLP/HTTP exporter and
    activates instrumentors defensively. See the package README for details.

``packages/opentelemetry-pyproto``
    Pure-Python implementation of the OpenTelemetry protobuf messages, with no
    native dependencies.

``packages/opentelemetry-exporter-otlp-pyproto-common``
    Shared encoding logic for the pyproto exporters.

``packages/opentelemetry-exporter-otlp-pyproto-http``
    Pure-Python OTLP/HTTP exporter (stdlib ``urllib``, no native dependencies).
    This is the exporter the distribution selects by default, and the reason a
    Dash0 distribution can be injected into an arbitrary process' ``PYTHONPATH``
    without risking native-dependency conflicts with the host application.

``packages/opentelemetry-exporter-otlp-pyproto-grpc``
    Pure-Python OTLP/gRPC exporter (depends on ``grpcio``).

Why these live together
=======================

Injecting instrumentation into a process means loading these packages inside the
host interpreter. A protobuf/grpc C extension there risks ABI and version
conflicts with the host application, which is why upstream OpenTelemetry disables
Python injection by default. The pyproto exporters remove native code entirely,
so co-locating them with the distribution makes a self-contained, injection-safe
distribution.

Status
======

This is a prototype. The pyproto packages are vendored from the ``pyproto``
branch of the OpenTelemetry Python fork. Not yet done here: the injector's
per-``libc`` (``glibc``/``musl``) ``PYTHONPATH`` packaging, the curated
instrumentation pin set, and the integration/injection test matrix.
