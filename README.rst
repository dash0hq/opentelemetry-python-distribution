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
- **The full contrib instrumentation set built in**: every upstream
  auto-instrumentation package (plus the X-Ray propagator) ships as a pinned
  dependency, so no ``opentelemetry-bootstrap`` step is needed and only
  instrumentations whose target library is installed activate.
- **Pure-Python OTLP export** with no ``google.protobuf``/``grpcio``
  dependency: OTLP/HTTP (``otlp_proto_http``) selected by default for all
  three signals, OTLP/gRPC (``otlp_proto_grpc``) when
  ``OTEL_EXPORTER_OTLP_PROTOCOL=grpc`` (or a per-signal
  ``OTEL_EXPORTER_OTLP_<SIGNAL>_PROTOCOL``) is set.
- **Sensible, injection-friendly defaults**: enable/disable gate, a required
  collector endpoint, a Kubernetes pod-UID resource detector, a service-name
  fallback, a ``telemetry.distro.name`` marker, an optional startup span, and
  graceful flushing on ``SIGTERM``/``SIGINT``.
- **An injector-ready bootstrap script**: the wheel ships the
  ``sitecustomize.py`` that the OpenTelemetry injector triggers via
  ``PYTHONPATH`` (``dash0/opentelemetry/injector/sitecustomize.py``), with
  interpreter-version, double-instrumentation, and dependency-conflict guards
  and graceful self-deactivation; see the package README for the deployment
  contract.
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

The pyproto exporters are **drop-ins** for the upstream
``opentelemetry-exporter-otlp-proto-http`` and ``-grpc`` packages: they occupy
the same import namespaces and register under the same ``otlp_proto_http`` /
``otlp_proto_grpc`` entry-point names. Because the distribution depends on the
pyproto packages (and not the regular ones), the standard names resolve to the
pure-Python implementations.

The directories keep their upstream names, but the packages are *published* as
``dash0-opentelemetry-pyproto`` and
``dash0-opentelemetry-exporter-otlp-pyproto-{common,http,grpc}``: the
``opentelemetry-*`` distribution names belong to the upstream OpenTelemetry
project, which has not released these packages yet. Once it does, the
distribution will depend on the official releases and deprecate the renamed
copies.


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


Installation
============

Releases are published on the Dash0 package index — a static PEP 503 simple
index on GitHub Pages whose artifacts are GitHub release assets of this
repository — not on public PyPI:

.. code-block:: bash

    pip install \
      --extra-index-url https://dash0hq.github.io/opentelemetry-python-distribution/simple/ \
      dash0-opentelemetry-distro

Production consumers (such as the dash0-operator's instrumentation image
build) should install with a fully hashed lockfile, ``--require-hashes``, and
``--only-binary :all:``; see the consumer contract in `RELEASING.rst`_.

For development, consume the workspace directly:

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
