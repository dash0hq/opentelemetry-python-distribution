import os

from opentelemetry.environment_variables import (
    OTEL_LOGS_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_TRACES_EXPORTER,
)
from opentelemetry.sdk.environment_variables import OTEL_EXPORTER_OTLP_PROTOCOL

from dash0.opentelemetry import distro as distro_module
from dash0.opentelemetry.distro import Dash0Distro


class _FakeEntryPoint:
    def __init__(self, name, instrumentor_factory):
        self.name = name
        self._instrumentor_factory = instrumentor_factory

    def load(self):
        return self._instrumentor_factory


def test_configure_defaults_to_pyproto_http_for_all_signals(monkeypatch):
    for variable in (
        OTEL_TRACES_EXPORTER,
        OTEL_METRICS_EXPORTER,
        OTEL_LOGS_EXPORTER,
        OTEL_EXPORTER_OTLP_PROTOCOL,
    ):
        monkeypatch.delenv(variable, raising=False)

    Dash0Distro().configure()

    assert os.environ[OTEL_TRACES_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_METRICS_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_LOGS_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_EXPORTER_OTLP_PROTOCOL] == "http/protobuf"


def test_configure_does_not_override_explicit_configuration(monkeypatch):
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, "console")

    Dash0Distro().configure()

    assert os.environ[OTEL_TRACES_EXPORTER] == "console"


def test_load_instrumentor_skips_disabled(monkeypatch):
    monkeypatch.setattr(
        distro_module, "_DISABLED_INSTRUMENTORS", frozenset({"noisy"})
    )

    def _must_not_run():
        raise AssertionError("disabled instrumentor was loaded")

    Dash0Distro().load_instrumentor(_FakeEntryPoint("noisy", _must_not_run))


def test_load_instrumentor_isolates_failures():
    def _raise_on_load():
        raise RuntimeError("incompatible library version")

    entry_point = _FakeEntryPoint("broken", _raise_on_load)

    # Must not propagate: a broken instrumentor may not abort auto-instrumentation
    # of an injected process.
    Dash0Distro().load_instrumentor(entry_point)
