"""Enforce the distribution's dependency policy (see its README).

The distro ships a curated set of upstream packages, so every dependency in
``packages/dash0-opentelemetry/pyproject.toml`` must be pinned to an
exact version (``== X.Y.Z``). Two exemptions:

* uv workspace members (the in-repo pyproto packages): their version is fixed
  by the workspace checkout, not by PyPI resolution;
* optional-dependency entries whose package is already pinned exactly in the
  base dependencies (e.g. an extra that re-references the SDK to pull in one of
  its extras);
* the names in ``EXEMPT_FROM_EXACT_PIN``, which must be declared with exactly
  the specifier that table gives, and often that is none at all. Every
  specifier reaches the injector's conflict check (``sitecustomize.py``)
  through ``all-dependencies.txt``, and one violated line stands the whole
  distro down, so for a package that is both common in applications and
  dependency-free an unbounded requirement is usually the safer choice. A
  bound belongs there only when the versions it excludes cannot work at all,
  where standing down beats failing inside the package. Each entry records
  which case it is and why.

Additionally, the pyproject file must spell out the distro's *entire* installed
tree: every package the distro pulls in transitively (per ``uv export`` over
the lock file) must itself appear in ``dependencies`` with an exact pin, so no
version in the injected tree is left to transitive resolution.

Runs on Python >= 3.11 (tomllib) with uv on the PATH. Exits non-zero listing
every violation.
"""

import re
import subprocess
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
DISTRO_PYPROJECT = ROOT / "packages" / "dash0-opentelemetry" / "pyproject.toml"

EXEMPT_FROM_EXACT_PIN = {
    "pyyaml": (
        ">=5.1",
        "read by dash0-opentelemetry-configuration to parse OTEL_CONFIG_FILE. "
        "pyyaml has no dependencies of its own, so it is left unbounded above "
        "and whatever version the application already has is used. It is "
        "bounded below because pyyaml 3.10 through 3.13 call "
        "collections.Hashable in yaml/constructor.py, an alias Python 3.10 "
        "removed, so safe_load raises AttributeError on any mapping, which is "
        "every real configuration file. Those releases declare no "
        "requires-python, so nothing but this floor stops pip installing them "
        "on an interpreter they cannot work on. 5.1 is the first stable "
        "release after the last broken one, with only prereleases in between.",
    ),
}

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


def _normalize(name):
    # PEP 503 normalization, so pyproject spellings match uv's.
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse(requirement):
    match = _REQUIREMENT.match(requirement.split(";", 1)[0])
    if match is None:
        return None, None
    return _normalize(match.group("name")), match.group("specifier")


def _distro_closure():
    """The distro's resolved transitive closure, from the lock file.

    Returns ``{normalized name: version}`` for every non-workspace package a
    plain install of the distro pulls in.
    """
    result = subprocess.run(
        [
            "uv",
            "export",
            "--package",
            "dash0-opentelemetry",
            "--frozen",
            "--no-dev",
            "--no-hashes",
            "--no-annotate",
            "--no-header",
            "--no-emit-workspace",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    closure = {}
    for line in result.stdout.splitlines():
        line = line.split(";", 1)[0].strip()
        if not line or line.startswith(("#", "-")):
            continue
        name, _, version = line.partition("==")
        closure[_normalize(name.strip())] = version.strip()
    return closure


def _is_exact_pin(specifier):
    return _EXACT_PIN.match(specifier) is not None and not specifier.endswith(".*")


def policy_violations(project, workspace_members, closure):
    """Every way ``project`` breaks the dependency policy, as a list of strings.

    ``project`` is the ``[project]`` table of the distro's pyproject file,
    ``workspace_members`` the normalized names of the in-repo packages, and
    ``closure`` the ``{normalized name: version}`` mapping a plain install of
    the distro produces. An empty list means the policy holds.
    """
    violations = []

    pinned_in_base = {}
    exempt_from_exact_pin = set()
    for requirement in project.get("dependencies", []):
        name, specifier = _parse(requirement)
        if name is None:
            violations.append(f"dependencies: cannot parse {requirement!r}")
        elif name in workspace_members:
            continue
        elif name in EXEMPT_FROM_EXACT_PIN:
            exempt_from_exact_pin.add(name)
            required, reason = EXEMPT_FROM_EXACT_PIN[name]
            if re.sub(r"\s+", "", specifier) != required:
                expected = f"{name} {required}".strip()
                violations.append(
                    f"dependencies: {requirement!r} must be declared as "
                    f"'{expected}' and carry no other version specifier "
                    f"({reason})"
                )
        elif _is_exact_pin(specifier):
            pinned_in_base[name] = specifier.removeprefix("==").strip()
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
                or name in EXEMPT_FROM_EXACT_PIN
                or _is_exact_pin(specifier)
            ):
                continue
            else:
                violations.append(
                    f"[{extra}]: {requirement!r} is neither pinned to an exact "
                    f"version nor covered by an exact pin in dependencies"
                )

    for name, version in sorted(closure.items()):
        if name in exempt_from_exact_pin:
            continue
        if name not in pinned_in_base:
            violations.append(
                f"closure: {name} == {version} is pulled in transitively but "
                f"not declared in dependencies (declare it with an exact pin)"
            )
        elif pinned_in_base[name] != version:
            violations.append(
                f"closure: {name} resolves to {version} but dependencies pins "
                f"{pinned_in_base[name]}"
            )

    return violations


def main():
    with open(DISTRO_PYPROJECT, "rb") as file:
        project = tomllib.load(file)["project"]

    violations = policy_violations(
        project,
        {_normalize(member) for member in _workspace_members()},
        _distro_closure(),
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

    print(
        "All distribution dependencies are pinned exactly and the full "
        "transitive closure is declared."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
