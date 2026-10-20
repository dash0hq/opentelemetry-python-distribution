"""Declarative-configuration (OTEL_CONFIG_FILE) handling of Dash0Configurator.

These tests need the ``opentelemetry-configuration`` package, which the pinned
SDK pulls in through the ``opentelemetry-sdk[file-configuration]`` extra, a dev
dependency; they are skipped when it is not installed.
"""

from logging import WARNING

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

from opentelemetry import configuration as _configure_sdk_module
from opentelemetry.configuration._resource import create_resource

_POD_UID = "2edc9ee8-c9a2-4f3e-9f5e-1a2b3c4d5e6f"

_MINIMAL_CONFIG = 'file_format: "1.0"\n'

_CONFIG_WITH_SERVICE_NAME = """\
file_format: "1.0"
resource:
  attributes:
    - name: service.name
      value: from-file
"""

_CONFIG_WITH_DETECTOR = """\
file_format: "1.0"
resource:
  detection/development:
    detectors:
      - dash0_kubernetes: {}
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


def test_pod_uid_is_detected_under_declarative_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(resource_module, "detect_kubernetes_pod_uid", lambda: _POD_UID)
    config = load_config_file(str(_load(tmp_path, _MINIMAL_CONFIG)))

    _add_dash0_resource_detectors(config, models)
    attributes = create_resource(config.resource).attributes

    assert attributes["k8s.pod.uid"] == _POD_UID


def test_config_file_attributes_win_over_detected_ones(tmp_path):
    config = load_config_file(str(_load(tmp_path, _CONFIG_WITH_SERVICE_NAME)))

    _add_dash0_resource_detectors(config, models)
    attributes = create_resource(config.resource).attributes

    assert attributes["telemetry.distro.name"] == "dash0-python"
    assert attributes["service.name"] == "from-file"


def test_detectors_already_listed_are_not_injected_twice(tmp_path):
    config = load_config_file(str(_load(tmp_path, _CONFIG_WITH_DETECTOR)))

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


def test_ignored_configurator_kwargs_are_reported(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv(OTEL_CONFIG_FILE, str(_load(tmp_path, _MINIMAL_CONFIG)))
    monkeypatch.setattr(_configure_sdk_module, "configure_sdk", lambda config: None)

    with caplog.at_level(WARNING):
        assert (
            Dash0Configurator()._configure_from_declarative_file(
                auto_instrumentation_version="1.2.3"
            )
            is True
        )

    expected = "ignoring configurator kwargs: ['auto_instrumentation_version']"
    assert expected in caplog.text


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
