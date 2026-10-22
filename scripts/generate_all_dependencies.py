"""Generate ``all-dependencies.txt`` for an injected tree.

The injector bootstrap (``sitecustomize.py``) reads this file and compares every
line against what the *application* has installed. A line the application
violates stands the whole distribution down: it removes itself from
``PYTHONPATH`` for the process and its children, and the application reports no
telemetry at all.

What each line has to say is therefore narrow. The bootstrap puts the injected
tree *last* on ``sys.path`` (see the ``path.append`` in ``import_distro``), so
the application's copy of a shared package already wins at import time. The
distribution never shadows it. The only question left is whether the
distribution's own code works against the version the application brought, and
the packages of the tree already answer that in their ``Requires-Dist``
metadata.

So a line carries the conjunction of what the tree declares about that package,
not the version the tree happens to contain. For ``wrapt`` that is
``<3.0.0,>=1.0.0`` and friends rather than ``==1.17.3``, which is what
``opentelemetry-instrumentation`` itself says it supports. Emitting the
installed version instead rejects versions upstream declares compatible, and
silently turns off the distribution for an application that pinned any of them.

Some declarations are deliberately ignored: the exact pins the distribution's
own packages make. ``packages/dash0-opentelemetry/pyproject.toml`` pins every
dependency to one version, which is a statement about the set Dash0 validated
and builds from, rather than a statement about what the code can run against.
Carrying those pins into the manifest would reproduce exactly the behaviour
this script exists to stop. A declaration made by a distribution whose name
starts with ``--curated-prefix`` (``dash0-`` by default) is therefore skipped
when it admits a single version, as ``==1.44.0`` and ``===1.0`` do.

Every other declaration those same packages make is kept, because a range is a
compatibility statement whoever wrote it. The three vendored pyproto exporters
say ``opentelemetry-sdk~=1.12``, which is their own account of the SDK versions
they work against. Dropping it would leave ``opentelemetry-sdk`` with no
constraint at all, since every distribution of the tree that declares it
carries the curated prefix.

A package nothing else in the tree depends on gets a bare name with no
specifier, so no version of it can stand the distribution down. That is what
makes the ``UNPINNED_BY_DESIGN`` table in ``scripts/check_pinned_dependencies.py``
actually reach the bootstrap: ``pyyaml`` is required only by the distribution's
own packages, so it comes out unconstrained.

Requirements gated on an extra are skipped, because the extra may not be
installed. Environment markers are carried through on their own line rather
than evaluated here: generation happens on a build machine, evaluation happens
in the application's interpreter, and the two can disagree. The bootstrap
evaluates the marker itself and skips the line when it does not apply.

Usage::

    python scripts/generate_all_dependencies.py <tree-dir> [-o <output>]

``<tree-dir>`` is a directory produced by ``pip install --target``. With no
``-o`` the manifest goes to stdout.
"""

from argparse import ArgumentParser
from collections import defaultdict
from email.parser import Parser as EmailParser
from pathlib import Path
from re import sub as re_sub
from sys import stdout

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


def normalize(name: str) -> str:
    """Return the PEP 503 normalized form of a distribution name."""
    return re_sub(r"[-_.]+", "-", name).lower()


def pins_one_version(specifier: SpecifierSet) -> bool:
    """Say whether a specifier set admits at most one version.

    True for ``==1.44.0`` and for ``===1.0``, and for a set holding either of
    them alongside anything else, since the conjunction is then no wider than
    the pin. False for a set with no clauses at all, and for every range,
    including the prefix match ``==1.44.*``, which admits a whole series.
    """
    return any(
        clause.operator == "==="
        or (clause.operator == "==" and not clause.version.endswith(".*"))
        for clause in specifier
    )


def read_tree(
    tree: Path, curated_prefix: str = "dash0-"
) -> tuple[set[str], dict[str, set[tuple[str, str | None]]]]:
    """Read every ``.dist-info`` of an installed tree.

    Returns the set of normalized names the tree contains, and a mapping from
    normalized name to the ``(specifier, marker)`` pairs the tree declares about
    it. ``marker`` is ``None`` for a requirement with no environment marker.
    Requirements gated on an extra are left out, and so is every requirement
    that pins one version and is declared by a distribution whose normalized
    name starts with ``curated_prefix``.
    """
    installed: set[str] = set()
    demands: dict[str, set[tuple[str, str | None]]] = defaultdict(set)

    for metadata_path in sorted(tree.glob("*.dist-info/METADATA")):
        metadata = EmailParser().parsestr(
            metadata_path.read_text(encoding="utf-8", errors="replace")
        )
        name = metadata.get("Name")
        if not name:
            raise ValueError(f"{metadata_path} has no Name header")
        installed.add(normalize(name))
        curated = normalize(name).startswith(curated_prefix)

        for raw in metadata.get_all("Requires-Dist") or []:
            try:
                requirement = Requirement(raw)
            except Exception:
                continue
            marker = str(requirement.marker) if requirement.marker else None
            if marker and "extra ==" in marker:
                continue
            if curated and pins_one_version(requirement.specifier):
                continue
            demands[normalize(requirement.name)].add(
                (str(requirement.specifier), marker)
            )

    return installed, demands


def manifest_lines(
    installed: set[str], demands: dict[str, set[tuple[str, str | None]]]
) -> list[str]:
    """Build the manifest, one PEP 508 requirement per line, sorted by name."""
    lines: list[str] = []
    for name in sorted(installed):
        pairs = demands.get(name, set())

        unmarked = [specifier for specifier, marker in pairs if marker is None]
        lines.append(name + str(SpecifierSet(",".join(filter(None, unmarked)))))

        for marker in sorted({marker for _, marker in pairs if marker is not None}):
            clauses = [
                specifier
                for specifier, requirement_marker in pairs
                if requirement_marker == marker
            ]
            joined = str(SpecifierSet(",".join(filter(None, clauses))))
            lines.append(f"{name}{joined}; {marker}")

    return lines


def main() -> int:
    parser = ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tree", type=Path, help="directory from pip install --target")
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument(
        "--curated-prefix",
        default="dash0-",
        help="ignore exact pins declared by distributions whose normalized "
        "name starts with this; such a pin curates the build rather than "
        "describing what the code supports. Ranges they declare are kept",
    )
    arguments = parser.parse_args()

    if not arguments.tree.is_dir():
        parser.error(f"{arguments.tree} is not a directory")

    installed, demands = read_tree(arguments.tree, arguments.curated_prefix)
    if not installed:
        parser.error(f"{arguments.tree} holds no .dist-info directories")

    text = "\n".join(manifest_lines(installed, demands)) + "\n"
    if arguments.output is None:
        stdout.write(text)
    else:
        arguments.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
