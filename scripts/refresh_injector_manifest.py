"""Regenerate the ``all-dependencies.txt`` the distribution wheel ships.

``sitecustomize.py`` reads ``all-dependencies.txt`` from its own directory at
interpreter startup and stands the whole distribution down when the application
violates any line of it. Until now nothing in this repository produced that
file. The DEB and RPM builds in ``dash0hq/dash0-packages`` wrote their own,
one exact pin per installed package, which is the behaviour
``scripts/generate_all_dependencies.py`` exists to replace.

Shipping the file inside the wheel moves the decision here, where the packages
whose metadata it summarises are. A build then copies one file rather than
re-deriving it, and every consumer of the distribution gets the same manifest.

The installed tree is built by ``uv pip install --target`` from
``packages/dash0-opentelemetry``, so it resolves through the workspace and
reflects the pins in this checkout rather than the last release on PyPI. The
install targets Python ``TARGET_PYTHON``, the floor of the distribution's
``requires-python``: a dependency a newer interpreter does not need is in the
tree of an older one, never the other way round.

The result is stable enough to check in. Every version in the tree is pinned
exactly by ``packages/dash0-opentelemetry/pyproject.toml``, which
``scripts/check_pinned_dependencies.py`` enforces, so resolution has nothing
left to decide. Environment markers are carried into the manifest unevaluated,
so the file does not depend on the interpreter or the platform that generated
it either.

Usage::

    python3 scripts/refresh_injector_manifest.py
    python3 scripts/refresh_injector_manifest.py --check

``--check`` prints a unified diff and exits non-zero instead of writing, which
is what CI runs.

Runs on Python >= 3.10 with ``uv`` on the PATH and ``packaging`` importable.
"""

from argparse import ArgumentParser
from difflib import unified_diff
from pathlib import Path
from subprocess import run
from sys import exit as sys_exit
from tempfile import TemporaryDirectory

from generate_all_dependencies import manifest_lines, read_tree

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DISTRO: Path = REPO_ROOT / "packages" / "dash0-opentelemetry"
MANIFEST: Path = (
    DISTRO / "src" / "dash0" / "opentelemetry" / "injector" / "all-dependencies.txt"
)
TARGET_PYTHON: str = "3.10"


def main() -> int:
    parser = ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="print a diff and exit non-zero instead of writing",
    )
    arguments = parser.parse_args()

    with TemporaryDirectory() as scratch:
        tree = Path(scratch) / "tree"
        run(
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--target",
                str(tree),
                "--python",
                TARGET_PYTHON,
                str(DISTRO),
            ],
            check=True,
        )
        installed, demands = read_tree(tree)

    if not installed:
        print(f"installing {DISTRO.name} produced no .dist-info directories")
        return 1

    generated: str = "\n".join(manifest_lines(installed, demands)) + "\n"
    relative: Path = MANIFEST.relative_to(REPO_ROOT)

    if not arguments.check:
        MANIFEST.write_text(generated, encoding="utf-8")
        print(f"wrote {len(installed)} packages to {relative}")
        return 0

    checked_in: str = MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else ""
    if checked_in == generated:
        print(f"{relative} matches the tree {DISTRO.name} installs")
        return 0

    for line in unified_diff(
        checked_in.splitlines(keepends=True),
        generated.splitlines(keepends=True),
        fromfile=f"a/{relative}",
        tofile=f"b/{relative}",
    ):
        print(line, end="")
    print(
        f"{relative} is not what {Path(__file__).name} generates; "
        f"re-run it instead of editing the file by hand."
    )
    return 1


if __name__ == "__main__":
    sys_exit(main())
