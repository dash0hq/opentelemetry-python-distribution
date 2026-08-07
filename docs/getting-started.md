# Getting started

## Installation

Install the distribution from PyPI:

```bash
pip install dash0-opentelemetry
```

This single package pulls in the full upstream auto-instrumentation set, the pure-Python OTLP exporters, and all resource detectors.
No additional `opentelemetry-bootstrap` step is required.

## Minimal quick start

Point the distribution at a collector and run your application under `opentelemetry-instrument`:

```bash
export DASH0_OTEL_COLLECTOR_BASE_URL=http://localhost:4318
opentelemetry-instrument python app.py
```

That is enough to auto-instrument all installed libraries and export traces, metrics, and logs over OTLP/HTTP.
Your application needs zero OpenTelemetry imports.

## Sending directly to Dash0

To export directly to the Dash0 ingress instead of a local collector, use the Dash0 ingress URL and add an authorization header:

```bash
export DASH0_OTEL_COLLECTOR_BASE_URL=https://ingress.<region>.<cloud>.dash0.com
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer $DASH0_AUTH_TOKEN,Dash0-Dataset=default"
opentelemetry-instrument python app.py
```

## Running the Flask example

The repository ships a self-contained, Docker-based Flask demo in `examples/dash0-distro-flask`.
It demonstrates zero-code instrumentation, pure-Python OTLP/HTTP export, Kubernetes pod-UID detection, and `telemetry.distro.name` in resource attributes.

```bash
cd examples/dash0-distro-flask
export SCRIPT_UID=$(id -u) SCRIPT_GID=$(id -g)
docker compose up
```

Exported telemetry is written to JSONL files in `output/` (traces, metrics, logs).

For a step-by-step walkthrough that builds the same app from scratch, verifies the exported spans, and forwards them to Dash0 (with troubleshooting), see the [Flask example](flask-tutorial) tutorial.

## What happens at startup

When `opentelemetry-instrument` runs:

1. `Dash0Distro` is discovered via the `opentelemetry_distro` entry point.
   It checks `DASH0_DISABLE` and `DASH0_OTEL_COLLECTOR_BASE_URL`.
   If either gate fails, it sets `OTEL_SDK_DISABLED=true` and skips all instrumentation.
2. The distro selects the pure-Python OTLP/HTTP exporter, sets `OTEL_EXPORTER_OTLP_ENDPOINT`, and injects detected resource attributes into the environment.
3. Each installed instrumentor is loaded defensively: failures are logged and skipped.
4. `Dash0Configurator` is discovered via the `opentelemetry_configurator` entry point.
   It delegates to the standard SDK configurator, then optionally emits a bootstrap span and installs signal handlers.
5. Your application starts.
