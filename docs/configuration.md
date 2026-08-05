# Configuration

## Dash0-specific environment variables

| Variable | Effect |
|---|---|
| `DASH0_OTEL_COLLECTOR_BASE_URL` | **Required.** OTLP endpoint to export to. If unset, the distribution disables itself entirely and sets `OTEL_SDK_DISABLED=true`. |
| `DASH0_DISABLE` | Set to `true` to disable the distribution entirely. The SDK becomes a no-op. |
| `DASH0_AUTOMATIC_SERVICE_NAME` | Set to `false` to opt out of the entrypoint-derived `service.name` fallback. |
| `DASH0_BOOTSTRAP_SPAN` | Name of a single span to emit once at startup. Useful for confirming the distribution is active. |
| `DASH0_FLUSH_ON_SIGTERM_SIGINT` | Set to `true` to flush all telemetry (traces, metrics, logs) on `SIGTERM` or `SIGINT` before exiting. Signal handlers can only be installed from the main thread; if the distribution is configured from a non-main thread, this setting is silently ignored. |

## Standard OpenTelemetry variables

All standard `OTEL_*` variables are honored.
The distribution sets defaults using `setdefault` and never overrides values you provide.

The following variables are relevant to the distribution's behavior:

| Variable | Default set by distro | Notes |
|---|---|---|
| `OTEL_TRACES_EXPORTER` | `otlp_proto_http` | Pure-Python OTLP/HTTP exporter. |
| `OTEL_METRICS_EXPORTER` | `otlp_proto_http` | Pure-Python OTLP/HTTP exporter. |
| `OTEL_LOGS_EXPORTER` | `otlp_proto_http` | Pure-Python OTLP/HTTP exporter. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Set to `grpc` for OTLP/gRPC. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Value of `DASH0_OTEL_COLLECTOR_BASE_URL` | Derived automatically; override if needed. |
| `OTEL_EXPORTER_OTLP_HEADERS` | — | Headers sent with every OTLP request. Required for Dash0 authentication: `Authorization=Bearer <token>,Dash0-Dataset=default`. |
| `OTEL_EXPORTER_OTLP_<SIGNAL>_PROTOCOL` | — | Per-signal protocol override (`TRACES`, `METRICS`, `LOGS`). |
| `OTEL_EXPORTER_OTLP_<SIGNAL>_ENDPOINT` | — | Per-signal endpoint override. Custom ports and explicitly set endpoints are never rewritten by the distro. |
| `OTEL_SERVICE_NAME` | — | Standard service name. The distro adds a fallback derived from the entrypoint when this is unset. |
| `OTEL_RESOURCE_ATTRIBUTES` | — | Additional resource attributes. The distro reads this to detect whether `service.name` is already set, and appends its own detected attributes (`telemetry.distro.*`, `k8s.pod.uid`) to it. |
| `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` | — | Comma-separated list of instrumentor entry-point names to skip (e.g. `flask,redis`). Honored by the auto-instrumentation loader. |
| `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` | — | Comma-separated resource detector names. Reference the Dash0 detectors here when using declarative SDK configuration (`OTEL_CONFIG_FILE`). |

## Mixed-protocol endpoint rewriting

When signals use different protocols and the shared base URL targets the "wrong" conventional port (4317 for gRPC, 4318 for HTTP), the distribution automatically derives a corrected per-signal endpoint.

For example, if `DASH0_OTEL_COLLECTOR_BASE_URL=http://collector:4318` and `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=grpc`, the distribution rewrites the traces endpoint to `http://collector:4317` rather than sending gRPC to the HTTP port.

Custom ports and explicitly set per-signal endpoints are always left untouched.

## Disabling the distribution

If you need to disable the distribution entirely without removing it:

```bash
export DASH0_DISABLE=true
opentelemetry-instrument python app.py
```

The SDK becomes a no-op and no instrumentation or export occurs.

## Setting a service name

The distribution uses the following priority order for `service.name`:

1. `OTEL_SERVICE_NAME` (you set it explicitly)
2. `service.name` from `OTEL_RESOURCE_ATTRIBUTES`
3. Name derived from the entrypoint script basename (e.g., `app.py` → `app`)

Steps 2 and 3 are suppressed when `DASH0_AUTOMATIC_SERVICE_NAME=false`.

To disable the entrypoint fallback and keep `service.name` unset when you have not provided one:

```bash
export DASH0_AUTOMATIC_SERVICE_NAME=false
```
