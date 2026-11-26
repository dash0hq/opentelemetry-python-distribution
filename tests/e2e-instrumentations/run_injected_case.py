"""Run one instrumentation case through the injected tree, the way a consumer does."""

from os import environ, execvp

from sink_gate import announce_ready_then_wait_for_the_sink

INJECTED_TREE: str = "/dash0"

announce_ready_then_wait_for_the_sink()

environ["PYTHONPATH"] = INJECTED_TREE

execvp("python", ["python", "/app/app.py"])
