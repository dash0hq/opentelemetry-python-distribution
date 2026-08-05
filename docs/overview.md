# Dash0 OpenTelemetry Python Distribution

The Dash0 distribution of OpenTelemetry for Python is a lightweight, opinionated layer on top of the upstream OpenTelemetry SDK that instruments Python applications with **no code changes** and exports telemetry using a **pure-Python protobuf implementation**.
No `google.protobuf` or `grpcio` native dependencies are required.

## Why pure Python?

Removing native dependencies is the core design goal.
It makes the distribution safe to *inject* into an arbitrary process via `PYTHONPATH`, for example from a Kubernetes operator or injector, without risking ABI or version conflicts with the target application.
If the distribution carried a native protobuf or gRPC dependency, injecting it into an application that already uses a different version of those libraries would break the application.
The pure-Python implementation avoids that class of problem entirely.

This is the Python counterpart of the [Dash0 OpenTelemetry distribution for Node.js](https://github.com/dash0hq/opentelemetry-js-distribution), bringing the same injection-safe model to Python.

## What you get

**Zero-code instrumentation.** `Dash0Distro` and `Dash0Configurator` are discovered through standard OpenTelemetry entry points and wire up the SDK before your application starts.
No `import opentelemetry` anywhere in your application code.

**The full contrib instrumentation set, built in.** Every upstream auto-instrumentation package ships as a pinned dependency.
No `opentelemetry-bootstrap` step is needed.
Instrumentations activate only when their target library is installed, so carrying all 40+ of them is safe.

**Pure-Python OTLP export.** OTLP/HTTP is selected by default for all three signals (traces, metrics, logs).
OTLP/gRPC is available via `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`.
Neither protocol requires native dependencies.

**Sensible, injection-friendly defaults.** The distribution sets an enable/disable gate, requires a collector endpoint, detects the Kubernetes pod UID, derives a service name from the entrypoint, marks telemetry with `telemetry.distro.name`, and can flush telemetry gracefully on `SIGTERM`/`SIGINT`.

**An injector-ready bootstrap script.** The wheel ships a `sitecustomize.py` that the OpenTelemetry injector activates via `PYTHONPATH`.
It includes interpreter-version, double-instrumentation, and dependency-conflict guards with graceful self-deactivation.

**Defensive instrumentation loading.** A single failing instrumentor is logged and skipped rather than aborting instrumentation of the whole process.

## Relationship to the upstream OpenTelemetry SDK

The distribution is a thin layer on top of the upstream SDK.
It sets defaults, registers resource detectors, and selects the pure-Python exporters.
All standard `OTEL_*` environment variables work as documented by the upstream project.
The distribution only sets values with `setdefault` and never overrides values you provide.
