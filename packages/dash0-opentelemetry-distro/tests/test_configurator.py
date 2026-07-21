"""Declarative-configuration (OTEL_CONFIG_FILE) handling of Dash0Configurator.

These tests need the declarative-configuration machinery (the
``opentelemetry-sdk[file-configuration]`` extra on SDK 1.43, a dev dependency,
or the standalone ``opentelemetry-configuration`` package on SDK 1.44+); they
are skipped when it is not installed.
"""

import pytest
from dash0.opentelemetry import resource as resource_module
from dash0.opentelemetry._environment_variables import (
    DASH0_AUTOMATIC_SERVICE_NAME,
    OTEL_CONFIG_FILE,
    OTEL_RESOURCE_ATTRIBUTES,
    OTEL_SERVICE_NAME,
)
from dash0.opentelemetry.configurator import (
    Dash0Configurator,
    _add_dash0_resource_detectors,
    _load_declarative_machinery,
)

try:
    load_config_file, _, models = _load_declarative_machinery()
except ImportError:
    pytest.skip(
        "declarative-configuration machinery not installed",
        allow_module_level=True,
    )

try:
    import opentelemetry.configuration as _configure_sdk_module
    from opentelemetry.configuration._resource import create_resource
except ImportError:
    import opentelemetry.sdk._configuration._sdk as _configure_sdk_module
    from opentelemetry.sdk._configuration._resource import create_resource

_MINIMAL_CONFIG = 'file_format: "1.0"\n'

_CONFIG_WITH_SERVICE_NAME = """\
file_format: "1.0"
resource:
  attributes:
    - name: service.name
      value: from-file
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for variable in (
        OTEL_CONFIG_FILE,
        OTEL_RESOURCE_ATTRIBUTES,
        OTEL_SERVICE_NAME,
        DASH0_AUTOMATIC_SERVICE_NAME,
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(resource_module, "running_in_kubernetes", lambda: False)
    monkeypatch.setattr(resource_module.sys, "argv", ["/opt/app/server.py"])


def _load(tmp_path, content):
    config_file = tmp_path / "otel-config.yaml"
    config_file.write_text(content, encoding="utf8")
    return config_file


def test_detectors_injected_into_config_without_resource_section(tmp_path):
    config = load_config_file(str(_load(tmp_path, _MINIMAL_CONFIG)))

    _add_dash0_resource_detectors(config, models)
    attributes = create_resource(config.resource).attributes

    assert attributes["telemetry.distro.name"] == "dash0-python"
    assert attributes["service.name"] == "server"
    assert attributes["service.instance.id"]


def test_config_file_attributes_win_over_detected_ones(tmp_path):
    config = load_config_file(str(_load(tmp_path, _CONFIG_WITH_SERVICE_NAME)))

    _add_dash0_resource_detectors(config, models)
    attributes = create_resource(config.resource).attributes

    assert attributes["telemetry.distro.name"] == "dash0-python"
    assert attributes["service.name"] == "from-file"


def test_detectors_already_listed_are_not_injected_twice(tmp_path):
    config = load_config_file(str(_load(tmp_path, _MINIMAL_CONFIG)))
    # Built programmatically rather than from YAML: on SDK 1.43 the loader
    # rejects the spec's `detection/development` key (fixed in 1.44).
    config.resource = models.Resource(
        detection_development=models.ExperimentalResourceDetection(
            detectors=[models.ExperimentalResourceDetector(dash0_kubernetes=None)]
        )
    )

    _add_dash0_resource_detectors(config, models)

    listed = [
        name
        for detector in config.resource.detection_development.detectors
        for name in getattr(detector, "additional_properties", {})
    ]
    assert listed.count("dash0_kubernetes") == 1
    assert listed.count("dash0_distribution") == 1
    assert listed.count("dash0_service_name") == 1


def test_configurator_skips_declarative_path_without_config_file():
    assert Dash0Configurator()._configure_from_declarative_file() is False


def test_configurator_applies_declarative_config_with_detector(monkeypatch, tmp_path):
    monkeypatch.setenv(OTEL_CONFIG_FILE, str(_load(tmp_path, _MINIMAL_CONFIG)))
    applied = {}
    monkeypatch.setattr(
        _configure_sdk_module,
        "configure_sdk",
        lambda config: applied.update(config=config),
    )

    assert Dash0Configurator()._configure_from_declarative_file() is True

    attributes = create_resource(applied["config"].resource).attributes
    assert attributes["telemetry.distro.name"] == "dash0-python"
    assert attributes["service.name"] == "server"
