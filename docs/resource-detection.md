# Resource detection

The distribution ships three resource detectors registered as standard OpenTelemetry entry points.
They are activated automatically when the distribution runs and can also be referenced explicitly via `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`.

## Distribution detector (`dash0_distribution`)

Adds metadata identifying the Dash0 distribution:

| Attribute | Value |
|---|---|
| `telemetry.distro.name` | `dash0-python` |
| `telemetry.distro.version` | Current distribution version |

This attribute appears on every span, metric, and log record exported by the distribution.
It lets you filter telemetry by the distribution version in Dash0.

## Kubernetes detector (`dash0_kubernetes`)

Detects the Kubernetes pod UID when running inside a Kubernetes pod:

| Attribute | Value |
|---|---|
| `k8s.pod.uid` | UUID of the current pod |

**Detection method.** The detector first confirms it is running inside a Kubernetes pod by inspecting `/etc/hosts`.
It then extracts the pod UID from the cgroup filesystem:

- cgroup v1: reads `/proc/self/mountinfo` and extracts the pod UID from the kubepods hierarchy.
- cgroup v2: reads `/proc/self/cgroup` and parses the pod UID from the cgroup path.

cgroup v1 is tried first; cgroup v2 is the fallback.

Both standard cgroup path formats and Kubernetes slice naming conventions are handled.

If the detector cannot confirm it is inside a Kubernetes pod, or cannot extract the pod UID, it returns an empty resource without failing.

**Other `k8s.*` attributes** — such as `k8s.namespace.name`, `k8s.node.name`, `k8s.deployment.name`, and similar — cannot be read from the cgroup filesystem and are not set by this detector.
They require access to the Kubernetes API and should be added via the [OpenTelemetry Collector's `k8sattributesprocessor`](https://opentelemetry.io/docs/kubernetes/collector/components/#kubernetes-attributes-processor).
The [Dash0 Operator](https://www.dash0.com/changelog/automatic-kubernetes-resource-detection) handles this automatically for workloads it manages.
See the [OpenTelemetry Kubernetes attributes best practices](https://www.dash0.com/guides/opentelemetry-kubernetes-attributes-best-practices) guide for a full picture of how to enrich telemetry with Kubernetes metadata.

## Service name detector (`dash0_service_name`)

Sets `service.name` when it has not been provided explicitly:

| Attribute | Value |
|---|---|
| `service.name` | Derived from `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, or entrypoint basename |
| `service.instance.id` | Stable per-process UUID |

**Priority order for `service.name`:**

1. `OTEL_SERVICE_NAME` environment variable.
2. `service.name` key in `OTEL_RESOURCE_ATTRIBUTES`.
3. Basename of the entrypoint script (e.g., `app.py` → `app`).

The entrypoint fallback ensures that every process has a human-readable `service.name` even in injection scenarios where no explicit name has been configured.
To disable this fallback, set `DASH0_AUTOMATIC_SERVICE_NAME=false`.

This detector also wraps the upstream `service` detector, so there is no need to list both `service` and `dash0_service_name` in `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`.

## Using detectors explicitly

**You normally do not need this.**
In the default execution path (`opentelemetry-instrument`), the distro injects `telemetry.distro.*`, `k8s.pod.uid`, and the service name fallback into `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_SERVICE_NAME` before the SDK initializes.
The SDK's built-in `OTELResourceDetector` picks those up automatically.
No explicit detector configuration is required.

**When you do need it: `OTEL_CONFIG_FILE`.**
The experimental declarative SDK configuration (`OTEL_CONFIG_FILE`) runs only the detectors your config file lists, and it does not read `OTEL_RESOURCE_ATTRIBUTES` or `OTEL_SERVICE_NAME` by itself.
It does substitute environment variables, so you can still feed both in by naming them explicitly.
The distro adds nothing to that file, so name the detectors yourself to keep `telemetry.distro.*`, `k8s.pod.uid` and the `service.name` fallback:

```yaml
file_format: "1.0"
propagator:
  composite:
    - tracecontext: {}
    - baggage: {}
resource:
  attributes_list: ${OTEL_RESOURCE_ATTRIBUTES:-}
  detection/development:
    detectors:
      - dash0_distribution: {}
      - dash0_kubernetes: {}
      - dash0_service_name: {}
```

The `attributes_list` line is optional and shown because it is how `OTEL_RESOURCE_ATTRIBUTES` reaches a config file.
The `:-` suffix supplies an empty default, so an unset variable yields no attributes instead of an error.
Values under `resource.attributes` override anything `attributes_list` sets.

Declare the `propagator` block even though the schema allows omitting it.
A file without it installs a noop propagator, so no trace context is read from incoming requests or written to outgoing ones, and traces break at every service boundary.

Each detector is independent, so list only the ones you want.
Attributes you declare under `resource.attributes` take precedence over anything a detector reports.
The Python, Ruby and JavaScript distributions handle the `dash0_*` detectors the same way, though the complete resource still differs between them because the SDKs ship different built-in detectors.

`OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` has no effect here.
Declarative configuration never reads it, so setting it alongside `OTEL_CONFIG_FILE` changes nothing.

**What `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` does to the default detectors.**
This applies to the `opentelemetry-instrument` path, not the `OTEL_CONFIG_FILE` one.
The SDK always appends `service_instance` and `otel` (the `OTELResourceDetector`) to whatever you list.
You do not need to add them yourself, and you cannot remove them by omitting them.
