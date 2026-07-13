"""Dash0 OpenTelemetry distribution.

Provides :class:`Dash0Distro`, the ``opentelemetry_distro`` entry point activated
by ``opentelemetry-instrument`` when the Dash0 distribution is installed.

The distribution is meant to be injected into customer processes (for example by
the OpenTelemetry injector), so it does two things that matter in that context:

* it selects the pure-Python OTLP/HTTP exporter by default, which has no native
  dependencies and is therefore safe to prepend to an arbitrary process'
  ``PYTHONPATH``; and
* it activates every instrumentor defensively, so that a single instrumentor that
  fails to load cannot abort auto-instrumentation of the injected process.
"""

import os
from logging import getLogger

from opentelemetry.environment_variables import (
    OTEL_LOGS_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_TRACES_EXPORTER,
)
from opentelemetry.instrumentation.distro import BaseDistro
from opentelemetry.sdk.environment_variables import OTEL_EXPORTER_OTLP_PROTOCOL

_logger = getLogger(__name__)

# Name under which the pure-Python OTLP/HTTP exporter registers itself in the
# opentelemetry_{traces,metrics,logs}_exporter entry point groups. In an injected
# tree only the pyproto exporter ships under this name, so it resolves to the
# pure-Python implementation rather than the protobuf/grpc one.
_PYPROTO_HTTP_EXPORTER = "otlp_proto_http"

# Instrumentor entry-point names that must never be activated by this
# distribution (for example because they are too noisy or not yet supported for
# injection). Keyed by the opentelemetry_instrumentor entry-point name.
_DISABLED_INSTRUMENTORS = frozenset()


class Dash0Distro(BaseDistro):
    """OpenTelemetry distribution configured for Dash0.

    Selects the pure-Python OTLP/HTTP exporter as the default for all three
    signals and isolates instrumentor activation failures so that injected
    auto-instrumentation degrades gracefully instead of breaking the host
    process.
    """

    def _configure(self, **kwargs):
        for exporter_variable in (
            OTEL_TRACES_EXPORTER,
            OTEL_METRICS_EXPORTER,
            OTEL_LOGS_EXPORTER,
        ):
            os.environ.setdefault(exporter_variable, _PYPROTO_HTTP_EXPORTER)
        os.environ.setdefault(OTEL_EXPORTER_OTLP_PROTOCOL, "http/protobuf")

    def load_instrumentor(self, entry_point, **kwargs):
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
