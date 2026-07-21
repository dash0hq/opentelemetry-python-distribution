import logging

import pytest
from dash0.opentelemetry import configurator as configurator_module
from dash0.opentelemetry._environment_variables import (
    DASH0_BOOTSTRAP_SPAN,
    DASH0_FLUSH_ON_SIGTERM_SIGINT,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_CONFIG_FILE,
)
from dash0.opentelemetry.configurator import (
    Dash0Configurator,
    _declarative_config_import_error,
)
from opentelemetry.sdk._configuration import _OTelSDKConfigurator

_MANAGED_VARS = (
    DASH0_BOOTSTRAP_SPAN,
    DASH0_FLUSH_ON_SIGTERM_SIGINT,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_CONFIG_FILE,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for variable in _MANAGED_VARS:
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def _record_sdk_configure(monkeypatch):
    calls = []
    monkeypatch.setattr(
        _OTelSDKConfigurator,
        "_configure",
        lambda self, **kwargs: calls.append(kwargs),
    )
    return calls


def test_configure_skips_sdk_when_declarative_config_unavailable(
    monkeypatch, caplog, _record_sdk_configure
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_CONFIG_FILE, "/etc/otel/config.yaml")
    monkeypatch.setattr(
        configurator_module,
        "_declarative_config_import_error",
        lambda: "declarative configuration requires pyyaml",
    )

    with caplog.at_level(logging.ERROR, logger=configurator_module.__name__):
        Dash0Configurator().configure()

    # One actionable error instead of a traceback, and no half-configured SDK.
    assert not _record_sdk_configure
    assert any(
        OTEL_CONFIG_FILE in record.getMessage() and "pyyaml" in record.getMessage()
        for record in caplog.records
    )


def test_configure_uses_sdk_configurator_when_declarative_config_available(
    monkeypatch, _record_sdk_configure
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_CONFIG_FILE, "/etc/otel/config.yaml")
    monkeypatch.setattr(
        configurator_module,
        "_declarative_config_import_error",
        lambda: None,
    )

    Dash0Configurator().configure()

    assert len(_record_sdk_configure) == 1


def test_configure_without_config_file_never_checks_imports(
    monkeypatch, _record_sdk_configure
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")

    def _must_not_run():
        raise AssertionError("import preflight ran without OTEL_CONFIG_FILE")

    monkeypatch.setattr(
        configurator_module, "_declarative_config_import_error", _must_not_run
    )

    Dash0Configurator().configure()

    assert len(_record_sdk_configure) == 1


def test_declarative_config_import_error_is_none_or_actionable():
    # Environment-dependent: None when the declarative-configuration
    # dependencies are installed, otherwise a message naming what to install.
    result = _declarative_config_import_error()

    assert result is None or "install" in result.lower()
