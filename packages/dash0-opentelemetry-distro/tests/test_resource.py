import os

import pytest
from dash0.opentelemetry import resource as resource_module
from dash0.opentelemetry._environment_variables import (
    DASH0_AUTOMATIC_SERVICE_NAME,
    OTEL_RESOURCE_ATTRIBUTES,
    OTEL_SERVICE_NAME,
)
from dash0.opentelemetry.resource import (
    apply_detected_resource_attributes,
    detect_fallback_service_name,
    pod_uid_from_cgroup_v1,
    pod_uid_from_cgroup_v2,
)

_POD_UID = "2edc9ee8-c9a2-4f3e-9f5e-1a2b3c4d5e6f"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for variable in (
        OTEL_RESOURCE_ATTRIBUTES,
        OTEL_SERVICE_NAME,
        DASH0_AUTOMATIC_SERVICE_NAME,
    ):
        monkeypatch.delenv(variable, raising=False)
    # No Kubernetes by default, so detection stays inert unless a test opts in.
    monkeypatch.setattr(resource_module, "running_in_kubernetes", lambda: False)


def test_pod_uid_from_cgroup_v1(monkeypatch):
    line = f"1234 1234 0:42 / /var/lib/kubelet/pods/{_POD_UID}/etc-hosts rw"
    monkeypatch.setattr(
        resource_module, "_read_candidate_lines", lambda *a, **k: [line]
    )
    assert pod_uid_from_cgroup_v1() == _POD_UID


def test_pod_uid_from_cgroup_v2(monkeypatch):
    slice_uid = _POD_UID.replace("-", "_")
    line = (
        "0::/kubepods.slice/kubepods-besteffort.slice/"
        f"kubepods-besteffort-pod{slice_uid}.slice/"
        "cri-containerd-" + ("a" * 64) + ".scope"
    )
    monkeypatch.setattr(
        resource_module, "_read_candidate_lines", lambda *a, **k: [line]
    )
    assert pod_uid_from_cgroup_v2() == _POD_UID


def test_detect_fallback_service_name(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])
    assert detect_fallback_service_name() == "server"


def test_apply_sets_distro_attributes_and_service_name(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])

    apply_detected_resource_attributes("9.9.9")

    assert os.environ[OTEL_SERVICE_NAME] == "server"
    attributes = os.environ[OTEL_RESOURCE_ATTRIBUTES]
    assert "telemetry.distro.name=dash0-python" in attributes
    assert "telemetry.distro.version=9.9.9" in attributes


def test_apply_respects_existing_service_name(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])
    monkeypatch.setenv(OTEL_SERVICE_NAME, "explicit")

    apply_detected_resource_attributes("9.9.9")

    assert os.environ[OTEL_SERVICE_NAME] == "explicit"


def test_apply_respects_service_name_opt_out(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])
    monkeypatch.setenv(DASH0_AUTOMATIC_SERVICE_NAME, "false")

    apply_detected_resource_attributes("9.9.9")

    assert OTEL_SERVICE_NAME not in os.environ


def test_merge_does_not_override_existing_attribute(monkeypatch):
    monkeypatch.setenv(OTEL_RESOURCE_ATTRIBUTES, "telemetry.distro.name=custom")
    monkeypatch.setattr(resource_module.sys, "argv", ["server.py"])

    apply_detected_resource_attributes("9.9.9")

    attributes = os.environ[OTEL_RESOURCE_ATTRIBUTES]
    assert "telemetry.distro.name=custom" in attributes
    assert "telemetry.distro.name=dash0-python" not in attributes
