"""Enforce the distribution's dependency policy (see its README).

The distro ships a curated set of upstream packages, so every dependency in
``packages/dash0-opentelemetry-distro/pyproject.toml`` must be pinned to an
exact version (``== X.Y.Z``). Two exemptions:

* uv workspace members (the in-repo pyproto packages): their version is fixed
  by the workspace checkout, not by PyPI resolution;
* optional-dependency entries whose package is already pinned exactly in the
  base dependencies (e.g. an extra that re-references the SDK to pull in one of
  its extras).

Runs on Python >= 3.11 (tomllib), stdlib only. Exits non-zero listing every
violation.
"""

import re
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
DISTRO_PYPROJECT = ROOT / "packages" / "dash0-opentelemetry-distro" / "pyproject.toml"

# name, optional [extras], remainder (version specifier); the environment
# marker (after ';') is split off before matching.
_REQUIREMENT = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?P<specifier>.*?)\s*$"
)

# Exactly one '== <version>' clause; '==1.*' wildcards are ranges in disguise.
_EXACT_PIN = re.compile(r"^==\s*[^,\s]+$")


def _workspace_members():
    with open(ROOT / "pyproject.toml", "rb") as file:
        workspace = tomllib.load(file)
    sources = workspace.get("tool", {}).get("uv", {}).get("sources", {})
    return {
        name
        for name, source in sources.items()
        if isinstance(source, dict) and source.get("workspace")
    }


def _parse(requirement):
    match = _REQUIREMENT.match(requirement.split(";", 1)[0])
    if match is None:
        return None, None
    return match.group("name"), match.group("specifier")


def _is_exact_pin(specifier):
    return _EXACT_PIN.match(specifier) is not None and not specifier.endswith(".*")


def main():
    with open(DISTRO_PYPROJECT, "rb") as file:
        project = tomllib.load(file)["project"]

    workspace_members = _workspace_members()
    violations = []

    pinned_in_base = set()
    for requirement in project.get("dependencies", []):
        name, specifier = _parse(requirement)
        if name is None:
            violations.append(f"dependencies: cannot parse {requirement!r}")
        elif name in workspace_members:
            continue
        elif _is_exact_pin(specifier):
            pinned_in_base.add(name)
        else:
            violations.append(
                f"dependencies: {requirement!r} is not pinned to an exact "
                f"version (expected '{name} == <version>')"
            )

    for extra, requirements in project.get("optional-dependencies", {}).items():
        for requirement in requirements:
            name, specifier = _parse(requirement)
            if name is None:
                violations.append(f"[{extra}]: cannot parse {requirement!r}")
            elif (
                name in workspace_members
                or name in pinned_in_base
                or _is_exact_pin(specifier)
            ):
                continue
            else:
                violations.append(
                    f"[{extra}]: {requirement!r} is neither pinned to an exact "
                    f"version nor covered by an exact pin in dependencies"
                )

    if violations:
        print(f"{DISTRO_PYPROJECT.relative_to(ROOT)} violates the dependency policy:")
        for violation in violations:
            print(f"  - {violation}")
        print(
            "The distribution ships a curated set of upstream packages; "
            "pin every dependency exactly (see the package README)."
        )
        return 1

    print("All distribution dependencies are pinned exactly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
