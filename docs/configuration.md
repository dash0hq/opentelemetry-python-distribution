# Configuration

## Dash0-specific environment variables

| Variable | Effect |
|---|---|
| `DASH0_OTEL_COLLECTOR_BASE_URL` | **Required.** OTLP endpoint to export to. If unset, the distribution disables itself entirely and sets `OTEL_SDK_DISABLED=true`. |
| `DASH0_DISABLE` | Set to `true` to disable the distribution entirely. The SDK becomes a no-op. |
| `DASH0_AUTOMATIC_SERVICE_NAME` | Set to `false` to opt out of detected `service.name` and `service.version`. |
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
| `OTEL_TRACES_SAMPLER` | `always_on` | Every span is recorded and exported, whatever an incoming trace context says. See [Sampling](#sampling). Declarative configuration (`OTEL_CONFIG_FILE`) never reads it. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Value of `DASH0_OTEL_COLLECTOR_BASE_URL` | Derived automatically; override if needed. |
| `OTEL_EXPORTER_OTLP_HEADERS` | — | Headers sent with every OTLP request. Required for Dash0 authentication: `Authorization=Bearer <token>,Dash0-Dataset=default`. |
| `OTEL_EXPORTER_OTLP_<SIGNAL>_PROTOCOL` | — | Per-signal protocol override (`TRACES`, `METRICS`, `LOGS`). |
| `OTEL_EXPORTER_OTLP_<SIGNAL>_ENDPOINT` | — | Per-signal endpoint override. Custom ports and explicitly set endpoints are never rewritten by the distro. |
| `OTEL_SERVICE_NAME` | — | Standard service name. The distro adds a fallback derived from the entrypoint when this is unset. |
| `OTEL_RESOURCE_ATTRIBUTES` | — | Additional resource attributes. The distro reads this to detect whether `service.name` is already set, and appends its own detected attributes (`telemetry.distro.*`, `k8s.pod.uid`) to it. |
| `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` | — | Comma-separated list of instrumentor entry-point names to skip (e.g. `flask,redis`). Honored by the auto-instrumentation loader. |
| `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` | — | Comma-separated resource detector names, honored by the SDK's environment-based configuration. Declarative configuration (`OTEL_CONFIG_FILE`) never reads it. |
| `OTEL_CONFIG_FILE` | — | Path to a declarative SDK configuration file, which takes over from every variable above that configures providers, exporters or the resource. List the `dash0_*` detectors in the file to keep `telemetry.distro.*`, `k8s.pod.uid` and the `service.name` fallback. |

## Sampling

The distribution defaults `OTEL_TRACES_SAMPLER` to `always_on`.
Every span your application starts is recorded and exported.

OpenTelemetry's own default is `parentbased_always_on`, and this is the one place where the distribution deliberately departs from it.

`ParentBased` holds five sub-samplers, and the `root` one applies only to a span that has no parent.
A span whose parent arrived in a `traceparent` header is decided by `remote_parent_sampled` or `remote_parent_not_sampled` instead, which default to `AlwaysOn` and `AlwaysOff`.
So a caller that sends a `traceparent` with the sampled flag off silences every span in the service receiving the request, and in every service that one calls.

That caller is often outside your organization, which means your clients decide whether you get to trace your own API.
Resetting the trace context at your network boundary solves it, and getting that right across every entry point is harder than it sounds, so the usual outcome is missing traces with no visible cause.

`always_on` takes the incoming trace context out of the decision.
Dash0 samples traces after ingestion rather than inside your process, using [Signal Control](https://dash0.com/docs/dash0/telemetry/signal-control/sample-traces), which evaluates a whole trace at once.
A span dropped by a sampler in your process never reaches that evaluation.

Set `OTEL_TRACES_SAMPLER` yourself to override the default:

```bash
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
```

Two consequences are worth knowing about.

Your application exports more spans than it would under `parentbased_always_on`, which costs CPU in the process and bandwidth to your collector.
Reduce volume with Signal Control, or with a sampling processor in a collector you run, rather than in the SDK.

Outgoing requests carry a `traceparent` whose sampled flag is set.
A downstream service still running `parentbased_always_on` therefore samples the traces you start.

Declarative configuration does not read `OTEL_TRACES_SAMPLER`.
When `OTEL_CONFIG_FILE` is set and the file omits `sampler`, the OpenTelemetry default applies.
Declare the sampler in the file to get the same behavior:

```yaml
tracer_provider:
  processors:
    - batch:
        exporter:
          otlp_http: {}
  sampler:
    always_on: {}
```

`processors` is required whenever `tracer_provider` is present, so add the `sampler` key to the block you already have rather than declaring a block that holds only a sampler.

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
3. `Name` from the installed distribution the process was started from
4. `[project].name` from the nearest `pyproject.toml`, walking up from the entrypoint script
5. Name derived from the entrypoint script basename (e.g., `app.py` → `app`)

Steps 3 and 4 also set `service.version`.
Steps 2 through 5 are suppressed when `DASH0_AUTOMATIC_SERVICE_NAME=false`.
See `docs/resource-detection.md` for how a distribution is identified and where the `pyproject.toml` walk stops.

To disable detection and keep `service.name` unset when you have not provided one:

```bash
export DASH0_AUTOMATIC_SERVICE_NAME=false
```
