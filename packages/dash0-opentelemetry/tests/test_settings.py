import pytest
from dash0.opentelemetry._environment_variables import (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
)
from dash0.opentelemetry.settings import evaluate_gate, is_false, is_true


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(DASH0_DISABLE, raising=False)
    monkeypatch.delenv(DASH0_OTEL_COLLECTOR_BASE_URL, raising=False)


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
