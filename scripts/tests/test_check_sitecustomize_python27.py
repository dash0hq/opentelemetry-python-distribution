"""Unit tests for the Python 2.7 warn-and-continue contract check."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_sitecustomize_python27 as csp  # noqa: E402

COMPLIANT_OUTPUT = (
    '{"level": "warn", "message": "cannot auto-instrument Python process: '
    "unsupported Python version: 2.7.18 (default, Apr 20 2020, 19:27:10) \n"
    '[GCC 8.3.0]", "logger_name": "dash0", '
    '"dash0.monitoring.telemetry_collection_issue": true}\n'
    "application-ran\n"
)


def test_compliant_output_passes():
    assert csp.problems(0, 0, COMPLIANT_OUTPUT) == []


def test_compile_failure_is_reported():
    problems = csp.problems(1, 0, COMPLIANT_OUTPUT)
    assert any("byte-compile" in problem for problem in problems)


def test_nonzero_application_exit_is_reported():
    problems = csp.problems(0, 1, COMPLIANT_OUTPUT)
    assert any("exited with 1" in problem for problem in problems)


def test_missing_warning_is_reported():
    problems = csp.problems(0, 0, "application-ran\n")
    assert any("warning was not logged" in problem for problem in problems)


def test_missing_application_output_is_reported():
    # A SyntaxError in sitecustomize.py does not stop the interpreter, so the
    # exit code alone cannot catch the pre-fix regression of issue #36; the
    # 'import sitecustomize' failed marker and the warn message do.
    pre_fix_output = (
        "'import sitecustomize' failed; use -v for traceback\napplication-ran\n"
    )
    problems = csp.problems(0, 0, pre_fix_output)
    assert any("rejected sitecustomize.py" in problem for problem in problems)
    assert any("warning was not logged" in problem for problem in problems)


def test_missing_sentinel_is_reported():
    problems = csp.problems(0, 0, "")
    assert any("application did not run" in problem for problem in problems)
