"""Run one instrumentation case, once the OTLP sink is reachable.

The sink listens on the host, and the container reaches it through a reverse
tunnel that testcontainers only establishes after the container reports ready.
A container reports ready by writing ``READY_MARKER`` to stdout. A case that
exported the moment it started would therefore export into a tunnel that does
not exist yet and lose everything it emitted, so this writes the marker, waits
for the sink's port to accept a connection, and only then hands control to the
case.
"""

from os import environ, execvp
from socket import create_connection
from time import monotonic, sleep
from urllib.parse import urlsplit

READY_MARKER: str = "instrumentation-case-runner-ready"
SINK_TIMEOUT: float = 60.0
POLL_INTERVAL: float = 0.2

endpoint = urlsplit(environ["DASH0_OTEL_COLLECTOR_BASE_URL"])
host: str | None = endpoint.hostname
port: int | None = endpoint.port
if host is None or port is None:
    raise SystemExit(
        f"DASH0_OTEL_COLLECTOR_BASE_URL has no host and port: {endpoint.geturl()}"
    )

print(READY_MARKER, flush=True)

deadline: float = monotonic() + SINK_TIMEOUT
while True:
    try:
        create_connection((host, port), timeout=1.0).close()
        break
    except OSError as unreachable:
        if monotonic() > deadline:
            raise SystemExit(
                f"the sink at {host}:{port} did not accept a connection "
                f"within {SINK_TIMEOUT} seconds"
            ) from unreachable
        sleep(POLL_INTERVAL)

execvp(
    "opentelemetry-instrument",
    ["opentelemetry-instrument", "python", "/app/app.py"],
)
