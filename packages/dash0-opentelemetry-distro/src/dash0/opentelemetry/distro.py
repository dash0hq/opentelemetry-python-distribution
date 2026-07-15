"""Dash0 OpenTelemetry distribution.

Provides :class:`Dash0Distro`, the ``opentelemetry_distro`` entry point activated
by ``opentelemetry-instrument`` when the Dash0 distribution is installed. It runs
before the configurator, so it is where the distribution:

* gates itself off if disabled or if no collector endpoint is configured;
* selects the pure-Python OTLP/HTTP exporter (no native dependencies, safe to
  inject) and points it at the Dash0 collector;
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
    OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_LOGS_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_SDK_DISABLED,
    OTEL_TRACES_EXPORTER,
)
from .resource import apply_detected_resource_attributes
from .settings import evaluate_gate
from .version import __version__

_logger = getLogger(__name__)

# Name under which the pure-Python OTLP/HTTP exporter registers itself. In an
# injected tree only the pyproto exporter ships under this name, so it resolves
# to the pure-Python implementation rather than the protobuf/grpc one.
_PYPROTO_HTTP_EXPORTER = "otlp_proto_http"

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

        for exporter_variable in (
            OTEL_TRACES_EXPORTER,
            OTEL_METRICS_EXPORTER,
            OTEL_LOGS_EXPORTER,
        ):
            environ.setdefault(exporter_variable, _PYPROTO_HTTP_EXPORTER)
        environ.setdefault(OTEL_EXPORTER_OTLP_PROTOCOL, "http/protobuf")
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
