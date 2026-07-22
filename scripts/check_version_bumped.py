"""Fail when a package changed but its released version was not bumped.

Published artifacts are immutable: the release workflow skips building any
package whose wheel filename already appears in ``scripts/index-manifest.json``
(see ``build_simple_index.py``). Without this check, a code change merged
without a version bump would be *silently* skipped at release time — the run
goes green while consumers keep resolving the old bytes.

Compares the working tree against a base ref (default ``origin/main``): any
package whose ``src/`` or ``pyproject.toml`` changed while its current-version
wheel is already in the manifest must bump its version (vendored packages:
``.postN``; the distro: semver).

Runs on Python >= 3.11 (tomllib) with git on the PATH.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "scripts" / "index-manifest.json"


def workspace_packages() -> dict[str, Path]:
    """Map of distribution name -> package directory, from packages/*."""
    packages = {}
    for pyproject in sorted(REPO_ROOT.glob("packages/*/pyproject.toml")):
        data = tomllib.loads(pyproject.read_text())
        packages[data["project"]["name"]] = pyproject.parent
    return packages


def package_version(package_dir: Path) -> str:
    data = tomllib.loads((package_dir / "pyproject.toml").read_text())
    version_file = package_dir / data["tool"]["hatch"]["version"]["path"]
    return re.search(r'__version__ = "([^"]+)"', version_file.read_text()).group(1)


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
    packages = {}
    for name, package_dir in workspace_packages().items():
        relative = package_dir.relative_to(REPO_ROOT)
        package_changed = any(
            path == f"{relative}/pyproject.toml" or path.startswith(f"{relative}/src/")
            for path in changed
        )
        packages[name] = (package_version(package_dir), package_changed)

    problems = violations(packages, manifest)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
