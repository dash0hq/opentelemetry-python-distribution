dash0-distro-flask demo
=======================

Demonstrates the **Dash0 OpenTelemetry Python distribution**. A Flask
application is fully instrumented — producing HTTP trace spans (plus metrics
and logs) exported over OTLP/HTTP — without any OpenTelemetry import in its
source code and without a single line of SDK or exporter setup.

This is the Dash0-distro counterpart of the ``instrumentation-configuration``
demo in `opentelemetry-injector-demo`_: same zero-code goal, but the SDK is
wired up by the distribution (discovered through entry points by
``opentelemetry-instrument``) instead of by a declarative YAML file.

.. _opentelemetry-injector-demo:
   https://github.com/ocelotl/opentelemetry-injector-demo/tree/main/instrumentation-configuration


How it works
------------

1. ``opentelemetry-instrument`` runs the app. It discovers, via entry points,
   the distribution's ``Dash0Distro`` (``opentelemetry_distro``) and
   ``Dash0Configurator`` (``opentelemetry_configurator``) and runs them before
   ``app.py`` executes.

2. ``Dash0Distro`` gates on ``DASH0_OTEL_COLLECTOR_BASE_URL`` (set in
   ``docker-compose.yml``), points ``OTEL_EXPORTER_OTLP_ENDPOINT`` at the
   collector, and defaults all three signals to the **pure-Python pyproto
   OTLP/HTTP exporter** (``otlp_proto_http``, no ``google.protobuf``). It also
   injects the ``telemetry.distro.name=dash0-python`` resource attribute.

3. The auto-instrumentation then activates every installed instrumentor,
   including ``FlaskInstrumentor``. The standard
   ``OTEL_PYTHON_FLASK_EXCLUDED_URLS`` variable (set to ``items/42``) is honored,
   so that route produces no span — the distro analogue of the reference demo's
   declarative ``excluded_urls`` option.

4. ``app.py`` has zero OpenTelemetry imports. Instrumentation is injected from
   outside, exactly as a Kubernetes injector would do it.

The pyproto packages and the distribution are installed from this repository's
``packages/`` directory (mounted into the build container), so the demo is
self-contained — nothing needs to be published to PyPI.


Running the demo
----------------

Requires Docker with the Compose plugin. The collector runs as
``SCRIPT_UID``/``SCRIPT_GID`` so it can write into the bind-mounted ``output/``
directory as your own user.

.. code-block:: bash

    cd examples/dash0-distro-flask
    export SCRIPT_UID=$(id -u) SCRIPT_GID=$(id -g)
    docker compose up

To force a clean rebuild of the agent venv:

.. code-block:: bash

    rm -rf python-agent && docker compose up


Inspecting the output
---------------------

After the traffic container exits, JSONL files are written to ``output/``:

.. code-block:: bash

    # 3 spans, not 4 — the /items/42 request is dropped by
    # OTEL_PYTHON_FLASK_EXCLUDED_URLS.
    wc -l output/traces.jsonl

    # The resource carries telemetry.distro.name=dash0-python, proving the
    # Dash0 distribution configured the SDK.
    grep -o 'telemetry.distro.name[^,]*' output/traces.jsonl | head -1


Running the tests
-----------------

.. code-block:: bash

    uv run pytest tests/ -v

The suite runs the whole stack in Docker, then asserts: Flask GET spans are
present with ``http.route``; the ``/items/42`` span is excluded; the resource
carries ``telemetry.distro.name=dash0-python`` and the configured
``service.name``; and ``app.py`` contains no OpenTelemetry import. Use
``--no-docker`` to re-run the assertions against an existing ``output/``.


Files
-----

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - File
     - Purpose
   * - ``app.py``
     - Minimal Flask app. No OTel imports.
   * - ``traffic.py``
     - Sends four HTTP requests to generate span data.
   * - ``collector-config.yaml``
     - Collector: receives OTLP/HTTP on ``:4318`` and writes each signal to a
       JSONL file under ``/output``.
   * - ``docker-compose.yml``
     - ``prepare-python-agent`` (builds the venv from the in-repo packages),
       ``app`` (Flask under ``opentelemetry-instrument``), ``traffic``,
       ``collector``.
   * - ``tests/``
     - pytest suite that runs the stack and validates the exported telemetry.
   * - ``output/``
     - Written at runtime by the collector (git-ignored).
