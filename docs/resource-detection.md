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

To reference detectors by name in a declarative config file or via the environment variable:

```bash
export OTEL_EXPERIMENTAL_RESOURCE_DETECTORS=dash0_distribution,dash0_kubernetes,dash0_service_name
```

Each detector is independent: you can include or omit any of them individually.
