# Kubernetes injection

The distribution is designed to be injected into running Python processes by the [Dash0 Operator for Kubernetes](https://www.dash0.com/docs/dash0/monitoring/kubernetes/dash0-operator/overview).
No application code changes are required.

## How injection works

The distribution wheel ships a `sitecustomize.py` at `dash0/opentelemetry/injector/sitecustomize.py`.
Python automatically executes any `sitecustomize.py` it finds on `PYTHONPATH` during interpreter startup, before the application's own code runs.

The Dash0 Operator for Kubernetes injects the distribution directory into `PYTHONPATH`.
When the Python interpreter starts, it finds and executes `sitecustomize.py`, which activates the distribution.

## Safety checks before instrumentation

Before activating instrumentation, `sitecustomize.py` performs several guards.
If any guard fails, the distribution deactivates itself gracefully — including from child processes — rather than breaking the application.

### Python version check

The distribution requires Python 3.10 or later.
If the interpreter is older (including Python 2.x), the script deactivates itself and exits cleanly.

The script itself is written in valid Python 2.7+ syntax (including a PEP-263 encoding declaration) so it can safely parse and self-deactivate even on very old interpreters without a syntax error.

### Double-instrumentation check

If another OpenTelemetry distribution or the upstream SDK is already active in the process (detected by checking for overlapping OpenTelemetry packages), the script deactivates itself to avoid double-instrumenting the application.

### Dependency conflict check

The script validates the application's installed packages against the distribution's pinned dependency manifest (`all-dependencies.txt`).
If a version conflict is detected that would prevent the distribution from loading correctly, it deactivates itself and logs the conflict.

## Graceful self-deactivation

When any safety check fails, the distribution:

1. Sets `DASH0_DISABLE=true` in the current process environment.
2. Sets the same variable for child processes (so they also skip instrumentation).
3. Logs the reason for deactivation at `WARNING` level.
4. Exits `sitecustomize.py` without activating instrumentation.

The application continues running normally, unmodified.

## PYTHONPATH bridge

When running via injection, the `sitecustomize.py` also bridges the environment:

- If `OTEL_EXPORTER_OTLP_ENDPOINT` is not set but `DASH0_OTEL_COLLECTOR_BASE_URL` is set, the script copies the value to `OTEL_EXPORTER_OTLP_ENDPOINT` before the OpenTelemetry SDK initializes.

This allows the operator to pass a single `DASH0_OTEL_COLLECTOR_BASE_URL` environment variable without needing to know which specific `OTEL_*` variables to set.

## Kubernetes pod UID detection

When running inside a Kubernetes pod, the `dash0_kubernetes` resource detector automatically extracts the pod UID from the cgroup filesystem and adds it as `k8s.pod.uid` to every span, metric, and log record.
See [Resource detection](resource-detection) for details.

## Example: operator-style injection

An operator injects the distribution by setting environment variables on the pod and mutating `PYTHONPATH`:

```yaml
env:
  - name: PYTHONPATH
    value: /dash0/opentelemetry/injector:$(PYTHONPATH)
  - name: DASH0_OTEL_COLLECTOR_BASE_URL
    value: http://dash0-collector.dash0-system.svc.cluster.local:4318
```

The application pod requires no changes.
When the Python interpreter starts, it picks up `sitecustomize.py` from the injected `PYTHONPATH` and activates the distribution.
