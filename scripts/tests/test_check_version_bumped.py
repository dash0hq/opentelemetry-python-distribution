"""Unit tests for the released-version bump check."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_version_bumped as cvb  # noqa: E402

WHEEL = "dash0_opentelemetry_pyproto-1.44.0-py3-none-any.whl"


def test_changed_package_with_published_version_is_a_violation():
    problems = cvb.violations(
        {"dash0-opentelemetry-pyproto": ("1.44.0", True)},
        {WHEEL: "a" * 64},
    )
    assert len(problems) == 1
    assert "bump the version" in problems[0]


def test_bumped_or_unchanged_packages_pass():
    manifest = {WHEEL: "a" * 64}
    assert (
        cvb.violations(
            {"dash0-opentelemetry-pyproto": ("1.44.0.post1", True)}, manifest
        )
        == []
    )
    assert (
        cvb.violations({"dash0-opentelemetry-pyproto": ("1.44.0", False)}, manifest)
        == []
    )


def test_workspace_discovery_matches_expected_packages():
    names = set(cvb.workspace_packages())
    assert names == {
        "dash0-opentelemetry-distro",
        "dash0-opentelemetry-pyproto",
        "dash0-opentelemetry-exporter-otlp-pyproto-common",
        "dash0-opentelemetry-exporter-otlp-pyproto-http",
        "dash0-opentelemetry-exporter-otlp-pyproto-grpc",
    }
    for name, package_dir in cvb.workspace_packages().items():
        version = cvb.package_version(package_dir)
        assert version[0].isdigit(), (name, version)


def test_package_changed_counts_packaged_files_but_not_tests():
    pkg = cvb.REPO_ROOT / "packages" / "some-pkg"
    assert cvb.package_changed(pkg, {"packages/some-pkg/README.rst"})
    assert cvb.package_changed(pkg, {"packages/some-pkg/src/mod.py"})
    assert cvb.package_changed(pkg, {"packages/some-pkg/pyproject.toml"})
    assert not cvb.package_changed(pkg, {"packages/some-pkg/tests/test_mod.py"})
    # A trailing slash on the prefix keeps a sibling package from matching.
    assert not cvb.package_changed(pkg, {"packages/some-pkg-other/README.rst"})
