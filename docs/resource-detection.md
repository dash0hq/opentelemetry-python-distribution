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

Sets `service.name` and `service.version` when they have not been provided explicitly:

| Attribute | Value |
|---|---|
| `service.name` | Derived from `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, installed package metadata, `pyproject.toml`, or entrypoint basename |
| `service.version` | The version of the installed distribution or the `pyproject.toml` that supplied the name |
| `service.instance.id` | Stable per-process UUID |

**Priority order for `service.name`:**

1. `OTEL_SERVICE_NAME` environment variable.
2. `service.name` key in `OTEL_RESOURCE_ATTRIBUTES`.
3. `Name` from the installed distribution the process was started from.
4. `[project].name` from the nearest `pyproject.toml`.
5. Basename of the entrypoint script (e.g., `app.py` → `app`).

Steps 3 and 4 also supply `service.version`, from `Version` and `[project].version`.
Steps 1, 2 and 5 do not.
No version is ever invented, because an absent version is more useful than a wrong one.

**How the installed distribution is identified.**
A process started by a console script is owned by the distribution that declared that script, which is the common shape of a `pip install .` deployment.
A process started with `python -m package` is owned by the distribution that installed the top-level package, resolved through `importlib.metadata.packages_distributions`.
A process started as a plain script, such as `python app.py`, is owned by no distribution and falls through to the next step.

Reading installed metadata rather than source is what Java's Spring Boot starter does with `build-info.properties` and what the Node.js detector does with `package.json`.
A deployed container often ships no `pyproject.toml`, and `.dist-info/METADATA` is derived from `pyproject.toml` at build time anyway.

**How `pyproject.toml` is found.**
The walk starts at the directory holding the entrypoint script, not the working directory, because `python path/to/app.py` can be run from anywhere.
It stops at a `.git` directory or at the filesystem root, so a monorepo yields the project that owns the entrypoint rather than the one at the top of the checkout.
This step needs `tomllib` and is therefore skipped on Python 3.10, which predates it.
`tomli` is deliberately not taken as a dependency.

A generic runner is identified as itself.
Running `gunicorn myapp:app` reports `service.name=gunicorn`, because the console script belongs to `gunicorn`.
That already was the behavior of the entrypoint basename, so it is not a change, but it now carries `gunicorn`'s version with it.
Set `OTEL_SERVICE_NAME` for those deployments.

The detection chain ensures that every process has a human-readable `service.name` even in injection scenarios where no explicit name has been configured.
To disable all of it, set `DASH0_AUTOMATIC_SERVICE_NAME=false`.

This detector also wraps the upstream `service` detector, so there is no need to list both `service` and `dash0_service_name` in `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`.

## Using detectors explicitly

**You normally do not need this.**
In the default execution path (`opentelemetry-instrument`), the distro injects `telemetry.distro.*`, `k8s.pod.uid`, and the service name fallback into `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_SERVICE_NAME` before the SDK initializes.
The SDK's built-in `OTELResourceDetector` picks those up automatically.
No explicit detector configuration is required.

**When you do need it: `OTEL_CONFIG_FILE`.**
The experimental declarative SDK configuration (`OTEL_CONFIG_FILE`) reads neither `OTEL_RESOURCE_ATTRIBUTES` nor `OTEL_SERVICE_NAME`, and it runs only the detectors your config file lists.
The distro adds nothing to that file, so name the detectors yourself to keep `telemetry.distro.*`, `k8s.pod.uid` and the `service.name` fallback:

```yaml
file_format: "1.0"
resource:
  detection/development:
    detectors:
      - dash0_distribution: {}
      - dash0_kubernetes: {}
      - dash0_service_name: {}
```

Each detector is independent, so list only the ones you want.
Attributes you declare under `resource.attributes` take precedence over anything a detector reports.
The Ruby and JavaScript distributions behave the same way, so one config file produces the same resource in all three languages.

`OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` has no effect here.
Declarative configuration never reads it, so setting it alongside `OTEL_CONFIG_FILE` changes nothing.

**What `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` does to the default detectors.**
This applies to the `opentelemetry-instrument` path, not the `OTEL_CONFIG_FILE` one.
The SDK always appends `service_instance` and `otel` (the `OTELResourceDetector`) to whatever you list.
You do not need to add them yourself, and you cannot remove them by omitting them.
