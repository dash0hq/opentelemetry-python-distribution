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
The experimental declarative SDK configuration (`OTEL_CONFIG_FILE`) ignores `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_SERVICE_NAME` by design.
In that case, reference the detectors explicitly in the config file, or via the environment variable:

```bash
export OTEL_EXPERIMENTAL_RESOURCE_DETECTORS=dash0_distribution,dash0_kubernetes,dash0_service_name
```

You must list all three if you want all three — none of the Dash0 detectors are included by default in the declarative config path.

**What `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` does to the default detectors.**
The SDK always appends `service_instance` and `otel` (the `OTELResourceDetector`) to whatever you list.
You do not need to add them yourself, and you cannot remove them by omitting them.
