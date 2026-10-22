import os
from importlib.util import find_spec

import pytest
from dash0.opentelemetry import resource as resource_module
from dash0.opentelemetry._environment_variables import (
    DASH0_AUTOMATIC_SERVICE_NAME,
    OTEL_RESOURCE_ATTRIBUTES,
    OTEL_SERVICE_NAME,
)
from dash0.opentelemetry.resource import (
    Dash0DistributionResourceDetector,
    Dash0KubernetesResourceDetector,
    Dash0ServiceNameResourceDetector,
    apply_detected_resource_attributes,
    detect_fallback_service_name,
    detect_service_metadata,
    distribution_of_running_program,
    module_run_with_dash_m,
    pod_uid_from_cgroup_v1,
    pod_uid_from_cgroup_v2,
    service_metadata_from_pyproject,
)
from dash0.opentelemetry.version import __version__

_POD_UID = "2edc9ee8-c9a2-4f3e-9f5e-1a2b3c4d5e6f"

_needs_tomllib = pytest.mark.skipif(
    find_spec("tomllib") is None,
    reason="reading pyproject.toml needs tomllib, which arrived in 3.11",
)


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
    monkeypatch.setattr(resource_module, "distributions", list)
    monkeypatch.setattr(resource_module, "packages_distributions", dict)


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


def test_distribution_detector_reports_distro_attributes():
    attributes = Dash0DistributionResourceDetector().detect().attributes

    assert attributes["telemetry.distro.name"] == "dash0-python"
    assert attributes["telemetry.distro.version"] == __version__


def test_kubernetes_detector_reports_pod_uid(monkeypatch):
    monkeypatch.setattr(resource_module, "detect_kubernetes_pod_uid", lambda: _POD_UID)

    attributes = Dash0KubernetesResourceDetector().detect().attributes

    assert attributes["k8s.pod.uid"] == _POD_UID


def test_kubernetes_detector_is_empty_outside_kubernetes():
    assert not Dash0KubernetesResourceDetector().detect().attributes


def test_service_name_detector_reports_fallback_service_name(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])

    attributes = Dash0ServiceNameResourceDetector().detect().attributes

    assert attributes["service.name"] == "server"


def test_service_name_detector_wraps_upstream_instance_id(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])

    attributes = Dash0ServiceNameResourceDetector().detect().attributes

    # Mirrors the upstream declarative `service` detector, which reports a
    # process-stable service.instance.id alongside the service name.
    assert attributes["service.instance.id"]


def test_service_name_detector_prefers_otel_service_name(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])
    monkeypatch.setenv(OTEL_SERVICE_NAME, "explicit")

    attributes = Dash0ServiceNameResourceDetector().detect().attributes

    assert attributes["service.name"] == "explicit"


def test_service_name_detector_respects_opt_out(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])
    monkeypatch.setenv(DASH0_AUTOMATIC_SERVICE_NAME, "false")

    attributes = Dash0ServiceNameResourceDetector().detect().attributes

    assert "service.name" not in attributes


def test_service_name_detector_suppresses_fallback_for_resource_attributes(
    monkeypatch,
):
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])
    monkeypatch.setenv(OTEL_RESOURCE_ATTRIBUTES, "service.name=elsewhere")

    attributes = Dash0ServiceNameResourceDetector().detect().attributes

    # Declarative configuration ignores OTEL_RESOURCE_ATTRIBUTES by design, so
    # the detector neither resurrects the value nor papers over it with the
    # entrypoint fallback.
    assert "service.name" not in attributes


class _FakeEntryPoint:
    def __init__(self, group, name):
        self.group = group
        self.name = name


class _FakeDistribution:
    def __init__(self, name, version, scripts=()):
        self.metadata = {"Name": name, "Version": version}
        self.entry_points = [
            _FakeEntryPoint("console_scripts", script) for script in scripts
        ]


def test_a_console_script_names_the_distribution_that_declared_it(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/usr/local/bin/checkout"])
    monkeypatch.setattr(
        resource_module,
        "distributions",
        lambda: [_FakeDistribution("checkout-service", "2.4.0", ("checkout",))],
    )

    assert detect_service_metadata() == ("checkout-service", "2.4.0")


def test_a_script_run_directly_claims_no_distribution(monkeypatch):
    """A path ending in .py is not a console script, so the scan is skipped."""
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])
    monkeypatch.setattr(
        resource_module,
        "distributions",
        lambda: [_FakeDistribution("server", "1.0.0", ("server",))],
    )
    monkeypatch.setattr(resource_module, "packages_distributions", dict)

    assert distribution_of_running_program() is None


