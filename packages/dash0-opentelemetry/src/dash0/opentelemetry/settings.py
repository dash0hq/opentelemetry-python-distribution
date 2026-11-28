"""Enablement gate for the Dash0 distribution.

Mirrors the two hard gates the Node.js distribution checks before doing
anything: an explicit kill switch, and a required collector endpoint (there is
no point instrumenting if there is nowhere to send the telemetry). The endpoint
checked is the one the SDK will export to, which is ``OTEL_EXPORTER_OTLP_ENDPOINT``
when the user set it, and an endpoint whose URL or whose port ``urlparse``
rejects counts as no endpoint at all. A per-signal endpoint the user set is
checked the same way, because it is the endpoint its own signal exports to.
"""

from os import environ
from urllib.parse import urlparse

from ._environment_variables import (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
)

_PER_SIGNAL_ENDPOINTS = (
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
)


def is_true(value):
    return value is not None and value.strip().lower() == "true"


def is_false(value):
    return value is not None and value.strip().lower() == "false"


def evaluate_gate():
    """Return ``(enabled, reason)``.

    ``reason`` is a human-readable explanation when disabled, else ``None``.
    """
    if is_true(environ.get(DASH0_DISABLE)):
        return False, f"{DASH0_DISABLE} is set to true"
    base_url = environ.get(DASH0_OTEL_COLLECTOR_BASE_URL)
    if not base_url:
        return False, f"{DASH0_OTEL_COLLECTOR_BASE_URL} is not set"
    override = environ.get(OTEL_EXPORTER_OTLP_ENDPOINT)
    shared_variable = (
        OTEL_EXPORTER_OTLP_ENDPOINT if override else DASH0_OTEL_COLLECTOR_BASE_URL
    )
    endpoints = [(shared_variable, override or base_url)]
    endpoints += [
        (variable, environ[variable])
        for variable in _PER_SIGNAL_ENDPOINTS
        if environ.get(variable)
    ]
    for variable, endpoint in endpoints:
        try:
            _ = urlparse(endpoint).port
        except ValueError as error:
            return False, f"{variable} cannot be parsed: {error}"
    return True, None
