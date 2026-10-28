"""Unit tests for the dependency policy check."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_pinned_dependencies import (  # noqa: E402
    EXEMPT_FROM_EXACT_PIN,
    policy_violations,
)

WORKSPACE = {"dash0-opentelemetry-pyproto"}


def violations_for(dependencies, closure=None):
    return policy_violations({"dependencies": dependencies}, WORKSPACE, closure or {})


def test_an_exact_pin_satisfies_the_policy():
    assert violations_for(["psutil == 7.2.2"]) == []


def test_a_range_is_rejected_for_a_name_with_no_exemption():
    problems = violations_for(["psutil >= 7.2.2"])
    assert len(problems) == 1
    assert "not pinned to an exact version" in problems[0]


def test_a_workspace_member_needs_no_pin():
    assert violations_for(["dash0-opentelemetry-pyproto"]) == []


def test_an_exempt_name_must_carry_the_specifier_the_table_gives():
    required, _ = EXEMPT_FROM_EXACT_PIN["pyyaml"]
    assert violations_for([f"pyyaml {required}"]) == []


def test_an_exempt_name_without_its_specifier_is_rejected():
    problems = violations_for(["pyyaml"])
    assert len(problems) == 1
    assert "must be declared as 'pyyaml >=5.1'" in problems[0]


def test_an_exempt_name_with_a_different_specifier_is_rejected():
    problems = violations_for(["pyyaml == 6.0.3"])
    assert len(problems) == 1
    assert "must be declared as 'pyyaml >=5.1'" in problems[0]


def test_whitespace_in_the_declared_specifier_does_not_matter():
    assert violations_for(["pyyaml>=5.1"]) == []
    assert violations_for(["pyyaml  >=  5.1"]) == []


def test_the_rejection_message_carries_the_reason_from_the_table():
    _, reason = EXEMPT_FROM_EXACT_PIN["pyyaml"]
    assert reason in violations_for(["pyyaml"])[0]


def test_an_exempt_name_is_skipped_by_the_closure_check():
    assert violations_for(["pyyaml >=5.1"], {"pyyaml": "6.0.3"}) == []


def test_a_closure_entry_missing_from_dependencies_is_a_violation():
    problems = violations_for([], {"psutil": "7.2.2"})
    assert len(problems) == 1
    assert "pulled in transitively" in problems[0]


def test_a_closure_entry_resolving_away_from_its_pin_is_a_violation():
    problems = violations_for(["psutil == 7.2.1"], {"psutil": "7.2.2"})
    assert len(problems) == 1
    assert "resolves to 7.2.2" in problems[0]
