"""Which configuration the configurator hands to the SDK at startup.

``configure_sdk`` installs global providers that a process accepts only once,
and ``_initialize_components`` does the same on the environment-variable path,
so both are replaced with recorders. ``load_config_file`` stays real wherever
the test needs to see the SDK's own error.
"""

import pytest
from dash0.opentelemetry import configurator as configurator_module
from dash0.opentelemetry._environment_variables import (
    DASH0_BOOTSTRAP_SPAN,
    DASH0_DISABLE,
    DASH0_FLUSH_ON_SIGTERM_SIGINT,
    DASH0_OTEL_COLLECTOR_BASE_URL,
)
from dash0.opentelemetry.configurator import Dash0Configurator
from opentelemetry import configuration
from opentelemetry.configuration import ConfigurationError
from opentelemetry.sdk import _configuration as sdk_configuration
from opentelemetry.sdk.environment_variables import OTEL_CONFIG_FILE


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for variable in (
        DASH0_DISABLE,
        DASH0_BOOTSTRAP_SPAN,
        DASH0_FLUSH_ON_SIGTERM_SIGINT,
        OTEL_CONFIG_FILE,
    ):
        # setenv first so monkeypatch restores the variable even when the
        # configurator sets it during the test.
        monkeypatch.setenv(variable, "")
        monkeypatch.delenv(variable)
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")


@pytest.fixture
def default_config_file(tmp_path, monkeypatch):
    """Point the default path at a file in ``tmp_path`` that does not exist yet."""
    path = tmp_path / "etc" / "otel-config.yaml"
    monkeypatch.setattr(configurator_module, "_DEFAULT_CONFIG_FILE", str(path))
    return path


@pytest.fixture
def sdk_calls(monkeypatch):
    """Record what the SDK configures from, without installing providers."""
    calls = {"loaded": [], "configured": [], "from_environment": 0}

    def record_load(path):
        calls["loaded"].append(str(path))
        return {"file_format": "1.0"}

    def record_environment(**_kwargs):
        calls["from_environment"] += 1

    monkeypatch.setattr(configuration, "load_config_file", record_load)
    monkeypatch.setattr(configuration, "configure_sdk", calls["configured"].append)
    monkeypatch.setattr(sdk_configuration, "_initialize_components", record_environment)
    return calls


def test_explicit_config_file_wins_over_default_file(
    tmp_path, default_config_file, sdk_calls, monkeypatch
):
    default_config_file.parent.mkdir()
    default_config_file.write_text('file_format: "1.0"\n')
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text('file_format: "1.0"\n')
    monkeypatch.setenv(OTEL_CONFIG_FILE, str(explicit))

    Dash0Configurator()._configure()

    assert sdk_calls["loaded"] == [str(explicit)]
    assert sdk_calls["from_environment"] == 0


def test_explicit_missing_config_file_is_honored(
    tmp_path, default_config_file, monkeypatch
):
    default_config_file.parent.mkdir()
    default_config_file.write_text('file_format: "1.0"\n')
    missing = tmp_path / "missing.yaml"
    monkeypatch.setenv(OTEL_CONFIG_FILE, str(missing))
    configured = []
    monkeypatch.setattr(configuration, "configure_sdk", configured.append)

    with pytest.raises(ConfigurationError, match="missing.yaml"):
        Dash0Configurator()._configure()

    assert configured == []


@pytest.mark.parametrize("unset_value", [None, ""])
def test_default_config_file_is_used_when_variable_unset_or_empty(
    unset_value, default_config_file, sdk_calls, monkeypatch
):
    default_config_file.parent.mkdir()
    default_config_file.write_text('file_format: "1.0"\n')
    if unset_value is not None:
        monkeypatch.setenv(OTEL_CONFIG_FILE, unset_value)

    Dash0Configurator()._configure()

    assert sdk_calls["loaded"] == [str(default_config_file)]
    assert len(sdk_calls["configured"]) == 1
    assert sdk_calls["from_environment"] == 0


def test_environment_variables_configure_sdk_without_any_config_file(
    default_config_file, sdk_calls
):
    Dash0Configurator()._configure()

    assert sdk_calls["loaded"] == []
    assert sdk_calls["from_environment"] == 1
    assert OTEL_CONFIG_FILE not in configurator_module.environ