_PYTHON = "/usr/local/bin/python3.13"

_DASH_M_COMMAND_LINES = [
    ([_PYTHON, "-m", "checkout"], ["-m"]),
    ([_PYTHON, "-m", "checkout", "alpha", "beta"], ["-m", "alpha", "beta"]),
    ([_PYTHON, "-u", "-m", "checkout", "alpha"], ["-m", "alpha"]),
    ([_PYTHON, "-um", "checkout", "alpha"], ["-m", "alpha"]),
    ([_PYTHON, "-W", "ignore", "-m", "checkout"], ["-m"]),
    ([_PYTHON, "-X", "importtime", "-m", "checkout", "alpha"], ["-m", "alpha"]),
    (
        [_PYTHON, "-B", "-W", "ignore", "-X", "utf8", "-m", "checkout", "a", "b"],
        ["-m", "a", "b"],
    ),
]


@pytest.mark.parametrize("orig_argv, argv", _DASH_M_COMMAND_LINES)
def test_the_module_survives_every_spelling_of_dash_m(monkeypatch, orig_argv, argv):
    """Each pair is what a real interpreter reports at ``sitecustomize`` time.

    The flags are never parsed, so a cluster such as ``-um`` and an option
    carrying a value such as ``-W ignore`` both have to land on the module.
    """
    monkeypatch.setattr(resource_module.sys, "orig_argv", orig_argv)
    monkeypatch.setattr(resource_module.sys, "argv", argv)

    assert module_run_with_dash_m() == "checkout"


def test_a_command_line_without_dash_m_yields_no_module(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "orig_argv", [_PYTHON, "/opt/app/app.py"])
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/app.py"])

    assert module_run_with_dash_m() is None


def test_python_dash_m_names_the_distribution_that_installed_the_package(monkeypatch):
    """``__main__`` does not exist yet, so the module comes from ``orig_argv``."""
    monkeypatch.setattr(
        resource_module.sys, "orig_argv", [_PYTHON, "-m", "checkout.cli"]
    )
    monkeypatch.setattr(resource_module.sys, "argv", ["-m"])
    monkeypatch.setattr(
        resource_module,
        "packages_distributions",
        lambda: {"checkout": ["checkout-service"]},
    )
    monkeypatch.setattr(
        resource_module,
        "distributions",
        lambda: [_FakeDistribution("checkout_service", "3.1.0")],
    )

    assert detect_service_metadata() == ("checkout_service", "3.1.0")


def test_python_dash_m_never_reports_the_flag_as_the_service_name(monkeypatch):
    """The regression: ``path.basename("-m")`` used to become the service name."""
    monkeypatch.setattr(resource_module.sys, "orig_argv", [_PYTHON, "-m", "checkout"])
    monkeypatch.setattr(resource_module.sys, "argv", ["-m"])

    assert detect_fallback_service_name() == "checkout"


def test_an_unresolvable_dash_m_reports_no_service_name(monkeypatch):
    """Without ``orig_argv`` there is no module to name, and ``-m`` is not one."""
    monkeypatch.setattr(resource_module.sys, "orig_argv", [])
    monkeypatch.setattr(resource_module.sys, "argv", ["-m"])

    assert detect_fallback_service_name() is None


def test_a_generic_runner_claims_no_distribution(monkeypatch):
    """``gunicorn`` declares a console script, but it launches someone else."""
    monkeypatch.setattr(resource_module.sys, "argv", ["/usr/local/bin/gunicorn"])
    monkeypatch.setattr(
        resource_module,
        "distributions",
        lambda: [_FakeDistribution("gunicorn", "23.0.0", ("gunicorn",))],
    )

    assert distribution_of_running_program() is None


