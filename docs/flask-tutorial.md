# Flask example

This tutorial builds the `dash0-distro-flask` example from nothing: a plain Flask app with **zero OpenTelemetry imports**, instrumented entirely from the outside by the Dash0 OpenTelemetry Python distribution. By the end you will have traces, metrics, and logs flowing over OTLP/HTTP, and you will have verified them.

It reproduces, step by step, the self-contained demo shipped in [`examples/dash0-distro-flask`](https://github.com/dash0hq/opentelemetry-python-distribution/tree/main/examples/dash0-distro-flask). If you would rather run the finished demo directly with Docker Compose, see [Getting Started](getting-started).

Why this distribution rather than plain OpenTelemetry: its OTLP exporters are **pure Python**, with no `google.protobuf` or `grpcio` native dependencies. That is what makes it safe to inject into an arbitrary process (for example, from a Kubernetes operator via `PYTHONPATH`) without risking ABI or version conflicts with the target application. The Flask app you build here needs no code changes for exactly the same reason.

## Prerequisites

- **Python 3.10 or newer.** The distribution requires it (`pip` refuses to install on 3.9).
- **A telemetry destination.** Either a local OpenTelemetry Collector (this tutorial runs one in Docker) or a Dash0 ingress endpoint. The distribution emits nothing until it is pointed at one.

## Step 1: Create the project and a virtual environment

```bash
mkdir flask-demo && cd flask-demo
python3 -m venv .venv
source .venv/bin/activate
```

## Step 2: Install the distribution

```bash
pip install dash0-opentelemetry flask
```

That single distribution package pulls in the full contrib auto-instrumentation set (40+ packages, including `opentelemetry-instrumentation-flask`), so you do **not** run `opentelemetry-bootstrap` or install any instrumentor by hand. It also brings the pure-Python OTLP exporters, every resource detector, and the `opentelemetry-instrument` launcher. Carrying all of the instrumentations is safe: each one activates only when its target library is actually installed, so the ones you do not use stay dormant.

> **Installing with uv:** If you install with `uv` instead of `pip`, add `--prerelease=allow`: the distribution pins some upstream instrumentation packages to pre-release versions, which `uv` skips by default. `pip` honors the exact pins without any flag.

## Step 3: Write the Flask app

Create `app.py`. It contains **no OpenTelemetry code at all** — instrumentation is injected from outside, exactly as a Kubernetes injector would do it.

```python
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def index():
    return "Hello from the dash0-distro-flask demo!\n"


@app.route("/items/<int:item_id>")
def get_item(item_id):
    return jsonify({"id": item_id, "name": f"item-{item_id}"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

## Step 4: Run a local collector

The distribution exports OTLP/HTTP. Run a collector that receives it and writes each signal to a local JSONL file so you can inspect the output. Save this as `collector-config.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

exporters:
  file/traces:
    path: /output/traces.jsonl
  file/metrics:
    path: /output/metrics.jsonl
  file/logs:
    path: /output/logs.jsonl

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [file/traces]
    metrics:
      receivers: [otlp]
      exporters: [file/metrics]
    logs:
      receivers: [otlp]
      exporters: [file/logs]
```

Start it, writing output into an `output/` directory in your project:

```bash
mkdir -p output
docker run --rm -p 4318:4318 \
  -v "$PWD/collector-config.yaml:/etc/otelcol/config.yaml" \
  -v "$PWD/output:/output" \
  otel/opentelemetry-collector-contrib:latest \
  --config=/etc/otelcol/config.yaml
```

Leave it running in this terminal.

## Step 5: Run the app under `opentelemetry-instrument`

In a second terminal, with the virtual environment activated, point the distribution at the collector and launch the app:

```bash
export DASH0_OTEL_COLLECTOR_BASE_URL=http://localhost:4318
export OTEL_SERVICE_NAME=dash0-distro-flask-demo
export OTEL_PYTHON_FLASK_EXCLUDED_URLS="items/42"
opentelemetry-instrument python app.py
```

`DASH0_OTEL_COLLECTOR_BASE_URL` is required. Without it the distribution disables itself and emits nothing — it sets `OTEL_SDK_DISABLED=true`, logs `Dash0 distribution disabled: DASH0_OTEL_COLLECTOR_BASE_URL is not set`, and starts your app uninstrumented. This gate is deliberate: an injected distribution must never send data to nowhere, so it stays inert until you point it at a destination. (The gate is strict enough that it overrides even a manual `OTEL_TRACES_EXPORTER=console`.)

`OTEL_SERVICE_NAME` and `OTEL_PYTHON_FLASK_EXCLUDED_URLS` are both standard OpenTelemetry variables — the distribution honors them unchanged. It only ever sets defaults with `setdefault` and never overrides a value you provide. Here `OTEL_PYTHON_FLASK_EXCLUDED_URLS` drops the `/items/42` request so you can see the effect.

## Step 6: Generate some traffic

In a third terminal, send a few requests:

```bash
for path in / /items/1 /items/2 /items/42; do
  curl -s -o /dev/null -w "$path -> %{http_code}\n" http://localhost:5000$path
done
```

Then stop the app (`Ctrl+C` in the second terminal) so its spans flush, and stop the collector once the files are written.

## Step 7: Verify the telemetry

The collector's `file` exporter writes one JSON object per export batch, and each batch holds many spans, so count the spans inside the batches rather than counting lines:

```bash
# 3 spans, not 4 — the /items/42 request is dropped by
# OTEL_PYTHON_FLASK_EXCLUDED_URLS.
python3 -c "import json,sys; print(sum(len(ss['spans']) for l in open('output/traces.jsonl') for rs in json.loads(l)['resourceSpans'] for ss in rs['scopeSpans']))"

# The resource carries telemetry.distro.name=dash0-python, proving the
# Dash0 distribution configured the SDK.
grep -o 'telemetry.distro.name[^,]*' output/traces.jsonl | head -1
```

You should see three trace spans — `GET /` and `GET /items/<int:item_id>` (twice) — each carrying an `http.route` attribute, and none for the excluded `/items/42`. The resource on every span carries `telemetry.distro.name=dash0-python` and the `service.name` you set. Metrics and logs land in the sibling JSONL files.

## Step 8: Send it to Dash0

The app itself never talks to Dash0 — the **collector** does. `DASH0_OTEL_COLLECTOR_BASE_URL` only takes a base URL and cannot carry the `Authorization` and `Dash0-Dataset` headers the Dash0 ingress requires, so the collector's exporter is what authenticates and forwards. Keeping the file exporter alongside it is what makes debugging easy: if the local JSONL has data but Dash0 is empty, the problem is credentials or dataset, not your app.

To ship the same telemetry to Dash0, point the collector at the Dash0 ingress in addition to the local files. Add an `otlphttp` exporter to `collector-config.yaml`:

```yaml
exporters:
  otlphttp/dash0:
    endpoint: ${env:DASH0_ENDPOINT}
    headers:
      Authorization: "Bearer ${env:DASH0_AUTH_TOKEN}"
      Dash0-Dataset: "${env:DASH0_DATASET}"
```

Add `otlphttp/dash0` to each pipeline's `exporters` list. Copy the endpoint verbatim from Dash0 under **Settings → Endpoints → OTLP via HTTP** (it already encodes your region and cloud), create an auth token under **Settings → Auth Tokens**, then export those values before starting the collector:

```bash
export DASH0_ENDPOINT=https://ingress.<region>.<cloud>.dash0.com
export DASH0_AUTH_TOKEN=auth_xxxxxxxxxxxxxxxx
export DASH0_DATASET=default
```

> **Copy the endpoint, and mind the port:** Copy the OTLP/HTTP endpoint exactly as shown; do not hand-assemble it, because the cloud (`gcp`/`aws`) and region differ per organization. Use the `https://` OTLP/HTTP host (port 443) for this tutorial — a `:4317` endpoint is the OTLP/gRPC port and will not work with the `otlphttp` exporter.

In the Dash0 UI, open **Tracing**, make sure the dataset selector matches `$DASH0_DATASET`, and filter by `service.name = dash0-distro-flask-demo`. You will see the `GET /` and `GET /items/<int:item_id>` spans, no span for `/items/42`, and `telemetry.distro.name = dash0-python` on each span's resource.

### Troubleshooting the export

Because the collector still writes `output/*.jsonl` locally, you can always tell where a problem is. If the JSONL files have data but nothing arrives in Dash0, check `docker compose logs collector` (or the collector's output) for export errors, and read the message rather than just the status code:

- **`invalid authentication token`** — the token itself is wrong. Recheck `DASH0_AUTH_TOKEN`.
- **`not authorized to ingest into dataset "<name>"`** — the token is valid but is not scoped to that dataset. This is a distinct HTTP 401: the connection and credentials are fine, only the dataset authorization is missing. Either set `DASH0_DATASET` to a dataset the token can write to, or grant the token access to the dataset under **Settings → Auth Tokens**.
- **`401` referencing the region/cloud** — the endpoint's region/cloud does not match the token's organization. Recheck `DASH0_ENDPOINT` against **Settings → Endpoints**.

If the JSONL files are empty in the first place, the app never produced telemetry — revisit Step 5 (most often `DASH0_OTEL_COLLECTOR_BASE_URL` was not set).

### Sending straight from the app

Alternatively, skip the collector and export straight from the app: set `DASH0_OTEL_COLLECTOR_BASE_URL` to the Dash0 endpoint and add `OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <token>,Dash0-Dataset=<ds>"`. The collector is recommended because it keeps the local JSONL for debugging and handles batching and retries.

## What happens at startup

When `opentelemetry-instrument` runs:

1. `Dash0Distro` is discovered via the `opentelemetry_distro` entry point. It checks `DASH0_DISABLE` and `DASH0_OTEL_COLLECTOR_BASE_URL`. If either gate fails, it sets `OTEL_SDK_DISABLED=true` and skips all instrumentation.
2. The distro selects the pure-Python OTLP/HTTP exporter, sets `OTEL_EXPORTER_OTLP_ENDPOINT`, and injects detected resource attributes (including `telemetry.distro.name=dash0-python`) into the environment.
3. Each installed instrumentor is loaded defensively, including `FlaskInstrumentor`, which wraps your app. Failures are logged and skipped.
4. `Dash0Configurator` is discovered via the `opentelemetry_configurator` entry point. It delegates to the standard SDK configurator, then optionally emits a bootstrap span and installs signal handlers.
5. Your application starts, now fully instrumented.

## Key takeaways

- **Zero code changes.** `app.py` has no OpenTelemetry imports. All wiring happens through OpenTelemetry entry points that `opentelemetry-instrument` runs before your app, which is why the same setup maps directly onto Kubernetes injection.
- **Pure-Python OTLP is the point.** No `google.protobuf` or `grpcio` native dependencies means the distribution can be injected into any process without ABI or version conflicts. OTLP/HTTP is the default for all signals; gRPC is opt-in via `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`.
- **The collector endpoint is a hard gate.** No `DASH0_OTEL_COLLECTOR_BASE_URL`, no telemetry — by design.
- **Standard OpenTelemetry variables still work.** The distribution layers on top of the upstream SDK with `setdefault` and never overrides your settings, so `OTEL_SERVICE_NAME`, `OTEL_PYTHON_FLASK_EXCLUDED_URLS`, and the rest behave exactly as upstream documents.
- **`telemetry.distro.name=dash0-python` is your fingerprint.** It rides on every span, metric, and log resource, so you can confirm in Dash0 that the distribution configured the SDK.
- **The app doesn't authenticate to Dash0 — the collector does.** Keep the local file exporter alongside the Dash0 one so you can localize any delivery failure, and read 401 messages carefully: a bad token and an unauthorized dataset are different problems.

## Further reading

- [Getting Started](getting-started) — Install the distribution and send your first telemetry.
- [Auto-instrumentation](auto-instrumentation) — The full set of libraries instrumented automatically.
- [Configuration](configuration) — All Dash0-specific and standard OpenTelemetry environment variables.
- [OTLP Exporters](exporters) — The pure-Python OTLP/HTTP and OTLP/gRPC exporters.
