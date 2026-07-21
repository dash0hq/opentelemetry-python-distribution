import os

import pytest
from dash0.opentelemetry._environment_variables import (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_PROTOCOL,
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL,
    OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
    OTEL_LOGS_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_SDK_DISABLED,
    OTEL_TRACES_EXPORTER,
)
from dash0.opentelemetry.distro import Dash0Distro

_MANAGED_VARS = (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_TRACES_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_LOGS_EXPORTER,
    OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL,
    OTEL_EXPORTER_OTLP_LOGS_PROTOCOL,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_SDK_DISABLED,
)


class _FakeEntryPoint:
    def __init__(self, name, instrumentor_factory):
        self.name = name
        self._instrumentor_factory = instrumentor_factory

    def load(self):
        return self._instrumentor_factory


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for variable in _MANAGED_VARS:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "")


def test_configure_enabled_defaults_to_pyproto_http(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")

    Dash0Distro().configure()

    assert os.environ[OTEL_TRACES_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_METRICS_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_LOGS_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_EXPORTER_OTLP_PROTOCOL] == "http/protobuf"
    assert os.environ[OTEL_EXPORTER_OTLP_ENDPOINT] == "http://collector:4318"


def test_configure_selects_pyproto_grpc_for_grpc_protocol(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4317")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_PROTOCOL, "grpc")

    Dash0Distro().configure()

    assert os.environ[OTEL_TRACES_EXPORTER] == "otlp_proto_grpc"
    assert os.environ[OTEL_METRICS_EXPORTER] == "otlp_proto_grpc"
    assert os.environ[OTEL_LOGS_EXPORTER] == "otlp_proto_grpc"
    assert os.environ[OTEL_EXPORTER_OTLP_PROTOCOL] == "grpc"


def test_configure_honors_per_signal_protocol_overrides(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_TRACES_PROTOCOL, "grpc")

    Dash0Distro().configure()

    assert os.environ[OTEL_TRACES_EXPORTER] == "otlp_proto_grpc"
    assert os.environ[OTEL_METRICS_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_LOGS_EXPORTER] == "otlp_proto_http"


def test_configure_falls_back_to_http_for_unsupported_protocol(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_PROTOCOL, "http/json")

    Dash0Distro().configure()

    assert os.environ[OTEL_TRACES_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_METRICS_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_LOGS_EXPORTER] == "otlp_proto_http"


def test_configure_does_not_override_explicit_configuration(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, "console")

    Dash0Distro().configure()

    assert os.environ[OTEL_TRACES_EXPORTER] == "console"


def test_configure_disabled_by_flag(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(DASH0_DISABLE, "true")

    Dash0Distro().configure()

    assert os.environ[OTEL_SDK_DISABLED] == "true"
    assert OTEL_TRACES_EXPORTER not in os.environ


def test_configure_disabled_when_no_collector_endpoint():
    Dash0Distro().configure()

    assert os.environ[OTEL_SDK_DISABLED] == "true"
    assert OTEL_TRACES_EXPORTER not in os.environ


def test_load_instrumentor_isolates_failures(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")

    def _raise_on_instantiation():
        raise RuntimeError("incompatible library version")

    # Must not propagate: the auto-instrumentation loader re-raises generic
    # exceptions, which would abort instrumentation of the whole process.
    Dash0Distro().load_instrumentor(_FakeEntryPoint("broken", _raise_on_instantiation))


def test_load_instrumentor_skips_when_disabled():
    def _must_not_run():
        raise AssertionError("instrumentor loaded while distribution disabled")

    # Distribution is disabled (no collector endpoint) → load_instrumentor is a
    # no-op and never touches the entry point.
    Dash0Distro().load_instrumentor(_FakeEntryPoint("any", _must_not_run))