def test_a_generic_runner_supplies_no_fallback_name(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/usr/local/bin/gunicorn"])

    assert detect_fallback_service_name() is None


def test_a_django_manage_script_supplies_no_fallback_name(monkeypatch):
    """The ``.py`` suffix comes off before the runner check, or it never matches."""
    monkeypatch.setattr(resource_module.sys, "argv", ["/app/manage.py"])

    assert detect_fallback_service_name() is None


def test_a_generic_runner_leaves_the_service_name_unset(monkeypatch):
    """Nothing identifies the service, so ``unknown_service`` has to stand."""
    monkeypatch.setattr(resource_module.sys, "argv", ["/usr/local/bin/gunicorn"])
    monkeypatch.setattr(
        resource_module,
        "distributions",
        lambda: [_FakeDistribution("gunicorn", "23.0.0", ("gunicorn",))],
    )
    monkeypatch.setattr(
        resource_module, "service_metadata_from_pyproject", lambda: (None, None)
    )

    assert detect_service_metadata() == (None, None)

    apply_detected_resource_attributes("9.9.9")

    assert OTEL_SERVICE_NAME not in os.environ
    assert "service.version" not in os.environ.get(OTEL_RESOURCE_ATTRIBUTES, "")


@_needs_tomllib
def test_pyproject_supplies_the_name_when_nothing_is_installed(monkeypatch, tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "checkout-service"\nversion = "0.9.1"\n', encoding="utf8"
    )
    monkeypatch.setattr(resource_module.sys, "argv", [str(source / "app.py")])
    monkeypatch.setattr(resource_module, "distributions", list)
    monkeypatch.setattr(resource_module, "packages_distributions", dict)

    assert service_metadata_from_pyproject() == ("checkout-service", "0.9.1")
    assert detect_service_metadata() == ("checkout-service", "0.9.1")


@_needs_tomllib
def test_the_walk_up_stops_at_a_git_directory(monkeypatch, tmp_path):
    """A monorepo must not hand the entrypoint the root project's name."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "the-monorepo"\n', encoding="utf8"
    )
    inner = tmp_path / "services" / "checkout"
    inner.mkdir(parents=True)
    (inner / ".git").mkdir()
    monkeypatch.setattr(resource_module.sys, "argv", [str(inner / "app.py")])

    assert service_metadata_from_pyproject() == (None, None)


@_needs_tomllib
def test_a_pyproject_without_a_project_table_is_ignored(monkeypatch, tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 88\n", encoding="utf8"
    )
    monkeypatch.setattr(resource_module.sys, "argv", [str(tmp_path / "app.py")])
    monkeypatch.setattr(resource_module, "distributions", list)
    monkeypatch.setattr(resource_module, "packages_distributions", dict)

    assert service_metadata_from_pyproject() == (None, None)
    assert detect_service_metadata() == ("app", None)


def test_a_version_is_never_invented(monkeypatch):
    """Absent is better than wrong, so the entrypoint fallback carries none."""
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])
    monkeypatch.setattr(resource_module, "distributions", list)
    monkeypatch.setattr(resource_module, "packages_distributions", dict)

    assert detect_service_metadata() == ("server", None)


def test_apply_reports_the_detected_service_version(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/usr/local/bin/checkout"])
    monkeypatch.setattr(
        resource_module,
        "distributions",
        lambda: [_FakeDistribution("checkout-service", "2.4.0", ("checkout",))],
    )

    apply_detected_resource_attributes("9.9.9")

    assert os.environ[OTEL_SERVICE_NAME] == "checkout-service"
    assert "service.version=2.4.0" in os.environ[OTEL_RESOURCE_ATTRIBUTES]


def test_an_explicit_service_name_suppresses_detection_entirely(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/usr/local/bin/checkout"])
    monkeypatch.setattr(
        resource_module,
        "distributions",
        lambda: [_FakeDistribution("checkout-service", "2.4.0", ("checkout",))],
    )
    monkeypatch.setenv(OTEL_SERVICE_NAME, "explicit")

    apply_detected_resource_attributes("9.9.9")

    assert os.environ[OTEL_SERVICE_NAME] == "explicit"
    assert "service.version" not in os.environ[OTEL_RESOURCE_ATTRIBUTES]


def test_the_declarative_detector_reports_name_and_version(monkeypatch):
    monkeypatch.setattr(resource_module.sys, "argv", ["/usr/local/bin/checkout"])
    monkeypatch.setattr(
        resource_module,
        "distributions",
        lambda: [_FakeDistribution("checkout-service", "2.4.0", ("checkout",))],
    )

    attributes = Dash0ServiceNameResourceDetector().detect().attributes

    assert attributes["service.name"] == "checkout-service"
    assert attributes["service.version"] == "2.4.0"
    assert attributes["service.instance.id"]
