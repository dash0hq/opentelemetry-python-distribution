"""SDK configurator for the Dash0 OpenTelemetry distribution.

Registered as the single ``opentelemetry_configurator`` entry point. It runs
after :class:`~dash0.opentelemetry.distro.Dash0Distro` has set the environment,
so it lets the standard OpenTelemetry SDK configurator build the providers,
exporters and Resource from that environment, then adds two Dash0 behaviors from
the Node.js distribution: an optional startup ("bootstrap") span and optional
graceful flushing on SIGTERM/SIGINT.

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
)
from .settings import evaluate_gate, is_true

_logger = getLogger(__name__)


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
