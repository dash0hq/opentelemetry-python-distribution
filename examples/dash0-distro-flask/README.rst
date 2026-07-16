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


Running the demo (local only)
-----------------------------

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


Seeing it in Dash0
------------------

By default the demo only writes telemetry to local JSONL files. To also ship it
to Dash0 and view it in the UI, overlay ``docker-compose.dash0.yml``, which
reconfigures the collector to export to Dash0's OTLP ingress **in addition to**
the local files. The app is unchanged.

1. In Dash0, create an auth token under **Settings → Auth Tokens**, and note
   your **region** (the ``<REGION>`` in ``ingress.<REGION>.aws.dash0.com``,
   e.g. ``us-west-2`` or ``eu-west-1``) and the **dataset** you want the data
   to land in (``default`` is fine).

2. Export the credentials and run with both compose files:

   .. code-block:: bash

       cd examples/dash0-distro-flask
       export SCRIPT_UID=$(id -u) SCRIPT_GID=$(id -g)
       export DASH0_AUTH_TOKEN=auth_xxxxxxxxxxxxxxxx
       export DASH0_REGION=us-west-2
       export DASH0_DATASET=default
       docker compose -f docker-compose.yml -f docker-compose.dash0.yml up

   The collector receives OTLP/HTTP from the app and forwards it to
   ``https://ingress.$DASH0_REGION.aws.dash0.com`` with
   ``Authorization: Bearer $DASH0_AUTH_TOKEN`` and ``Dash0-Dataset:
   $DASH0_DATASET``.

3. In the Dash0 UI, open **Tracing** and filter by
   ``service.name = dash0-distro-flask-demo`` (make sure the dataset selector
   matches ``$DASH0_DATASET``). You should see ``GET /`` and
   ``GET /items/<int:item_id>`` spans — and **no** span for ``/items/42``
   (excluded). Each span's resource carries
   ``telemetry.distro.name = dash0-python``, confirming the Dash0 distribution
   configured the SDK. Metrics and logs land under the same service.

**Debugging:** because the collector still writes ``output/*.jsonl`` locally,
you can tell where a problem is — if the JSONL files have data but Dash0 is
empty, it is a credentials/region/network issue (check
``docker compose logs collector`` for export errors); if the JSONL files are
empty, the app never produced telemetry.

Sending straight from the app (no collector) is also possible: point
``DASH0_OTEL_COLLECTOR_BASE_URL`` at the Dash0 ingress and set
``OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <token>,Dash0-Dataset=<ds>"``
on the ``app`` service. The collector overlay is recommended because it keeps
the local JSONL for debugging and handles batching/retries.


Inspecting the local output
---------------------------

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
   :widths: 32 68
   :header-rows: 1

   * - File
     - Purpose
   * - ``app.py``
     - Minimal Flask app. No OTel imports.
   * - ``traffic.py``
     - Sends four HTTP requests to generate span data.
   * - ``collector-config.yaml``
     - Local-only collector: receives OTLP/HTTP on ``:4318`` and writes each
       signal to a JSONL file under ``/output``.
   * - ``collector-config-dash0.yaml``
     - Collector that writes JSONL **and** forwards to Dash0's OTLP ingress.
   * - ``docker-compose.yml``
     - ``prepare-python-agent`` (builds the venv from the in-repo packages),
       ``app`` (Flask under ``opentelemetry-instrument``), ``traffic``,
       ``collector``.
   * - ``docker-compose.dash0.yml``
     - Overlay that switches the collector to the Dash0-forwarding config.
   * - ``tests/``
     - pytest suite that runs the stack and validates the exported telemetry.
   * - ``output/``
     - Written at runtime by the collector (git-ignored).
