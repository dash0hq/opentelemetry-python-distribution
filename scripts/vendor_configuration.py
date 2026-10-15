"""Regenerate ``packages/dash0-opentelemetry-configuration`` from the fork.

The declarative-configuration code is not written here. It lives on the
``dash0`` branch of https://github.com/dash0hq/opentelemetry-python, which
carries the Dash0 patches as commits on top of an upstream commit so they can
be rebased when upstream moves. This script is the only thing that turns that
branch into a package in this workspace, which is what keeps the two in step:
a change made here by hand is lost on the next run, and CI fails if the
checked-in tree is not what this script produces.

What it generates, all of which is therefore not to be edited by hand:

* ``src/opentelemetry/_configuration/``, copied from the fork with every
  ``opentelemetry.configuration`` reference rewritten to
  ``opentelemetry._configuration``. The distribution ships the implementation
  at a path upstream does not own, the same arrangement the pyproto exporter
  packages use, so that installing it beside a future published
  ``opentelemetry-configuration`` cannot collide file for file.
* ``src/opentelemetry/configuration/``, star re-export shims at the path the
  SDK imports. ``opentelemetry/sdk/_configuration/__init__.py`` imports
  ``opentelemetry.configuration`` by name, so the shims are what make
  ``OTEL_CONFIG_FILE`` work at all.
* ``pyproject.toml``, whose ``opentelemetry-api`` and ``opentelemetry-sdk``
  pins are copied from the distribution's own pins rather than written twice.

Two files inside the package are deliberately left alone. ``README.rst``
describes the vendoring for a reader of this repository, and
``src/opentelemetry/_configuration/version/__init__.py`` holds the released
version, which ``scripts/bump_for_release.py`` advances through ``.postN``.

Usage::

    python3 scripts/vendor_configuration.py
    python3 scripts/vendor_configuration.py --commit <sha>
    python3 scripts/vendor_configuration.py --check

``--commit`` re-points ``UPSTREAM`` at a new fork commit, which is what to run
after rebasing the ``dash0`` branch. ``--check`` regenerates into a scratch
directory and reports what differs without writing anything.

Runs on Python >= 3.11 (tomllib) with git on the PATH.
"""

from argparse import ArgumentParser, Namespace
from filecmp import dircmp
from pathlib import Path
from re import MULTILINE, search
from shutil import copytree, rmtree
from subprocess import run
from sys import exit as sys_exit
from tempfile import TemporaryDirectory

from tomllib import loads

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
PACKAGE: Path = REPO_ROOT / "packages" / "dash0-opentelemetry-configuration"
UPSTREAM: Path = PACKAGE / "UPSTREAM"
DISTRO_PYPROJECT: Path = (
    REPO_ROOT / "packages" / "dash0-opentelemetry" / "pyproject.toml"
)

PUBLIC_PATH: str = "opentelemetry.configuration"
PRIVATE_PATH: str = "opentelemetry._configuration"

LICENSE_HEADER: str = (
    "# Copyright The OpenTelemetry Authors\n# SPDX-License-Identifier: Apache-2.0\n"
)

PYPROJECT_TEMPLATE: str = """[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "dash0-opentelemetry-configuration"
dynamic = ["version"]
description = "Declarative configuration for the Dash0 OpenTelemetry distribution"
readme = "README.rst"
license = "Apache-2.0"
requires-python = ">=3.10"
dependencies = [
  "opentelemetry-api == {api_version}",
  "opentelemetry-sdk == {sdk_version}",
  "pyyaml",
]

[tool.hatch.version]
path = "src/opentelemetry/_configuration/version/__init__.py"

[tool.hatch.build.targets.sdist]
include = ["/src"]

[tool.hatch.build.targets.wheel]
packages = ["src/opentelemetry"]

[tool.pytest.ini_options]
testpaths = ["tests"]
"""


def read_upstream() -> dict[str, str]:
    """Parse ``UPSTREAM``'s ``key = value`` lines."""
    fields: dict[str, str] = {}
    for line in UPSTREAM.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip()
    return fields


def distro_pin(name: str) -> str:
    """The exact version the distribution pins ``name`` to."""
    project = loads(DISTRO_PYPROJECT.read_text())["project"]
    for requirement in project["dependencies"]:
        match = search(rf"^{name}\s*==\s*(\S+)$", requirement.strip())
        if match is not None:
            return match.group(1)
    raise SystemExit(f"{DISTRO_PYPROJECT} does not pin {name} exactly")


