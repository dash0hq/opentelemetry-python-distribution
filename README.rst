==================================
Dash0 OpenTelemetry Python Distro
==================================

The Dash0 distribution of OpenTelemetry for Python: a small, opinionated layer
on top of upstream OpenTelemetry that instruments a Python application with **no
code changes** and exports over OTLP using a **pure-Python protobuf**
implementation — no ``google.protobuf``/``grpcio`` native dependencies.

Removing the native dependency is the whole point: it makes the distribution
safe to *inject* into an arbitrary process' ``PYTHONPATH`` (for example from a
Kubernetes injector or operator) without risking ABI or version conflicts with
the target application. It is the Python counterpart of the
`Dash0 OpenTelemetry distribution for Node.js
<https://github.com/dash0hq/opentelemetry-js-distribution>`_.

This repository is a `uv <https://docs.astral.sh/uv/>`_ workspace containing the
distribution and the pure-Python OTLP exporter packages it builds on.


What you get
============

- **Zero-code instrumentation** via ``opentelemetry-instrument`` (or an
  injector): the distribution's ``Dash0Distro`` and ``Dash0Configurator`` are
  discovered through OpenTelemetry entry points and wire up the SDK before your
  application starts.
- **Pure-Python OTLP/HTTP export** (``otlp_proto_http``) with no
  ``google.protobuf`` dependency, selected by default for all three signals.
- **Sensible, injection-friendly defaults**: enable/disable gate, a required
  collector endpoint, a Kubernetes pod-UID resource detector, a service-name
  fallback, a ``telemetry.distro.name`` marker, an optional startup span, and
  graceful flushing on ``SIGTERM``/``SIGINT``.
- **Defensive instrumentation loading**: a single failing instrumentor is
  logged and skipped rather than aborting instrumentation of the whole process.


Architecture
============

::

    packages/
      dash0-opentelemetry-distro/               the distribution (distro + configurator)
      opentelemetry-pyproto/                    pure-Python protobuf message classes
      opentelemetry-exporter-otlp-pyproto-common/   shared OTLP encoding
      opentelemetry-exporter-otlp-pyproto-http/     pure-Python OTLP/HTTP exporter (default)
      opentelemetry-exporter-otlp-pyproto-grpc/     pure-Python OTLP/gRPC exporter
    examples/
      dash0-distro-flask/                       self-contained, Docker-based demo

The pyproto exporter is a **drop-in** for the upstream
``opentelemetry-exporter-otlp-proto-http``: it occupies the same import
namespace and registers under the same ``otlp_proto_http`` entry-point name.
Because the distribution depends on the pyproto package (and not the regular
one), the standard name resolves to the pure-Python implementation.


Quick start
===========

The distribution is activated by ``opentelemetry-instrument``; the application
needs no OpenTelemetry code. At minimum, point it at a collector:

.. code-block:: bash

    export DASH0_OTEL_COLLECTOR_BASE_URL=http://localhost:4318
    opentelemetry-instrument python app.py

That is enough to auto-instrument installed libraries and export traces,
metrics, and logs over OTLP/HTTP. To send directly to Dash0 instead of a local
collector, use the Dash0 ingress URL and add the auth header:

.. code-block:: bash

    export DASH0_OTEL_COLLECTOR_BASE_URL=https://ingress.<region>.<cloud>.dash0.com
    export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer $DASH0_AUTH_TOKEN,Dash0-Dataset=default"
    opentelemetry-instrument python app.py

See ``examples/dash0-distro-flask`` for a complete, runnable demo (local
collector and Dash0 ingress), including how to view the data in the Dash0 UI.


Configuration
=============

.. list-table::
   :widths: 38 62
   :header-rows: 1

   * - Environment variable
     - Effect
   * - ``DASH0_OTEL_COLLECTOR_BASE_URL`` (required)
     - OTLP endpoint to export to. If unset, the distribution disables itself.
   * - ``DASH0_DISABLE``
     - ``true`` disables the distribution entirely (SDK becomes a no-op).
   * - ``DASH0_AUTOMATIC_SERVICE_NAME``
     - ``false`` opts out of the entrypoint-derived ``service.name`` fallback.
   * - ``DASH0_BOOTSTRAP_SPAN``
     - Emit a single span with this name once at startup.
   * - ``DASH0_FLUSH_ON_SIGTERM_SIGINT``
     - ``true`` flushes telemetry on ``SIGTERM``/``SIGINT`` before exiting.

Standard ``OTEL_*`` variables are honored as usual; the distribution only sets
defaults (with ``setdefault``) and never overrides values you provide.


Installation status
===================

The pyproto packages are not yet published to a public index, so today the
distribution is consumed from this workspace (or bundled into an injected tree).
Publishing is set up but gated on the decisions in `RELEASING.rst`_. Until then:

.. code-block:: bash

    uv sync --package dash0-opentelemetry-distro


Development
===========

See `CONTRIBUTING.rst`_ for local setup, running the tests, and linting.
Release process and open publishing decisions live in `RELEASING.rst`_.

.. _CONTRIBUTING.rst: CONTRIBUTING.rst
.. _RELEASING.rst: RELEASING.rst


License
=======

Apache License 2.0. See ``LICENSE``.
