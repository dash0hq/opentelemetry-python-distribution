"""Check that the injector bootstrap script degrades gracefully on Python 2.7.

The OpenTelemetry injector prepends the injected tree to the PYTHONPATH of any
Python process, including interpreters this distribution does not support, so
``sitecustomize.py`` must at least parse there and deactivate itself instead of
crashing the process (see the script's header and issue #36: an em-dash without
a PEP-263 encoding declaration made Python 2.7 reject the file at parse time).

Python 2.7 is the oldest interpreter the injector may reach. This check stages
the script the way consumers deploy it (alone in a directory) and, in a
``python:2.7.18`` container, verifies that:

* the file byte-compiles (``py_compile``);
* a Python 2.7 process with the directory on PYTHONPATH logs the
  "unsupported Python version" warning, self-deactivates, and keeps running.

Stdlib-only; runs on any python3 with docker on the PATH. The staging directory is
created inside the repository so the check also works on macOS, where Docker
Desktop does not share the default temporary directory (/var/folders).
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITECUSTOMIZE = (
    REPO_ROOT
    / "packages"
    / "dash0-opentelemetry"
    / "src"
    / "dash0"
    / "opentelemetry"
    / "injector"
    / "sitecustomize.py"
)

PYTHON27_IMAGE = "python:2.7.18-buster"
# Printed by the containerized application; proves the process survived the
# injected sitecustomize.py and ran its own code.
APPLICATION_SENTINEL = "application-ran"

UNSUPPORTED_VERSION_WARNING = "unsupported Python version: 2.7"
IMPORT_FAILED_MARKER = "'import sitecustomize' failed"


def problems(
    compile_returncode: int, run_returncode: int, run_output: str
) -> list[str]:
    """Violations of the warn-and-continue contract, empty when compliant."""
    found = []
    if compile_returncode != 0:
        found.append("sitecustomize.py does not byte-compile on Python 2.7")
    if run_returncode != 0:
        found.append(
            "a Python 2.7 process with sitecustomize.py on the PYTHONPATH "
            f"exited with {run_returncode}"
        )
    if UNSUPPORTED_VERSION_WARNING not in run_output:
        found.append(
            f'the expected "{UNSUPPORTED_VERSION_WARNING}" warning was not logged'
        )
    if APPLICATION_SENTINEL not in run_output:
        found.append("the application did not run after sitecustomize.py")
    if IMPORT_FAILED_MARKER in run_output:
        found.append(
            "the interpreter rejected sitecustomize.py "
            f'("{IMPORT_FAILED_MARKER}" was logged)'
        )
    return found


def docker_run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "run", "--rm", *args],
        capture_output=True,
        text=True,
    )


def main() -> int:
    site_dir = Path(tempfile.mkdtemp(prefix=".sitecustomize-python27-", dir=REPO_ROOT))
    try:
        shutil.copy(SITECUSTOMIZE, site_dir)
        volume = f"{site_dir}:/agents"

        compile_result = docker_run(
            "-v",
            volume,
            PYTHON27_IMAGE,
            "python",
            "-m",
            "py_compile",
            "/agents/sitecustomize.py",
        )
        run_result = docker_run(
            "-v",
            volume,
            "-e",
            "PYTHONPATH=/agents",
            PYTHON27_IMAGE,
            "python",
            "-c",
            f"print('{APPLICATION_SENTINEL}')",
        )
    finally:
        shutil.rmtree(site_dir)

    run_output = run_result.stdout + run_result.stderr
    print(compile_result.stderr, end="", file=sys.stderr)
    print(run_output, end="")

    found = problems(compile_result.returncode, run_result.returncode, run_output)
    for problem in found:
        print(f"FAIL: {problem}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
