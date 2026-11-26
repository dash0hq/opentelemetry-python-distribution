"""Run one instrumentation case under ``opentelemetry-instrument``."""

from os import execvp

from sink_gate import announce_ready_then_wait_for_the_sink

announce_ready_then_wait_for_the_sink()

execvp(
    "opentelemetry-instrument",
    ["opentelemetry-instrument", "python", "/app/app.py"],
)
