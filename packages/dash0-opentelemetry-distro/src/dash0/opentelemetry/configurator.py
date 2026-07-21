"""SDK configurator for the Dash0 OpenTelemetry distribution.

Registered as the single ``opentelemetry_configurator`` entry point. It runs
after :class:`~dash0.opentelemetry.distro.Dash0Distro` has set the environment,
so it lets the standard OpenTelemetry SDK configurator build the providers,
exporters and Resource from that environment (or from a declarative
configuration file when ``OTEL_CONFIG_FILE`` is set), then adds two Dash0
behaviors from the Node.js distribution: an optional startup ("bootstrap") span
and optional graceful flushing on SIGTERM/SIGINT.

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


def _declarative_config_import_error():
    """Return why declarative configuration cannot be loaded, or ``None``.

    The SDK version this distribution pins bundles the ``OTEL_CONFIG_FILE``
    loader in ``opentelemetry.sdk._configuration.file`` behind the
    ``opentelemetry-sdk[file-configuration]`` extra (pyyaml, jsonschema), which
    a plain install does not pull in. Without this preflight the SDK
    configurator fails with a raw traceback and the process runs without any
    telemetry. Revisit when bumping the pinned SDK: from 1.44 the loader lives
    in the separate ``opentelemetry-configuration`` package instead.
    """
    try:
        # pylint: disable=import-outside-toplevel,unused-import
        import opentelemetry.sdk._configuration.file._loader  # noqa: F401

        return None
    except ImportError as error:
        # The loader's own message names the extra to install.
        return str(error)


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

        if environ.get(OTEL_CONFIG_FILE):
            import_error = _declarative_config_import_error()
            if import_error:
                _logger.error(
                    "%s is set but the declarative-configuration dependencies "
                    "are not installed: %s. The SDK will not be configured and "
                    "no telemetry will be sent.",
                    OTEL_CONFIG_FILE,
                    import_error,
                )
                return

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
