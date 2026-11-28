import pytest
from dash0.opentelemetry._environment_variables import (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
)
from dash0.opentelemetry.settings import evaluate_gate, is_false, is_true


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(DASH0_DISABLE, raising=False)
    monkeypatch.delenv(DASH0_OTEL_COLLECTOR_BASE_URL, raising=False)
    monkeypatch.delenv(OTEL_EXPORTER_OTLP_ENDPOINT, raising=False)
    monkeypatch.delenv(OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, raising=False)
    monkeypatch.delenv(OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, raising=False)
    monkeypatch.delenv(OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, raising=False)


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
