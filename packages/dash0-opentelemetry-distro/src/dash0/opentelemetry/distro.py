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

from opentelemetry.instrumentation.distro import BaseDistro

from ._environment_variables import (
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
from .resource import apply_detected_resource_attributes
from .settings import evaluate_gate
from .version import __version__

_logger = getLogger(__name__)

# Entry-point names under which the pure-Python (pyproto) exporters register
# themselves, keyed by OTLP protocol. In an injected tree only the pyproto
# exporters ship under these names, so they resolve to the pure-Python
# implementations rather than the protobuf/grpcio ones.
_PYPROTO_EXPORTERS_BY_PROTOCOL = {
    "http/protobuf": "otlp_proto_http",
    "grpc": "otlp_proto_grpc",
}

_DEFAULT_PROTOCOL = "http/protobuf"

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
        for exporter_variable, protocol_variable in (
            (OTEL_TRACES_EXPORTER, OTEL_EXPORTER_OTLP_TRACES_PROTOCOL),
            (OTEL_METRICS_EXPORTER, OTEL_EXPORTER_OTLP_METRICS_PROTOCOL),
            (OTEL_LOGS_EXPORTER, OTEL_EXPORTER_OTLP_LOGS_PROTOCOL),
        ):
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
                exporter = _PYPROTO_EXPORTERS_BY_PROTOCOL[_DEFAULT_PROTOCOL]
            environ.setdefault(exporter_variable, exporter)
        environ.setdefault(
            OTEL_EXPORTER_OTLP_ENDPOINT,
            environ[DASH0_OTEL_COLLECTOR_BASE_URL],
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
