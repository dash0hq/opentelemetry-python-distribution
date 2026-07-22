import os

import pytest
from dash0.opentelemetry._environment_variables import (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_PROTOCOL,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL,
    OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
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
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
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
    # All signals share the HTTP endpoint; no per-signal endpoints are needed
    # (the HTTP exporter appends the signal path to the shared endpoint itself).
    assert OTEL_EXPORTER_OTLP_TRACES_ENDPOINT not in os.environ
    assert OTEL_EXPORTER_OTLP_METRICS_ENDPOINT not in os.environ
    assert OTEL_EXPORTER_OTLP_LOGS_ENDPOINT not in os.environ


def test_configure_selects_pyproto_grpc_for_grpc_protocol(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4317")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_PROTOCOL, "grpc")

    Dash0Distro().configure()

    assert os.environ[OTEL_TRACES_EXPORTER] == "otlp_proto_grpc"
    assert os.environ[OTEL_METRICS_EXPORTER] == "otlp_proto_grpc"
    assert os.environ[OTEL_LOGS_EXPORTER] == "otlp_proto_grpc"
    assert os.environ[OTEL_EXPORTER_OTLP_PROTOCOL] == "grpc"
    # Base URL already carries the gRPC port; the shared endpoint serves every
    # signal, so no per-signal endpoints are derived.
    assert OTEL_EXPORTER_OTLP_TRACES_ENDPOINT not in os.environ
    assert OTEL_EXPORTER_OTLP_METRICS_ENDPOINT not in os.environ
    assert OTEL_EXPORTER_OTLP_LOGS_ENDPOINT not in os.environ


def test_configure_honors_per_signal_protocol_overrides(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_TRACES_PROTOCOL, "grpc")

    Dash0Distro().configure()

    assert os.environ[OTEL_TRACES_EXPORTER] == "otlp_proto_grpc"
    assert os.environ[OTEL_METRICS_EXPORTER] == "otlp_proto_http"
    assert os.environ[OTEL_LOGS_EXPORTER] == "otlp_proto_http"
    # The gRPC trace signal cannot use the shared HTTP-port endpoint: it gets a
    # per-signal endpoint with the port rewritten to the gRPC default (4317).
    # The HTTP metrics/logs signals keep using the shared endpoint (4318).
    assert os.environ[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT] == "http://collector:4317"
    assert OTEL_EXPORTER_OTLP_METRICS_ENDPOINT not in os.environ
    assert OTEL_EXPORTER_OTLP_LOGS_ENDPOINT not in os.environ


def test_configure_derives_http_per_signal_endpoint_from_grpc_base(monkeypatch):
    # Base URL carries the gRPC port (4317) and all signals default to gRPC, but
    # metrics is overridden to HTTP: metrics must be rewritten to the HTTP port
    # (4318) with the signal path appended, while traces/logs stay on the shared
    # gRPC endpoint.
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4317")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_PROTOCOL, "grpc")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_METRICS_PROTOCOL, "http/protobuf")

    Dash0Distro().configure()

    assert os.environ[OTEL_METRICS_EXPORTER] == "otlp_proto_http"
    assert (
        os.environ[OTEL_EXPORTER_OTLP_METRICS_ENDPOINT]
        == "http://collector:4318/v1/metrics"
    )
    assert OTEL_EXPORTER_OTLP_TRACES_ENDPOINT not in os.environ
    assert OTEL_EXPORTER_OTLP_LOGS_ENDPOINT not in os.environ


def test_configure_heals_uniform_grpc_on_http_port_base(monkeypatch):
    # Endpoint derivation is not limited to mixed protocols: with every signal
    # on gRPC but the base URL carrying the HTTP default port, each signal gets
    # a per-signal endpoint rewritten to the gRPC port instead of silently
    # failing against 4318.
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_PROTOCOL, "grpc")

    Dash0Distro().configure()

    assert os.environ[OTEL_EXPORTER_OTLP_ENDPOINT] == "http://collector:4318"
    assert os.environ[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT] == "http://collector:4317"
    assert os.environ[OTEL_EXPORTER_OTLP_METRICS_ENDPOINT] == "http://collector:4317"
    assert os.environ[OTEL_EXPORTER_OTLP_LOGS_ENDPOINT] == "http://collector:4317"


def test_configure_heals_uniform_http_on_grpc_port_base(monkeypatch):
    # Same healing in the other direction: all signals on the default HTTP
    # protocol against a gRPC-port base URL get per-signal HTTP endpoints (port
    # rewritten, signal path appended).
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4317")

    Dash0Distro().configure()

    assert os.environ[OTEL_EXPORTER_OTLP_ENDPOINT] == "http://collector:4317"
    assert (
        os.environ[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT]
        == "http://collector:4318/v1/traces"
    )
    assert (
        os.environ[OTEL_EXPORTER_OTLP_METRICS_ENDPOINT]
        == "http://collector:4318/v1/metrics"
    )
    assert (
        os.environ[OTEL_EXPORTER_OTLP_LOGS_ENDPOINT] == "http://collector:4318/v1/logs"
    )


def test_configure_leaves_custom_port_untouched(monkeypatch):
    # A non-default port is assumed to serve the requested protocol (e.g. a
    # gateway), so no port rewriting happens even for a mixed protocol.
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:9999")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_TRACES_PROTOCOL, "grpc")

    Dash0Distro().configure()

    assert os.environ[OTEL_EXPORTER_OTLP_ENDPOINT] == "http://collector:9999"
    assert OTEL_EXPORTER_OTLP_TRACES_ENDPOINT not in os.environ
    assert OTEL_EXPORTER_OTLP_METRICS_ENDPOINT not in os.environ


def test_configure_does_not_override_explicit_per_signal_endpoint(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_TRACES_PROTOCOL, "grpc")
    monkeypatch.setenv(OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, "http://sidecar:12345")

    Dash0Distro().configure()

    # A user-provided per-signal endpoint wins over the derived one.
    assert os.environ[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT] == "http://sidecar:12345"


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


@pytest.mark.parametrize(
    "base_endpoint,protocol,signal_path,expected",
    [
        # Matching / default-port cases need no override.
        ("http://collector:4318", "http/protobuf", "v1/traces", None),
        ("http://collector:4317", "grpc", "v1/traces", None),
        # gRPC signal on an HTTP-port base URL: rewrite port, no path.
        ("http://collector:4318", "grpc", "v1/traces", "http://collector:4317"),
        # HTTP signal on a gRPC-port base URL: rewrite port and append the path.
        (
            "http://collector:4317",
            "http/protobuf",
            "v1/metrics",
            "http://collector:4318/v1/metrics",
        ),
        # Trailing slash: the path is appended without doubling the separator.
        (
            "http://collector:4317/",
            "http/protobuf",
            "v1/logs",
            "http://collector:4318/v1/logs",
        ),
        # IPv6 literal keeps its brackets around the rewritten port.
        ("http://[::1]:4318", "grpc", "v1/traces", "http://[::1]:4317"),
        # Custom and absent ports are left alone.
        ("http://collector:9999", "grpc", "v1/traces", None),
        ("http://collector", "grpc", "v1/traces", None),
    ],
)
def test_per_signal_endpoint_override(base_endpoint, protocol, signal_path, expected):
    from dash0.opentelemetry.distro import _per_signal_endpoint_override

    assert (
        _per_signal_endpoint_override(base_endpoint, protocol, signal_path) == expected
    )
