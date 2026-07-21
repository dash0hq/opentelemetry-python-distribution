"""SDK configurator for the Dash0 OpenTelemetry distribution.

Registered as the single ``opentelemetry_configurator`` entry point. It runs
after :class:`~dash0.opentelemetry.distro.Dash0Distro` has set the environment,
so it lets the standard OpenTelemetry SDK configurator build the providers,
exporters and Resource from that environment, then adds two Dash0 behaviors from
the Node.js distribution: an optional startup ("bootstrap") span and optional
graceful flushing on SIGTERM/SIGINT.

When ``OTEL_CONFIG_FILE`` is set, declarative configuration takes over and
ignores the resource environment variables the distro populated. In that case
this configurator loads the config file itself and adds the distro's resource
detectors to it, so ``telemetry.distro.*``, ``k8s.pod.uid`` and the fallback
``service.name`` survive (see :func:`_add_dash0_resource_detectors`).

Normal-exit flushing is already handled by the SDK: the tracer/meter/logger
providers register ``atexit`` shutdown hooks. The signal handling below covers
container termination, where ``atexit`` does not run by default.
"""

import signal
from logging import getLogger
from os import environ, getpid, kill

from opentelemetry import _logs, metrics, trace
from opentelemetry.sdk._configuration import _OTelSDKConfigurator

from ._environment_variables import (
    DASH0_BOOTSTRAP_SPAN,
    DASH0_FLUSH_ON_SIGTERM_SIGINT,
    OTEL_CONFIG_FILE,
)
from .settings import evaluate_gate, is_true

_logger = getLogger(__name__)

# Entry-point names under which the detectors in resource.py are registered in
# the ``opentelemetry_resource_detector`` group (see pyproject.toml).
_DASH0_RESOURCE_DETECTORS = (
    "dash0_distribution",
    "dash0_kubernetes",
    "dash0_service_name",
)


def _load_declarative_machinery():
    """Return ``(load_config_file, configure_sdk, models)``.

    SDK 1.44+ ships declarative configuration as the standalone
    ``opentelemetry-configuration`` package; on SDK 1.43 it lives inside the
    SDK, behind the ``file-configuration`` extra. Raises ``ImportError`` when
    neither is available.
    """
    try:
        from opentelemetry.configuration import (
            configure_sdk,
            load_config_file,
            models,
        )
    except ImportError:
        from opentelemetry.sdk._configuration import models
        from opentelemetry.sdk._configuration._sdk import configure_sdk
        from opentelemetry.sdk._configuration.file._loader import (
            load_config_file,
        )
    return load_config_file, configure_sdk, models


def _add_dash0_resource_detectors(config, models):
    """Add the distro's resource detectors to a parsed declarative configuration.

    Mutates ``config`` in place. Detectors already listed in the config file
    are left alone; only the missing ones are appended.
    """
    if config.resource is None:
        config.resource = models.Resource()
    if config.resource.detection_development is None:
        config.resource.detection_development = models.ExperimentalResourceDetection()
    detection = config.resource.detection_development
    if detection.detectors is None:
        detection.detectors = []
    listed = set()
    for detector in detection.detectors:
        listed.update(getattr(detector, "additional_properties", {}))
    missing = {name: None for name in _DASH0_RESOURCE_DETECTORS if name not in listed}
    if missing:
        detection.detectors.append(models.ExperimentalResourceDetector(**missing))


class Dash0Configurator(_OTelSDKConfigurator):
    """Configure the OpenTelemetry SDK for the Dash0 distribution."""

    def _configure(self, **kwargs):
        enabled, reason = evaluate_gate()
        if not enabled:
            _logger.debug(
                "Dash0 distribution disabled (%s); skipping SDK configuration",
                reason,
            )
            return

        if not self._configure_from_declarative_file():
            super()._configure(**kwargs)

        bootstrap_span_name = environ.get(DASH0_BOOTSTRAP_SPAN)
        if bootstrap_span_name:
            trace.get_tracer("dash0-python-distribution").start_span(
                bootstrap_span_name
            ).end()

        if is_true(environ.get(DASH0_FLUSH_ON_SIGTERM_SIGINT)):

            def _flush_and_reraise(signum, _frame):
                for provider in (
                    trace.get_tracer_provider(),
                    metrics.get_meter_provider(),
                    _logs.get_logger_provider(),
                ):
                    shutdown = getattr(provider, "shutdown", None)
                    if shutdown is not None:
                        try:
                            shutdown()
                        except Exception:  # pylint: disable=broad-except
                            _logger.exception("dash0: error shutting down %s", provider)
                # Restore the default disposition and re-raise so the process
                # terminates with the expected exit semantics.
                signal.signal(signum, signal.SIG_DFL)
                kill(getpid(), signum)

            try:
                signal.signal(signal.SIGTERM, _flush_and_reraise)
                signal.signal(signal.SIGINT, _flush_and_reraise)
            except ValueError:
                # signal handlers can only be installed from the main thread
                _logger.debug(
                    "dash0: not on main thread, SIGTERM/SIGINT flush not installed"
                )

    def _configure_from_declarative_file(self):
        """Apply declarative configuration with the Dash0 detector added.

        The base configurator handles ``OTEL_CONFIG_FILE`` too, but the
        declarative resource builder ignores ``OTEL_RESOURCE_ATTRIBUTES`` and
        ``OTEL_SERVICE_NAME``, so the attributes the distro injected into the
        environment would silently disappear (``telemetry.distro.*``,
        ``k8s.pod.uid``, the fallback ``service.name``). Loading the config
        file here and adding the distro's resource detectors to the parsed
        configuration keeps them, while attributes declared in the file still
        win: detected attributes merge below explicit config attributes.

        Returns ``True`` when declarative configuration was applied here, and
        ``False`` when the base configurator should run instead — either no
        config file is set, or the declarative machinery is not importable (the
        base class then reports its usual, more informative error).
        """
        config_file = environ.get(OTEL_CONFIG_FILE)
        if not config_file:
            return False
        try:
            load_config_file, configure_sdk, models = _load_declarative_machinery()
        except ImportError:
            return False
        config = load_config_file(config_file)
        try:
            _add_dash0_resource_detectors(config, models)
        except Exception:  # pylint: disable=broad-except
            # The declarative config models are experimental; if they changed
            # shape, still configure from the file rather than failing startup.
            _logger.exception(
                "dash0: could not add the Dash0 resource detectors to the "
                "declarative configuration; telemetry.distro.* and k8s.pod.uid "
                "resource attributes may be missing"
            )
        configure_sdk(config)
        return True
