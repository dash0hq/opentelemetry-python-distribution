"""Thin wrappers over the external commands the end-to-end test drives.

Everything here shells out. There is no Kubernetes client dependency on
purpose: the test has to be runnable from a checkout with nothing installed
beyond pytest, and ``kubectl`` is already a prerequisite for having a cluster.
"""

from json import loads
from os import environ
from pathlib import Path
from subprocess import CompletedProcess
from subprocess import run as subprocess_run
from time import sleep, time

NAMESPACE: str = "dash0-e2e"
CLUSTER: str = environ.get("E2E_CLUSTER", "dash0-python-e2e")
KIND: str = environ.get("KIND_BINARY", "kind")
REPO_ROOT: Path = Path(__file__).resolve().parents[3]
MANIFESTS: Path = Path(__file__).resolve().parents[1] / "manifests"

APP_IMAGE: str = "dash0-e2e-app:test"
INSTALLED_APP_IMAGE: str = "dash0-e2e-app-installed:test"
INSTRUMENTATION_IMAGE: str = "dash0-e2e-instrumentation:test"


def run(command: list[str], check: bool = True, timeout: int = 900) -> CompletedProcess:
    """Run a command, capturing both streams, and fail loudly with their text."""
    result = subprocess_run(command, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise AssertionError(
            "command failed: {}\nexit {}\nstdout:\n{}\nstderr:\n{}".format(
                " ".join(command), result.returncode, result.stdout, result.stderr
            )
        )
    return result


def kubectl(*arguments: str, check: bool = True, timeout: int = 300) -> str:
    context = f"kind-{CLUSTER}"
    return run(
        ["kubectl", "--context", context, *arguments], check=check, timeout=timeout
    ).stdout


def cluster_exists() -> bool:
    return CLUSTER in run([KIND, "get", "clusters"], check=False).stdout.split()


def create_cluster() -> None:
    run([KIND, "create", "cluster", "--name", CLUSTER, "--wait", "180s"])


def build_images() -> None:
    """Build every image from this checkout.

    The instrumentation image builds from the repository root, so the
    distribution comes from the working copy rather than from an index. The two
    application images build from their own directories and know nothing about
    the distribution.
    """
    for image, directory in (
        (APP_IMAGE, "app"),
        (INSTALLED_APP_IMAGE, "app-installed"),
    ):
        run(
            [
                "docker",
                "build",
                "-q",
                "-t",
                image,
                "-f",
                str(MANIFESTS.parent / directory / "Dockerfile"),
                str(MANIFESTS.parent / directory),
            ]
        )
    run(
        [
            "docker",
            "build",
            "-q",
            "-t",
            INSTRUMENTATION_IMAGE,
            "-f",
            str(MANIFESTS.parent / "instrumentation" / "Dockerfile"),
            str(REPO_ROOT),
        ]
    )


def load_images() -> None:
    for image in (APP_IMAGE, INSTALLED_APP_IMAGE, INSTRUMENTATION_IMAGE):
        run([KIND, "load", "docker-image", "--name", CLUSTER, image])


def collector_config() -> str:
    """Render the collector configuration.

    The Dash0 exporter is added only when credentials are in the environment,
    so the test is runnable offline and still writes to a real organization
    when ``DASH0_ENDPOINT`` and ``DASH0_AUTH_TOKEN`` are set.
    """
    endpoint = environ.get("DASH0_ENDPOINT")
    token = environ.get("DASH0_AUTH_TOKEN")
    dataset = environ.get("DASH0_DATASET", "default")

    exporters = [
        "  file/traces:",
        "    path: /output/traces.jsonl",
        "  file/metrics:",
        "    path: /output/metrics.jsonl",
        "  file/logs:",
        "    path: /output/logs.jsonl",
    ]
    trace_exporters = ["file/traces"]
    metric_exporters = ["file/metrics"]
    log_exporters = ["file/logs"]

    if endpoint and token:
        exporters.extend(
            [
                "  otlphttp/dash0:",
                f"    endpoint: {endpoint}",
                "    headers:",
                f'      Authorization: "Bearer {token}"',
                f'      Dash0-Dataset: "{dataset}"',
            ]
        )
        trace_exporters.append("otlphttp/dash0")
        metric_exporters.append("otlphttp/dash0")
        log_exporters.append("otlphttp/dash0")

    return "\n".join(
        [
            "receivers:",
            "  otlp:",
            "    protocols:",
            "      http:",
            "        endpoint: 0.0.0.0:4318",
            "",
            "exporters:",
            *exporters,
            "",
            "service:",
            "  pipelines:",
            "    traces:",
            "      receivers: [otlp]",
            f"      exporters: [{', '.join(trace_exporters)}]",
            "    metrics:",
            "      receivers: [otlp]",
            f"      exporters: [{', '.join(metric_exporters)}]",
            "    logs:",
            "      receivers: [otlp]",
            f"      exporters: [{', '.join(log_exporters)}]",
            "",
        ]
    )


def wait_for(description: str, predicate, timeout: int = 300, interval: float = 3.0):
    """Poll until the predicate returns something truthy, or fail saying what."""
    deadline = time() + timeout
    last = None
    while time() < deadline:
        last = predicate()
        if last:
            return last
        sleep(interval)
    raise AssertionError(f"timed out after {timeout}s waiting for {description}")


def pod_uid(selector: str) -> str:
    """The UID Kubernetes assigned to the single running pod of a deployment."""
    raw = kubectl(
        "-n",
        NAMESPACE,
        "get",
        "pods",
        "-l",
        selector,
        "--field-selector=status.phase=Running",
        "-o",
        "jsonpath={.items[0].metadata.uid}",
    )
    return raw.strip()


def read_exported(filename: str) -> list[dict]:
    """Read one of the collector's JSONL files through the reader sidecar."""
    raw = kubectl(
        "-n",
        NAMESPACE,
        "exec",
        "deploy/collector",
        "-c",
        "reader",
        "--",
        "cat",
        f"/output/{filename}",
        check=False,
    )
    records = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(loads(line))
        except ValueError:
            continue
    return records
