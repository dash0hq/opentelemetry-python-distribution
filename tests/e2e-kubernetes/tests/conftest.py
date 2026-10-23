"""Brings up the cluster, the images and the workloads once per session."""

from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory

from cluster import (
    MANIFESTS,
    NAMESPACE,
    build_images,
    cluster_exists,
    collector_config,
    create_cluster,
    kubectl,
    load_images,
    read_exported,
    wait_for,
)
from pytest import fixture


@fixture(scope="session")
def deployed() -> None:
    """Everything the assertions need, brought up exactly once."""
    if not cluster_exists():
        create_cluster()

    build_images()
    load_images()

    kubectl(
        "delete",
        "namespace",
        NAMESPACE,
        "--ignore-not-found",
        "--wait",
        timeout=300,
    )
    kubectl("apply", "-f", str(MANIFESTS / "00-namespace.yaml"))

    with TemporaryDirectory() as directory:
        config = Path(directory) / "config.yaml"
        config.write_text(collector_config(), encoding="utf-8")
        rendered = Path(directory) / "configmap.yaml"
        rendered.write_text(
            kubectl(
                "-n",
                NAMESPACE,
                "create",
                "configmap",
                "collector-config",
                f"--from-file=config.yaml={config}",
                "--dry-run=client",
                "-o",
                "yaml",
            ),
            encoding="utf-8",
        )
        kubectl("apply", "-f", str(rendered))

    for manifest in sorted(MANIFESTS.glob("*.yaml")):
        kubectl("apply", "-f", str(manifest))

    for deployment in ("collector", "app-environment", "app-declarative"):
        kubectl(
            "-n",
            NAMESPACE,
            "rollout",
            "status",
            f"deployment/{deployment}",
            "--timeout=300s",
            timeout=360,
        )

    kubectl(
        "-n",
        NAMESPACE,
        "wait",
        "--for=condition=complete",
        "job/traffic",
        "--timeout=300s",
        timeout=360,
    )

    wait_for(
        "both applications to export spans",
        lambda: len(read_exported("traces.jsonl")) >= 2,
        timeout=180,
    )


@fixture(scope="session")
def trace_records(deployed) -> list[dict]:
    return read_exported("traces.jsonl")


@fixture(scope="session")
def dash0_credentials_present() -> bool:
    return bool(environ.get("DASH0_ENDPOINT") and environ.get("DASH0_AUTH_TOKEN"))
