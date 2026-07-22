"""Single source of truth for the workspace's packages and their versions.

``build_simple_index.py``, ``check_version_bumped.py``, and the release
workflow's build-selection step all need to answer "which packages exist and
at what version". They used to each derive that independently — two scanned
``packages/*/pyproject.toml`` while the index generator read the root
``[tool.uv.sources]`` — so the three could silently disagree about the
membership set. Deriving all of them from this one module keeps them aligned;
``[tool.uv.workspace] members = ["packages/*"]`` makes the glob the workspace's
own definition of membership.

Runs on Python >= 3.11 (tomllib).
"""

from pathlib import Path
from re import search

from tomllib import loads

REPO_ROOT = Path(__file__).resolve().parent.parent


def workspace_packages(repo_root: Path = REPO_ROOT) -> dict[str, Path]:
    """Map of distribution name -> package directory, from ``packages/*``."""
    packages = {}
    for pyproject in sorted(repo_root.glob("packages/*/pyproject.toml")):
        name = loads(pyproject.read_text())["project"]["name"]
        packages[name] = pyproject.parent
    return packages


def package_version(package_dir: Path) -> str:
    """Read ``__version__`` from the package's hatch-configured version file."""
    data = loads((package_dir / "pyproject.toml").read_text())
    version_file = package_dir / data["tool"]["hatch"]["version"]["path"]
    match = search(r'__version__ = "([^"]+)"', version_file.read_text())
    if match is None:
        raise ValueError(f"no __version__ assignment found in {version_file}")
    return match.group(1)


def declared_workspace_sources(repo_root: Path = REPO_ROOT) -> frozenset[str]:
    """Distribution names registered as workspace members in ``[tool.uv.sources]``.

    Kept separate from :func:`workspace_packages` so callers can assert the two
    agree — a package present on disk but missing from ``[tool.uv.sources]``
    (or vice versa) would break editable resolution while the scripts happily
    carried on.
    """
    sources = loads((repo_root / "pyproject.toml").read_text())["tool"]["uv"]["sources"]
    return frozenset(
        name
        for name, source in sources.items()
        if isinstance(source, dict) and source.get("workspace")
    )
