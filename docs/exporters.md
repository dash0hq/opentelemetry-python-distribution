# OTLP exporters

## Why pure Python?

The distribution ships its own OTLP exporters built on pure-Python protobuf message classes (`dash0-opentelemetry-pyproto`).
These exporters have no dependency on `google.protobuf` or `grpcio`, which are C extension packages that require binary compatibility with the target application.

Injecting a package with native dependencies into an arbitrary process risks ABI conflicts (different versions of the shared library) or version conflicts (the application already uses a different version of `google.protobuf`).
The pure-Python exporters eliminate that class of problem.

## Available exporters

### OTLP/HTTP (default)

**Exporter name:** `otlp_proto_http`
**Package:** `dash0-opentelemetry-exporter-otlp-pyproto-http`

Selected by default for all three signals (traces, metrics, logs).
Sends protobuf-encoded OTLP over HTTP/1.1.
Compatible with any OTLP-capable collector, including the Dash0 ingress.

### OTLP/gRPC

**Exporter name:** `otlp_proto_grpc`
**Package:** `dash0-opentelemetry-exporter-otlp-pyproto-grpc`

Available as an alternative to OTLP/HTTP.
Uses the same pure-Python protobuf implementation.
Activate it by setting the protocol:

```bash
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

Or for a specific signal only:

```bash
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=grpc
```

## Drop-in replacement for upstream exporters

The pyproto exporters occupy the same import namespaces and register under the same entry-point names (`otlp_proto_http`, `otlp_proto_grpc`) as the upstream `opentelemetry-exporter-otlp-proto-http` and `opentelemetry-exporter-otlp-proto-grpc` packages.

Because the distribution depends on the pyproto packages rather than the upstream ones, the standard exporter names resolve to the pure-Python implementations automatically.
No configuration change is required; existing `OTEL_EXPORTER_OTLP_*` settings continue to work.

Once the upstream OpenTelemetry project publishes official pure-Python exporter releases, the distribution will depend on those and deprecate the vendored copies.

## Protocol selection

The protocol is selected per signal using the following priority order:

1. `OTEL_EXPORTER_OTLP_<SIGNAL>_PROTOCOL` (e.g., `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL`)
2. `OTEL_EXPORTER_OTLP_PROTOCOL`
3. Default: `http/protobuf`

## Intelligent endpoint rewriting

When a signal uses a different protocol than the shared base URL's conventional port implies, the distribution automatically derives the correct per-signal endpoint.

**Example:** `DASH0_OTEL_COLLECTOR_BASE_URL=http://collector:4318` (the HTTP port) and `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=grpc`.
The distribution rewrites the traces endpoint to `http://collector:4317` (the gRPC port) so traces are sent to the right listener.

Rules:
- If the base URL port is the gRPC default (4317) and a signal uses HTTP, the signal's endpoint is rewritten to port 4318 with the `/v1/<signal>` path appended.
- If the base URL port is the HTTP default (4318) and a signal uses gRPC, the signal's endpoint is rewritten to port 4317.
- Custom ports and explicitly set per-signal endpoints are never rewritten.

## Sending to Dash0

```bash
export DASH0_OTEL_COLLECTOR_BASE_URL=https://ingress.<region>.<cloud>.dash0.com
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer $DASH0_AUTH_TOKEN,Dash0-Dataset=default"
opentelemetry-instrument python app.py
```

The Dash0 ingress accepts OTLP/HTTP on port 443 (TLS).
The `Authorization` header carries the Dash0 auth token and the `Dash0-Dataset` header selects the target dataset.
