import pytest
from dash0.opentelemetry import settings as settings_module
from dash0.opentelemetry._environment_variables import (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_LOGS_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_TRACES_EXPORTER,
)
from dash0.opentelemetry.settings import evaluate_gate, is_false, is_true
from opentelemetry.sdk.environment_variables import OTEL_CONFIG_FILE


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(OTEL_CONFIG_FILE, raising=False)
    monkeypatch.delenv(DASH0_DISABLE, raising=False)
    monkeypatch.delenv(DASH0_OTEL_COLLECTOR_BASE_URL, raising=False)
    monkeypatch.delenv(OTEL_EXPORTER_OTLP_ENDPOINT, raising=False)
    monkeypatch.delenv(OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, raising=False)
    monkeypatch.delenv(OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, raising=False)
    monkeypatch.delenv(OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, raising=False)
    monkeypatch.delenv(OTEL_LOGS_EXPORTER, raising=False)
    monkeypatch.delenv(OTEL_METRICS_EXPORTER, raising=False)
    monkeypatch.delenv(OTEL_TRACES_EXPORTER, raising=False)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("TRUE", True),
        (" True ", True),
        ("false", False),
        ("", False),
        (None, False),
    ],
)
def test_is_true(value, expected):
    assert is_true(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("false", True),
        ("FALSE", True),
        (" False ", True),
        ("true", False),
        ("", False),
        (None, False),
    ],
)
def test_is_false(value, expected):
    assert is_false(value) is expected


def test_gate_enabled_when_endpoint_set_and_not_disabled(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None


def test_gate_disabled_by_flag(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(DASH0_DISABLE, "true")

    enabled, reason = evaluate_gate()

    assert enabled is False
    assert DASH0_DISABLE in reason


def test_gate_disabled_without_endpoint():
    enabled, reason = evaluate_gate()

    assert enabled is False
    assert DASH0_OTEL_COLLECTOR_BASE_URL in reason


def test_gate_disabled_by_an_endpoint_urlparse_rejects(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://[::1:4318")

    enabled, reason = evaluate_gate()

    assert enabled is False
    assert DASH0_OTEL_COLLECTOR_BASE_URL in reason
    assert "Invalid IPv6 URL" in reason


def test_a_valid_override_survives_a_base_url_urlparse_rejects(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://[::1:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_ENDPOINT, "http://collector:4318")

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None


def test_gate_disabled_by_an_override_urlparse_rejects(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_ENDPOINT, "http://[::1:4318")

    enabled, reason = evaluate_gate()

    assert enabled is False
    assert OTEL_EXPORTER_OTLP_ENDPOINT in reason


@pytest.mark.parametrize(
    "endpoint", ["http://collector:notaport", "http://collector:70000"]
)
def test_gate_enabled_by_an_endpoint_whose_port_urlparse_cannot_read(
    monkeypatch, endpoint
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, endpoint)

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None


@pytest.mark.parametrize(
    "endpoint", ["http://collector:notaport", "http://collector:70000"]
)
def test_gate_enabled_by_a_per_signal_endpoint_whose_port_urlparse_cannot_read(
    monkeypatch, endpoint
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, endpoint)

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None


def test_gate_enabled_by_an_endpoint_with_no_port(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector")

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None


@pytest.mark.parametrize(
    "variable",
    [
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
        OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    ],
)
def test_gate_disabled_by_a_per_signal_endpoint_urlparse_rejects(monkeypatch, variable):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(variable, "http://[::1:4318")

    enabled, reason = evaluate_gate()

    assert enabled is False
    assert variable in reason
    assert "Invalid IPv6 URL" in reason


@pytest.mark.parametrize("exporter", ["none", "console", ""])
def test_gate_enabled_when_the_signal_of_a_rejected_endpoint_skips_otlp(
    monkeypatch, exporter
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_LOGS_EXPORTER, exporter)
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, "http://[::1:4318")

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None


@pytest.mark.parametrize("exporter", ["otlp", "otlp_proto_http", "otlp,console"])
def test_gate_disabled_when_the_signal_of_a_rejected_endpoint_uses_otlp(
    monkeypatch, exporter
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_LOGS_EXPORTER, exporter)
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, "http://[::1:4318")

    enabled, reason = evaluate_gate()

    assert enabled is False
    assert OTEL_EXPORTER_OTLP_LOGS_ENDPOINT in reason


@pytest.mark.parametrize(
    "variable",
    [DASH0_OTEL_COLLECTOR_BASE_URL, OTEL_EXPORTER_OTLP_TRACES_ENDPOINT],
)
def test_gate_enabled_by_a_rejected_endpoint_under_an_explicit_config_file(
    monkeypatch, tmp_path, variable
):
    config_file = tmp_path / "otel-config.yaml"
    config_file.write_text('file_format: "1.0"\n')
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(variable, "http://[::1:4318")
    monkeypatch.setenv(OTEL_CONFIG_FILE, str(config_file))

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None


def test_gate_enabled_by_a_rejected_endpoint_under_the_default_config_file(
    monkeypatch, tmp_path
):
    config_file = tmp_path / "otel-config.yaml"
    config_file.write_text('file_format: "1.0"\n')
    monkeypatch.setattr(settings_module, "_DEFAULT_CONFIG_FILE", str(config_file))
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, "http://[::1:4318")

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None


def test_gate_disabled_by_a_rejected_endpoint_when_the_config_file_variable_is_empty(
    monkeypatch,
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, "http://[::1:4318")
    monkeypatch.setenv(OTEL_CONFIG_FILE, "")

    enabled, reason = evaluate_gate()

    assert enabled is False
    assert OTEL_EXPORTER_OTLP_TRACES_ENDPOINT in reason


@pytest.mark.parametrize("exporter", ["console", "none"])
def test_gate_enabled_by_a_rejected_base_url_when_no_signal_uses_otlp(
    monkeypatch, exporter
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://[::1:4318")
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, exporter)
    monkeypatch.setenv(OTEL_METRICS_EXPORTER, exporter)
    monkeypatch.setenv(OTEL_LOGS_EXPORTER, exporter)

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None


def test_gate_disabled_by_a_rejected_base_url_when_one_signal_still_uses_otlp(
    monkeypatch,
):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://[::1:4318")
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, "console")
    monkeypatch.setenv(OTEL_METRICS_EXPORTER, "console")
    monkeypatch.setenv(OTEL_LOGS_EXPORTER, "otlp")

    enabled, reason = evaluate_gate()

    assert enabled is False
    assert DASH0_OTEL_COLLECTOR_BASE_URL in reason


def test_gate_enabled_by_per_signal_endpoints_that_parse(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, "http://collector:4317")
    monkeypatch.setenv(
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, "http://collector:4318/v1/metrics"
    )
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, "http://[::1]:4318/v1/logs")

    enabled, reason = evaluate_gate()

    assert enabled is True
    assert reason is None
