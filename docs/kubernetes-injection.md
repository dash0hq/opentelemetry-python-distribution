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
If any guard fails, the distribution deactivates itself gracefully, including from child processes, rather than breaking the application.

### Python version check

The distribution requires Python 3.10 or later.
If the interpreter is older (including Python 2.x), the script deactivates itself and exits cleanly.

The script itself is written in valid Python 2.7+ syntax (including a PEP-263 encoding declaration) so it can safely parse and self-deactivate even on very old interpreters without a syntax error.

### Double-instrumentation check

If another OpenTelemetry distribution or the upstream SDK is already active in the process (detected by checking for overlapping OpenTelemetry packages), the script deactivates itself to avoid double-instrumenting the application.

Distribution names are compared in their PEP 503 canonical form: lowercased, with runs of `-`, `_` and `.` collapsed to a single `-`.
Packages report the name they declared, verbatim, and non-canonical spellings are ordinary, so an application declaring `OpenTelemetry_SDK` is recognised as `opentelemetry-sdk`.
The OpenTelemetry API layer is excluded from this check, because applications legitimately depend on it for manual instrumentation without being auto-instrumented.

The check looks for import-path overlap, not just name overlap.
The pure-Python (pyproto) exporters ship under Dash0-owned distribution names while keeping the upstream import paths and entry points, so an application holding the upstream distribution has a different name and the same import path:

| Shipped distribution | Import path it owns | Upstream distribution it shadows |
|---|---|---|
| `dash0-opentelemetry-pyproto` | `opentelemetry.proto` | `opentelemetry-proto` |
| `dash0-opentelemetry-exporter-otlp-pyproto-common` | `opentelemetry.exporter.otlp.proto.common` | `opentelemetry-exporter-otlp-proto-common` |
| `dash0-opentelemetry-exporter-otlp-pyproto-grpc` | `opentelemetry.exporter.otlp.proto.grpc` | `opentelemetry-exporter-otlp-proto-grpc`, `opentelemetry-exporter-otlp` |
| `dash0-opentelemetry-exporter-otlp-pyproto-http` | `opentelemetry.exporter.otlp.proto.http` | `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-exporter-otlp` |

Finding any of the upstream names in the application counts as double instrumentation, because two distributions would then provide the same modules and register the same exporter entry points.

### Unreadable input

A problem in one foreign package, or in one line of the manifest, makes that one item impossible to verify.
It never deactivates the distribution on its own.

A distribution whose `METADATA` cannot be decoded is skipped, with a warning naming its install directory, and the scan continues with the rest.
A manifest line that is not a parseable requirement is skipped with a warning, as is a package whose installed version cannot be read or does not parse as PEP 440.
Only a manifest that cannot be read or decoded at all deactivates the distribution, because without it no conflict check is possible.

### Dependency conflict check

The script validates the application's installed packages against `all-dependencies.txt`, the dependency manifest shipped beside it.
Each line states what the upstream packages in the injected tree declare they support, so an application carrying its own `wrapt` or `typing-extensions` only conflicts when that version is outside the range upstream itself allows.
If a version conflict is detected that would prevent the distribution from loading correctly, it deactivates itself and logs the conflict.

Every requirement in the manifest is checked, so one deactivation names every conflicting package rather than only the first.
Each is reported as `name (requires <specifier>, found <version>)`, or `name (required package not found)`, sorted by name.

### Initialization failure

The last guard runs after the others have passed.
The script asks the OpenTelemetry auto-instrumentation not to swallow exceptions, so a failure in the distro, a configurator, or an instrumentor reaches the script instead of being logged and ignored.
Without this, a failed start-up would leave the distribution on `sys.path` around an SDK that never initialized: no telemetry, no warning, and every child process repeating it.
When initialization fails, the script logs the failing exception type and message and deactivates itself.

### Last-resort guard

Every guard above exists to leave the process in a known state.
An unexpected error escaping the guards themselves is the one path that leaves the process in the state they prevent: the distribution still on `PYTHONPATH`, and the injector still set to re-add it to child processes.

