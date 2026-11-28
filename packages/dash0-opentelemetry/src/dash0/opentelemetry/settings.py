"""Enablement gate for the Dash0 distribution.

Mirrors the two hard gates the Node.js distribution checks before doing
anything: an explicit kill switch, and a required collector endpoint (there is
no point instrumenting if there is nowhere to send the telemetry). The endpoint
checked is the one the SDK will export to, which is ``OTEL_EXPORTER_OTLP_ENDPOINT``
when the user set it, and an endpoint ``urlparse`` rejects counts as no endpoint
at all. A per-signal endpoint the user set is checked the same way, because it
is the endpoint its own signal exports to, and is skipped when that signal's
exporter is not an OTLP one, because then nothing ever parses it. Every endpoint
is skipped under declarative configuration, which builds its exporters from the
configuration file and reads none of these variables.
"""

from os import environ
from os.path import isfile
from urllib.parse import urlparse

from opentelemetry.sdk.environment_variables import OTEL_CONFIG_FILE

from ._environment_variables import (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_LOGS_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_TRACES_EXPORTER,
)

_PER_SIGNAL_ENDPOINTS = (
    (OTEL_TRACES_EXPORTER, OTEL_EXPORTER_OTLP_TRACES_ENDPOINT),
    (OTEL_METRICS_EXPORTER, OTEL_EXPORTER_OTLP_METRICS_ENDPOINT),
    (OTEL_LOGS_EXPORTER, OTEL_EXPORTER_OTLP_LOGS_ENDPOINT),
)

_OTLP_EXPORTER_NAMES = frozenset({"otlp", "otlp_proto_grpc", "otlp_proto_http"})

_DEFAULT_CONFIG_FILE = "/etc/opentelemetry/python/otel-config.yaml"


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
    if environ.get(OTEL_CONFIG_FILE) or isfile(_DEFAULT_CONFIG_FILE):
        return True, None
    override = environ.get(OTEL_EXPORTER_OTLP_ENDPOINT)
    shared_variable = (
        OTEL_EXPORTER_OTLP_ENDPOINT if override else DASH0_OTEL_COLLECTOR_BASE_URL
    )
    endpoints = [(shared_variable, override or base_url)]
    for exporter_variable, endpoint_variable in _PER_SIGNAL_ENDPOINTS:
        endpoint = environ.get(endpoint_variable)
        selected = environ.get(exporter_variable)
        exports_over_otlp = selected is None or any(
            name.strip() in _OTLP_EXPORTER_NAMES for name in selected.split(",")
        )
        if endpoint and exports_over_otlp:
            endpoints.append((endpoint_variable, endpoint))
    for variable, endpoint in endpoints:
        try:
            urlparse(endpoint)
        except ValueError as error:
            return False, f"{variable} cannot be parsed: {error}"
    return True, None
