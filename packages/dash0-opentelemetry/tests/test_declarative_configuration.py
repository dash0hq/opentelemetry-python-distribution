"""The Dash0 resource detectors under declarative configuration.

Declarative configuration runs only the detectors a config file lists, and it
does not read ``OTEL_RESOURCE_ATTRIBUTES`` or ``OTEL_SERVICE_NAME`` by itself.
A user who wants the distro's resource attributes therefore names the
``dash0_*`` detectors in their file, exactly as they would any other detector.
Nothing in the distro adds them, and the Ruby and JavaScript distributions
handle the ``dash0_*`` detectors the same way.

That makes the three entry-point names a public interface: they are the literal
text a user types into YAML. The tests below hold them to the entry points they
resolve through, hold the example in ``docs/resource-detection.md`` to the same
names, and prove that naming them produces the attributes while omitting them
does not.

``create_resource`` comes from the private module of
``dash0-opentelemetry-configuration`` because the public shims re-export only
the public ones. The coupling is to a package this repository vendors and
generates, not to a third party. Going through it rather than ``configure_sdk``
keeps each test independent, since ``configure_sdk`` installs global providers
that a process accepts only once.
"""

from importlib.metadata import entry_points
from pathlib import Path

import pytest
from dash0.opentelemetry import resource as resource_module
from dash0.opentelemetry._environment_variables import (
    DASH0_AUTOMATIC_SERVICE_NAME,
    OTEL_RESOURCE_ATTRIBUTES,
    OTEL_SERVICE_NAME,
)
from opentelemetry._configuration._resource import create_resource
from opentelemetry.configuration import load_config_file

_DASH0_DETECTOR_NAMES = (
    "dash0_distribution",
    "dash0_kubernetes",
    "dash0_service_name",
)

_POD_UID = "2edc9ee8-c9a2-4f3e-9f5e-1a2b3c4d5e6f"

_DOCUMENTED_EXAMPLE = """\
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
"""

_WITHOUT_DETECTORS = 'file_format: "1.0"\n'

_WITH_SERVICE_NAME_ATTRIBUTE = """\
file_format: "1.0"
resource:
  attributes:
    - name: service.name
      value: from-file
  detection/development:
    detectors:
      - dash0_distribution: {}
      - dash0_service_name: {}
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for variable in (
        OTEL_RESOURCE_ATTRIBUTES,
        OTEL_SERVICE_NAME,
        DASH0_AUTOMATIC_SERVICE_NAME,
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(resource_module, "running_in_kubernetes", lambda: False)
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])
    monkeypatch.setattr(resource_module, "distributions", list)
    monkeypatch.setattr(resource_module, "packages_distributions", dict)


def _resource_from(tmp_path, content):
    config_file = tmp_path / "otel-config.yaml"
    config_file.write_text(content, encoding="utf8")
    return create_resource(load_config_file(str(config_file)).resource)


def test_the_detector_names_resolve_through_the_entry_point_group():
    """Hold the names a user types in YAML to the entry points behind them.

    ``create_resource`` looks each name up in the
    ``opentelemetry_resource_detector`` group, so renaming an entry point
    without renaming it here breaks every config file that lists it.
    """
    group = entry_points(group="opentelemetry_resource_detector")
    registered = {point.name for point in group if point.name.startswith("dash0_")}

    assert registered == set(_DASH0_DETECTOR_NAMES)
    for name in _DASH0_DETECTOR_NAMES:
        (point,) = (candidate for candidate in group if candidate.name == name)
        point.load()


def test_the_documented_example_is_the_one_these_tests_exercise():
    """Hold ``docs/resource-detection.md`` to the YAML proven to work here.

    The documented block is what a user copies, so a rename that this suite
    catches everywhere else would still leave the docs telling people to write
    a name that no longer resolves.
    """
    documentation = Path(__file__).resolve().parents[3] / "docs"

    text = (documentation / "resource-detection.md").read_text(encoding="utf8")

    assert _DOCUMENTED_EXAMPLE in text


def test_a_config_file_listing_the_detectors_produces_the_dash0_attributes(tmp_path):
    attributes = _resource_from(tmp_path, _DOCUMENTED_EXAMPLE).attributes

    assert attributes["telemetry.distro.name"] == "dash0-python"
    assert attributes["telemetry.distro.version"]
    assert attributes["service.name"] == "server"
    assert attributes["service.instance.id"]


def test_the_documented_example_interpolates_otel_resource_attributes(
    monkeypatch, tmp_path
):
    """Hold the one claim the page makes that the detectors do not cover.

    Declarative configuration does not read ``OTEL_RESOURCE_ATTRIBUTES`` on its
    own, so the documented example names it through
    ``${OTEL_RESOURCE_ATTRIBUTES:-}``. Every other test here runs that example
    with the variable unset, which proves the default is harmless but not that
    a value arrives.
    """
    monkeypatch.setenv(
        OTEL_RESOURCE_ATTRIBUTES, "deployment.environment=prod,team=payments"
    )

    attributes = _resource_from(tmp_path, _DOCUMENTED_EXAMPLE).attributes

    assert attributes["deployment.environment"] == "prod"
    assert attributes["team"] == "payments"


def test_the_kubernetes_detector_reports_the_pod_uid(monkeypatch, tmp_path):
    monkeypatch.setattr(resource_module, "detect_kubernetes_pod_uid", lambda: _POD_UID)

    attributes = _resource_from(tmp_path, _DOCUMENTED_EXAMPLE).attributes

    assert attributes["k8s.pod.uid"] == _POD_UID


def test_a_config_file_without_the_detectors_has_no_dash0_attributes(tmp_path):
    """The opt-in design, stated as a test.

    Omitting the detectors drops the distro's attributes, and that is the
    intended behaviour rather than a defect. A change that started adding them
    unasked, here or upstream, fails this.
    """
    attributes = _resource_from(tmp_path, _WITHOUT_DETECTORS).attributes

    assert "telemetry.distro.name" not in attributes
    assert "k8s.pod.uid" not in attributes
    assert attributes["service.name"] == "unknown_service"


def test_attributes_declared_in_the_config_file_win_over_detected_ones(tmp_path):
    attributes = _resource_from(tmp_path, _WITH_SERVICE_NAME_ATTRIBUTE).attributes

    assert attributes["service.name"] == "from-file"
    assert attributes["telemetry.distro.name"] == "dash0-python"