The script therefore wraps its whole decision in a last-resort handler.
An unexpected error is logged with its exception type and message, naming the distribution, and the script then deactivates itself.
Both steps are guarded independently, and the reporting runs first, so a failure inside deactivation cannot silence the diagnostic.

Without this handler the only report is the single line `site.execsitecustomize()` prints, which does not name the distribution and carries no traceback unless `PYTHONVERBOSE` is set.

## Graceful self-deactivation

When any safety check fails, the distribution:

1. Removes its own directory from `sys.path` and from `PYTHONPATH`, comparing entries with `os.path.normpath` so a trailing separator on the injected entry still matches, and removing every occurrence rather than only the first.
2. Sets the same variable for child processes (so they also skip instrumentation).
3. Logs the reason for deactivation at `WARNING` level, as a single line holding one JSON object, written only to stderr.
4. Exits `sitecustomize.py` without activating instrumentation.

The application continues running normally, unmodified.

## Environment variable bridges

The distribution needs `DASH0_OTEL_COLLECTOR_BASE_URL` to activate, and the SDK needs `OTEL_EXPORTER_OTLP_ENDPOINT` to export.
A deployment that sets only one of the two still works, because there are two bridges, in two different files, at two different points in startup.

`sitecustomize.py`, at interpreter startup, fills in the Dash0 variable from the standard one:

- If `DASH0_OTEL_COLLECTOR_BASE_URL` is unset and `OTEL_EXPORTER_OTLP_ENDPOINT` is set, the script copies the endpoint into `DASH0_OTEL_COLLECTOR_BASE_URL`.

This is what lets a deployment configured only with the standard OpenTelemetry variable activate the distribution at all.
Without it the distribution would find no collector base URL, set `OTEL_SDK_DISABLED=true` and instrument nothing.

`Dash0Distro._configure` in `distro.py`, once the SDK loads, fills in the standard variable from the Dash0 one:

- `OTEL_EXPORTER_OTLP_ENDPOINT` is defaulted to the value of `DASH0_OTEL_COLLECTOR_BASE_URL`, with `setdefault`, so an endpoint you set yourself is never replaced.

This is what lets a deployment configured only with `DASH0_OTEL_COLLECTOR_BASE_URL` point its exporters somewhere.

The two are not interchangeable.
Only the `sitecustomize.py` bridge runs under injection before the distribution decides whether to activate, so only that one determines whether an operator who sets `OTEL_EXPORTER_OTLP_ENDPOINT` alone gets any telemetry.

Prefer `DASH0_OTEL_COLLECTOR_BASE_URL` when you configure this yourself.
It is the only one of the two that works on both startup paths, because `Dash0Distro._configure` derives `OTEL_EXPORTER_OTLP_ENDPOINT` from it whether the process started under `opentelemetry-instrument` or under injection.
Setting only `OTEL_EXPORTER_OTLP_ENDPOINT` works under injection and nowhere else.
Under `opentelemetry-instrument` the `sitecustomize.py` bridge never runs, so the distribution finds no collector base URL, sets `OTEL_SDK_DISABLED=true` and exports nothing.
The Dash0 operator is the case the `sitecustomize.py` bridge exists for: it sets `OTEL_EXPORTER_OTLP_ENDPOINT` and always starts the process under injection, so it needs no change.

## Diagnostic output

`sitecustomize.py` writes its own diagnostics to stderr as one JSON object per line, under the logger name `dash0`.
Warnings also carry `dash0.monitoring.telemetry_collection_issue`, because a guard that deactivates the distribution is a telemetry collection issue.

`OTEL_INJECTOR_LOG_LEVEL` selects how much it writes.
It takes a level name, matched case-insensitively and with surrounding whitespace ignored.

| Value | Effect |
|---|---|
| unset, or empty | Warnings only. This is the default. |
| `debug` | Every step the script takes, plus warnings. |
| `info`, `warn`, `warning`, `error`, `critical` | Warnings only. |
| anything else | Warnings only, plus one warning naming the value and listing the supported levels. |

No value suppresses warnings.
A warning is the only report an operator gets when a guard deactivates the distribution, so a level above `warning` is accepted and clamped to it rather than honored literally.

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
