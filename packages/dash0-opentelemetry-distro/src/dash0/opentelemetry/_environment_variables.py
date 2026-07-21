"""Environment variables read and written by the Dash0 distribution.

Grouped here so the distro, the configurator and the resource detection share a
single definition of each name.
"""

# --- Dash0-specific knobs (mirrors the Node.js distribution) ---

DASH0_DISABLE = "DASH0_DISABLE"
"""When set to ``true`` the distribution does nothing at all."""

DASH0_OTEL_COLLECTOR_BASE_URL = "DASH0_OTEL_COLLECTOR_BASE_URL"
"""Base URL of the collector to export to. Required; without it the
distribution disables itself, because there is nowhere to send telemetry."""

DASH0_AUTOMATIC_SERVICE_NAME = "DASH0_AUTOMATIC_SERVICE_NAME"
"""Set to ``false`` to opt out of deriving a fallback ``service.name``."""

DASH0_BOOTSTRAP_SPAN = "DASH0_BOOTSTRAP_SPAN"
"""When set, a single span with this name is emitted once at startup."""

DASH0_FLUSH_ON_SIGTERM_SIGINT = "DASH0_FLUSH_ON_SIGTERM_SIGINT"
"""Set to ``true`` to flush telemetry on SIGTERM/SIGINT before exiting."""


# --- Standard OpenTelemetry variables the distribution defaults ---

OTEL_TRACES_EXPORTER = "OTEL_TRACES_EXPORTER"
OTEL_METRICS_EXPORTER = "OTEL_METRICS_EXPORTER"
OTEL_LOGS_EXPORTER = "OTEL_LOGS_EXPORTER"
OTEL_EXPORTER_OTLP_PROTOCOL = "OTEL_EXPORTER_OTLP_PROTOCOL"
OTEL_EXPORTER_OTLP_TRACES_PROTOCOL = "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"
OTEL_EXPORTER_OTLP_METRICS_PROTOCOL = "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL"
OTEL_EXPORTER_OTLP_LOGS_PROTOCOL = "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL"
OTEL_EXPORTER_OTLP_ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"
OTEL_SERVICE_NAME = "OTEL_SERVICE_NAME"
OTEL_RESOURCE_ATTRIBUTES = "OTEL_RESOURCE_ATTRIBUTES"
OTEL_SDK_DISABLED = "OTEL_SDK_DISABLED"
OTEL_CONFIG_FILE = "OTEL_CONFIG_FILE"
