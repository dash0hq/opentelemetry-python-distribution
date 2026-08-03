"""Dash0 OpenTelemetry distribution.

Provides :class:`Dash0Distro`, the ``opentelemetry_distro`` entry point activated
by ``opentelemetry-instrument`` when the Dash0 distribution is installed. It runs
before the configurator, so it is where the distribution:

* gates itself off if disabled or if no collector endpoint is configured;
* selects the pure-Python OTLP exporters (no native dependencies, safe to
  inject) matching the configured OTLP protocol — ``http/protobuf`` by
  default, ``grpc`` when requested — and points them at the Dash0 collector;
* injects the detected resource attributes (distro name/version, a fallback
  service name, and the Kubernetes pod UID) so the SDK's Resource picks them up;
* activates every instrumentor defensively, so a single failing instrumentor
  cannot abort auto-instrumentation of an injected process.

This mirrors the Dash0 Node.js distribution, adapted to Python's distro/
configurator machinery.
"""

from logging import getLogger
from os import environ
from urllib.parse import urlparse, urlunparse

from opentelemetry.instrumentation.distro import BaseDistro

from ._environment_variables import (
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
from .resource import apply_detected_resource_attributes
from .settings import evaluate_gate
from .version import __version__

_logger = getLogger(__name__)

_GRPC_PROTOCOL = "grpc"
_HTTP_PROTOCOL = "http/protobuf"

# Entry-point names under which the pure-Python (pyproto) exporters register
# themselves, keyed by OTLP protocol. In an injected tree only the pyproto
# exporters ship under these names, so they resolve to the pure-Python
# implementations rather than the protobuf/grpcio ones.
_PYPROTO_EXPORTERS_BY_PROTOCOL = {
    _HTTP_PROTOCOL: "otlp_proto_http",
    _GRPC_PROTOCOL: "otlp_proto_grpc",
}

_DEFAULT_PROTOCOL = _HTTP_PROTOCOL

# Default OTLP receiver port per protocol. OTLP/gRPC and OTLP/HTTP conventionally
# listen on different ports, so a single collector base URL cannot address both.
_OTLP_DEFAULT_PORT = {_GRPC_PROTOCOL: 4317, _HTTP_PROTOCOL: 4318}

# Per-signal wiring: the exporter-selection variable, the per-signal protocol
# override, the per-signal endpoint override, and the OTLP/HTTP export path.
_SIGNALS = (
    (
        OTEL_TRACES_EXPORTER,
        OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
        "v1/traces",
    ),
    (
        OTEL_METRICS_EXPORTER,
        OTEL_EXPORTER_OTLP_METRICS_PROTOCOL,
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
        "v1/metrics",
    ),
    (
        OTEL_LOGS_EXPORTER,
        OTEL_EXPORTER_OTLP_LOGS_PROTOCOL,
        OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
        "v1/logs",
    ),
)


def _per_signal_endpoint_override(base_endpoint, protocol, signal_path):
    """Return the per-signal endpoint a signal on ``protocol`` needs, or ``None``
    when the shared ``OTEL_EXPORTER_OTLP_ENDPOINT`` already resolves correctly.

    OTLP/gRPC (default port 4317, address used as ``host:port``) and OTLP/HTTP
    (default port 4318, signal path appended) cannot share one endpoint. When a
    signal's protocol differs from the transport ``base_endpoint`` points at —
    detected by its port being the *other* supported protocol's default — the
    port is rewritten to this protocol's default so the single Dash0 collector
    base URL still routes every signal correctly. For an HTTP signal the path is
    appended here, because the exporter appends it only to the shared endpoint,
    not to a per-signal one. A custom or absent port is left untouched (the
    collector is assumed to serve that protocol there, or the user supplies an
    explicit per-signal endpoint, which is always honored).
    """
    parsed = urlparse(base_endpoint)
    try:
        current_port = parsed.port
    except ValueError:
        return None
    other_protocol_ports = {
        port for candidate, port in _OTLP_DEFAULT_PORT.items() if candidate != protocol
    }
    if current_port not in other_protocol_ports:
        return None
    host = parsed.hostname or ""
    if ":" in host:  # bracket an IPv6 literal so the port stays unambiguous
        host = f"[{host}]"
    netloc = f"{host}:{_OTLP_DEFAULT_PORT[protocol]}"
    if "@" in parsed.netloc:  # keep userinfo credentials, verbatim
        netloc = f"{parsed.netloc.rsplit('@', 1)[0]}@{netloc}"
    path = parsed.path
    if protocol == _HTTP_PROTOCOL:
        separator = "" if path.endswith("/") else "/"
        path = path + separator + signal_path
    return urlunparse(parsed._replace(netloc=netloc, path=path))


# Instrumentor entry-point names that must never be activated by this
# distribution. Empty by default; the standard OTEL_PYTHON_DISABLED_INSTRUMENTATIONS
# variable is also honored by the auto-instrumentation loader.
_DISABLED_INSTRUMENTORS = frozenset()


class Dash0Distro(BaseDistro):
    """OpenTelemetry distribution configured for Dash0."""

    def _configure(self, **kwargs):
        enabled, reason = evaluate_gate()
        if not enabled:
            # Make the SDK a no-op so nothing is exported, matching the Node.js
            # distribution's "do nothing" behavior when disabled/misconfigured.
            environ[OTEL_SDK_DISABLED] = "true"
            _logger.warning(
                "Dash0 distribution disabled: %s. No telemetry will be sent.",
                reason,
            )
            return

        default_protocol = environ.setdefault(
            OTEL_EXPORTER_OTLP_PROTOCOL, _DEFAULT_PROTOCOL
        )
        environ.setdefault(
            OTEL_EXPORTER_OTLP_ENDPOINT,
            environ[DASH0_OTEL_COLLECTOR_BASE_URL],
        )
        # The effective shared endpoint (a user-set value is honored above), used
        # to derive per-signal endpoints when signals resolve to different OTLP
        # transports.
        base_endpoint = environ[OTEL_EXPORTER_OTLP_ENDPOINT]
        for (
            exporter_variable,
            protocol_variable,
            endpoint_variable,
            signal_path,
        ) in _SIGNALS:
            protocol = environ.get(protocol_variable, default_protocol)
            exporter = _PYPROTO_EXPORTERS_BY_PROTOCOL.get(protocol)
            if exporter is None:
                _logger.warning(
                    "dash0: unsupported OTLP protocol %r in %s; defaulting %s to"
                    " the %r exporter",
                    protocol,
                    protocol_variable
                    if protocol_variable in environ
                    else OTEL_EXPORTER_OTLP_PROTOCOL,
                    exporter_variable,
                    _PYPROTO_EXPORTERS_BY_PROTOCOL[_DEFAULT_PROTOCOL],
                )
                protocol = _DEFAULT_PROTOCOL
                exporter = _PYPROTO_EXPORTERS_BY_PROTOCOL[protocol]
            selected_exporter = environ.setdefault(exporter_variable, exporter)
            if selected_exporter != exporter:
                # The user picked this signal's exporter directly; the distro
                # cannot know which transport it speaks, so deriving an endpoint
                # from the protocol variables could redirect a working exporter
                # to the wrong port.
                continue
            signal_endpoint = _per_signal_endpoint_override(
                base_endpoint, protocol, signal_path
            )
            if signal_endpoint is not None and endpoint_variable not in environ:
                environ[endpoint_variable] = signal_endpoint
                _logger.debug(
                    "dash0: shared endpoint %r targets the other OTLP transport;"
                    " derived %s=%s for protocol %r",
                    base_endpoint,
                    endpoint_variable,
                    signal_endpoint,
                    protocol,
                )

        apply_detected_resource_attributes(__version__)

    def load_instrumentor(self, entry_point, **kwargs):
        enabled, _ = evaluate_gate()
        if not enabled:
            return
        if entry_point.name in _DISABLED_INSTRUMENTORS:
            _logger.debug(
                "dash0: instrumentor %s is disabled, skipping", entry_point.name
            )
            return
        try:
            super().load_instrumentor(entry_point, **kwargs)
        except Exception:  # pylint: disable=broad-except
            _logger.exception(
                "dash0: instrumentor %s failed to load, continuing without it",
                entry_point.name,
            )
