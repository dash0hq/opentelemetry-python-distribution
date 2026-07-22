"""Fail when a package changed but its released version was not bumped.

Published artifacts are immutable: the release workflow skips building any
package whose wheel filename already appears in ``scripts/index-manifest.json``
(see ``build_simple_index.py``). Without this check, a code change merged
without a version bump would be *silently* skipped at release time — the run
goes green while consumers keep resolving the old bytes.

Compares the working tree against a base ref (default ``origin/main``): any
package whose *packaged* files changed (anything under the package directory
except ``tests/`` — ``src/``, ``pyproject.toml``, and metadata files such as
``README.rst`` that the wheel bundles into its long description) while its
current-version wheel is already in the manifest must bump its version
(vendored packages: ``.postN``; the distro: semver).

Runs on Python >= 3.11 (tomllib) with git on the PATH.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _workspace import package_version, workspace_packages

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "scripts" / "index-manifest.json"


def package_changed(package_dir: Path, changed: set[str]) -> bool:
    """Whether any file that ships in the package's wheel changed since base.

    The wheel bundles ``pyproject.toml``, ``src/``, and metadata files at the
    package root — notably ``README.rst``, referenced by ``[project].readme``,
    which becomes the long description in the wheel METADATA. ``tests/`` is
    excluded because it does not ship. Checking ``src/``/``pyproject.toml``
    alone missed metadata edits, letting a changed-but-not-bumped package be
    silently skipped at release time under an already-published filename.
    """
    prefix = f"{package_dir.relative_to(REPO_ROOT)}/"
    tests_prefix = f"{prefix}tests/"
    return any(
        path.startswith(prefix) and not path.startswith(tests_prefix)
        for path in changed
    )


def wheel_filename(name: str, version: str) -> str:
    return f"{name.replace('-', '_')}-{version}-py3-none-any.whl"


def violations(
    packages: dict[str, tuple[str, bool]], manifest: dict[str, str]
) -> list[str]:
    """``packages`` maps name -> (version, changed-since-base)."""
    problems = []
    for name, (version, changed) in sorted(packages.items()):
        if changed and wheel_filename(name, version) in manifest:
            problems.append(
                f"{name} changed but version {version} is already published; "
                f"bump the version (and the distro's == pin on it, if any)"
            )
    return problems


def changed_paths(base: str) -> set[str]:
    output = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {line for line in output.splitlines() if line}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args(argv)

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    if not manifest:
        print("manifest is empty; nothing has been published yet")
        return 0

    changed = changed_paths(args.base)
    packages = {
        name: (package_version(package_dir), package_changed(package_dir, changed))
        for name, package_dir in workspace_packages().items()
    }

    problems = violations(packages, manifest)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
