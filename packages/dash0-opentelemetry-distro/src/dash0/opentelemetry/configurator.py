"""SDK configurator for the Dash0 OpenTelemetry distribution.

Registered as the single ``opentelemetry_configurator`` entry point of this
distribution. Because the Dash0 distribution does not ship the upstream
``opentelemetry-distro`` package, it must supply the configurator itself instead
of relying on the one that package provides.

It currently reuses the OpenTelemetry SDK configurator unchanged. It exists as an
explicit Dash0 type so the entry point targets a stable symbol and so
distribution-specific SDK defaults (resource detectors, samplers, ...) have a
home to grow into.
"""

from opentelemetry.sdk._configuration import _OTelSDKConfigurator


class Dash0Configurator(_OTelSDKConfigurator):
    """Configure the OpenTelemetry SDK for the Dash0 distribution."""
