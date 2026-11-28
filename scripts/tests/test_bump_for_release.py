"""Unit tests for the release version-bump helper."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bump_for_release as bfr  # noqa: E402
from tomllib import loads  # noqa: E402


def test_accepts_plain_release_versions():
    for version in [
        "0.3.0",
        "1.44.0",
        "10.20.30",
        "0.3.0a1",
        "0.3.0b2",
        "0.3.0rc1",
        "1.44.0.post1",
    ]:
        assert bfr.is_valid_distro_version(version), version


def test_rejects_leading_v_and_malformed_versions():
    for version in [
        "v0.3.0",  # the exact bug that stalled the 0.3.0 release
        "vv0.3.0",
        "",
        "0.3",
        "0.3.0.post",
        "0.3.0-rc1",
        "release-0.3.0",
        "0.3.0 ",
    ]:
        assert not bfr.is_valid_distro_version(version), version


def test_write_pin_leaves_the_toml_parseable(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        "dependencies = [\n"
        '  "dash0-opentelemetry-pyproto == 1.44.0.post1",\n'
        "]\n"
    )
    bfr.write_pin(pyproject, "dash0-opentelemetry-pyproto", "1.44.0.post2")
    assert loads(pyproject.read_text())["project"]["dependencies"] == [
        "dash0-opentelemetry-pyproto == 1.44.0.post2"
    ]
    assert bfr.read_pin(pyproject, "dash0-opentelemetry-pyproto") == "1.44.0.post2"
