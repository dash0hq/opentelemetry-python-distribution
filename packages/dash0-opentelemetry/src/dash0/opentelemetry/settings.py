"""Enablement gate for the Dash0 distribution.

Mirrors the two hard gates the Node.js distribution checks before doing
anything: an explicit kill switch, and a required collector endpoint (there is
no point instrumenting if there is nowhere to send the telemetry). An endpoint
``urlparse`` rejects is treated as no endpoint at all.
"""

from os import environ
from urllib.parse import urlparse

from ._environment_variables import (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
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
    try:
        urlparse(base_url)
    except ValueError as error:
        return False, f"{DASH0_OTEL_COLLECTOR_BASE_URL} cannot be parsed: {error}"
    return True, None
