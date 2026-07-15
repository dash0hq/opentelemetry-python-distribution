"""Enablement gate for the Dash0 distribution.

Mirrors the two hard gates the Node.js distribution checks before doing
anything: an explicit kill switch, and a required collector endpoint (there is
no point instrumenting if there is nowhere to send the telemetry).
"""

from os import environ

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
    if not environ.get(DASH0_OTEL_COLLECTOR_BASE_URL):
        return False, f"{DASH0_OTEL_COLLECTOR_BASE_URL} is not set"
    return True, None