def generate(source: Path, destination: Path) -> None:
    """Write the whole generated part of the package into ``destination``."""
    private = destination / "src" / "opentelemetry" / "_configuration"
    private.parent.mkdir(parents=True, exist_ok=True)
    copytree(source, private)

    for path in private.rglob("*.py"):
        path.write_text(path.read_text().replace(PUBLIC_PATH, PRIVATE_PATH))

    public = destination / "src" / "opentelemetry" / "configuration"
    for module in sorted(private.rglob("*.py")):
        relative = module.relative_to(private)
        if any(part.startswith("_") for part in relative.parts[:-1]):
            continue
        if relative.name.startswith("_") and relative.name != "__init__.py":
            continue

        target = public / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        dotted = ".".join(
            (PRIVATE_PATH, *relative.parts[:-1], relative.stem)
        ).removesuffix(".__init__")
        lines = [LICENSE_HEADER, f"\nfrom {dotted} import *  # noqa: F403\n"]
        if search(r"^__all__", module.read_text(), MULTILINE):
            lines.append(f"from {dotted} import __all__  # noqa: F401\n")
        target.write_text("".join(lines))

    (destination / "pyproject.toml").write_text(
        PYPROJECT_TEMPLATE.format(
            api_version=distro_pin("opentelemetry-api"),
            sdk_version=distro_pin("opentelemetry-sdk"),
        )
    )


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--commit", help="re-point UPSTREAM at this fork commit")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report differences instead of writing",
    )
    arguments: Namespace = parser.parse_args()

    fields = read_upstream()
    commit: str = arguments.commit or fields["commit"]

    with TemporaryDirectory() as scratch:
        clone = Path(scratch) / "fork"
        run(["git", "init", "--quiet", str(clone)], check=True)
        run(
            ["git", "remote", "add", "origin", fields["repository"]],
            cwd=clone,
            check=True,
        )
        run(
            ["git", "fetch", "--quiet", "--depth", "1", "origin", commit],
            cwd=clone,
            check=True,
        )
        run(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=clone, check=True)

        source = clone / fields["source"]
        if not source.is_dir():
            print(f"{fields['source']} does not exist at {commit}")
            return 1

        staged = Path(scratch) / "staged"
        generate(source, staged)

        if arguments.check:
            differences = compare(staged, PACKAGE)
            for difference in differences:
                print(f"  {difference}")
            if differences:
                print(
                    f"{len(differences)} path(s) differ from what "
                    f"{Path(__file__).name} generates at {commit[:12]}; "
                    f"re-run it instead of editing the package by hand."
                )
                return 1
            print(f"the vendored package matches the fork at {commit[:12]}")
            return 0

        version_file = (
            PACKAGE
            / "src"
            / "opentelemetry"
            / "_configuration"
            / "version"
            / "__init__.py"
        )
        released_version = version_file.read_text() if version_file.exists() else None

        rmtree(PACKAGE / "src" / "opentelemetry", ignore_errors=True)
        copytree(staged / "src", PACKAGE / "src", dirs_exist_ok=True)
        (PACKAGE / "pyproject.toml").write_text((staged / "pyproject.toml").read_text())
        if released_version is not None:
            version_file.write_text(released_version)

    UPSTREAM.write_text(
        f"repository = {fields['repository']}\n"
        f"branch = {fields['branch']}\n"
        f"commit = {commit}\n"
        f"source = {fields['source']}\n"
    )
    print(f"vendored {fields['source']} from {fields['repository']} at {commit[:12]}")
    return 0


def compare(expected: Path, actual: Path) -> list[str]:
    """Paths that differ between the generated tree and the checked-in one."""
    differences: list[str] = []

    def walk(comparison: dircmp, prefix: Path) -> None:
        for name in comparison.left_only:
            differences.append(f"missing from the package: {prefix / name}")
        for name in comparison.right_only:
            differences.append(f"not generated, remove it: {prefix / name}")
        for name in comparison.diff_files:
            differences.append(f"differs: {prefix / name}")
        for name, sub in comparison.subdirs.items():
            walk(sub, prefix / name)

    for relative in ("src/opentelemetry", "pyproject.toml"):
        left, right = expected / relative, actual / relative
        if left.is_dir():
            walk(dircmp(left, right, ignore=["__pycache__", "version"]), Path(relative))
        elif left.read_text() != right.read_text():
            differences.append(f"differs: {relative}")
    return differences


if __name__ == "__main__":
    sys_exit(main())
