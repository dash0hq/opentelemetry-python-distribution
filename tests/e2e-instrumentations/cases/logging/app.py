"""Exercise the log pipeline and exit.

The application configures no OpenTelemetry handler of its own. A record
reaching the sink therefore proves the distribution attached one to the root
logger, and the span around the call is what gives the record a trace context
to carry.
"""

from logging import INFO, basicConfig, getLogger

from opentelemetry.trace import get_tracer

logger = getLogger(__name__)


def main() -> None:
    basicConfig(level=INFO)
    with get_tracer(__name__).start_as_current_span("handle-request"):
        logger.info("handled request for item %s", 7)


main()
