"""Generate the static PEP 503 package index served from GitHub Pages.

The index is regenerated statelessly on every run from the full set of
*published, non-draft* GitHub releases: their package assets are downloaded,
re-hashed, and rendered into a simple-index site whose file URLs point at the
release assets with ``#sha256=`` fragments, so consumers can install with
``--require-hashes``. The HTML is emitted here directly (stdlib only) — no
third-party code runs in the job that controls what consumers hash-pin.

Trust model: the committed manifest (``scripts/index-manifest.json``) is the
source of truth for what bytes a filename may have. Assets are re-hashed on
every run; a filename whose recomputed hash differs from its manifest entry
aborts generation (the immutability guard) — the ``SHA256SUMS`` sidecar
uploaded with each release is a human-readable convenience, not what the index
trusts. New filenames are appended to the manifest, which the release workflow
commits back, so tampering shows up in branch-protected git history.

Recovery levers, both git-audited:

* ``scripts/index-excluded.toml`` — filenames skipped by both the guard and
  the index (recovery when the guard trips on a poisoned filename);
* ``scripts/index-yanked.toml`` — project versions marked yanked (PEP 592) in
  the generated index.

Runs on Python >= 3.11 (tomllib). Network access to the GitHub API and to the
release-asset downloads is required outside ``--help``/tests.
"""

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REPO = "dash0hq/opentelemetry-python-distribution"
DEFAULT_MANIFEST = REPO_ROOT / "scripts" / "index-manifest.json"
DEFAULT_YANKED = REPO_ROOT / "scripts" / "index-yanked.toml"
DEFAULT_EXCLUDED = REPO_ROOT / "scripts" / "index-excluded.toml"

# Only artifacts of these projects are ever indexed; anything else attached to
# a release (hostile or stray) is ignored.
EXPECTED_PROJECTS = frozenset(
    {
        "dash0-opentelemetry-pyproto",
        "dash0-opentelemetry-exporter-otlp-pyproto-common",
        "dash0-opentelemetry-exporter-otlp-pyproto-http",
        "dash0-opentelemetry-exporter-otlp-pyproto-grpc",
        "dash0-opentelemetry-distro",
    }
)

_ARTIFACT_RE = re.compile(
    r"^(?P<project>[A-Za-z0-9_.]+)-(?P<version>[0-9][^-]*?)"
    r"(?:-py3-none-any\.whl|\.tar\.gz)$"
)
_PRERELEASE_VERSION_RE = re.compile(r"(?:a|b|rc)[0-9]+|\.dev[0-9]+")


class IndexGenerationError(Exception):
    """Raised when the index must not be generated from the current inputs."""


def _normalize(name: str) -> str:
    """PEP 503 name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Entry:
    """One package file in the generated index."""

    filename: str
    url: str
    sha256: str
    uploaded_at: str
    yanked_reason: str | None = None

    @property
    def project(self) -> str:
        return _normalize(_ARTIFACT_RE.match(self.filename)["project"])

    @property
    def version(self) -> str:
        return _ARTIFACT_RE.match(self.filename)["version"]


def load_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_manifest(path: Path, manifest: dict[str, str]) -> None:
    path.write_text(json.dumps(dict(sorted(manifest.items())), indent=2) + "\n")


def load_excluded(path: Path) -> frozenset[str]:
    if not path.exists():
        return frozenset()
    data = tomllib.loads(path.read_text())
    return frozenset(data.get("excluded", []))


def load_yanked(path: Path) -> dict[tuple[str, str], str]:
    """Map of (normalized project, version) -> yank reason."""
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text())
    return {
        (_normalize(item["project"]), item["version"]): item.get("reason", "withdrawn")
        for item in data.get("yanked", [])
    }


def expected_asset_url_prefix(repo: str) -> str:
    return f"https://github.com/{repo}/releases/download/"


def collect_entries(
    releases: list[dict],
    *,
    repo: str,
    manifest: dict[str, str],
    excluded: frozenset[str],
    yanked: dict[tuple[str, str], str],
    fetch_asset: "callable",
) -> tuple[list[Entry], dict[str, str]]:
    """Walk releases and produce index entries plus manifest additions.

    ``fetch_asset`` maps an asset download URL to its bytes; it is injectable
    so tests never touch the network.

    Raises IndexGenerationError on any trust violation: a hash that differs
    from the manifest, or an asset URL outside this repository's release
    downloads.
    """
    url_prefix = expected_asset_url_prefix(repo)
    additions: dict[str, str] = {}
    entries: dict[str, Entry] = {}
    for release in releases:
        if release.get("draft"):
            continue
        for asset in release.get("assets", []):
            filename = asset["name"]
            match = _ARTIFACT_RE.match(filename)
            if not match or _normalize(match["project"]) not in EXPECTED_PROJECTS:
                continue
            if filename in excluded:
                continue
            if release.get("prerelease") and not _PRERELEASE_VERSION_RE.search(
                match["version"]
            ):
                raise IndexGenerationError(
                    f"release {release.get('tag_name')} is marked as a GitHub "
                    f"pre-release but {filename} does not carry a PEP 440 "
                    f"pre-release version; publish it as a full release or "
                    f"use an rc/dev version"
                )
            url = asset["browser_download_url"]
            if not url.startswith(url_prefix):
                raise IndexGenerationError(
                    f"asset {filename} resolves to {url}, outside the expected "
                    f"origin {url_prefix}"
                )
            digest = hashlib.sha256(fetch_asset(url)).hexdigest()
            known = manifest.get(filename) or additions.get(filename)
            if known is not None and known != digest:
                raise IndexGenerationError(
                    f"{filename} on release {release.get('tag_name')} hashes to "
                    f"{digest}, but {known} was previously published under that "
                    f"filename. Published artifacts are immutable; cut a new "
                    f"version, or exclude the filename via index-excluded.toml "
                    f"after investigating."
                )
            if filename not in manifest:
                additions[filename] = digest
            if filename not in entries:  # first (oldest) release wins
                entries[filename] = Entry(
                    filename=filename,
                    url=url,
                    sha256=digest,
                    uploaded_at=asset.get("created_at", ""),
                    yanked_reason=yanked.get(
                        (_normalize(match["project"]), match["version"])
                    ),
                )
    return sorted(entries.values(), key=lambda e: e.filename), additions


def _github_api(repo: str, token: str | None) -> list[dict]:
    """Enumerate all releases (paginated)."""
    releases: list[dict] = []
    page = 1
    while True:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        with urllib.request.urlopen(request) as response:
            batch = json.loads(response.read())
        if not batch:
            return releases
        releases.extend(batch)
        page += 1


def _fetch_asset(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        return response.read()


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        '<meta name="pypi:repository-version" content="1.0">\n'
        f"<title>{html.escape(title)}</title>\n"
        "</head>\n"
        "<body>\n"
        f"{body}"
        "</body>\n"
        "</html>\n"
    )


def generate_site(entries: list[Entry], output_dir: Path, repo: str) -> None:
    """Render the static PEP 503 simple-index site.

    Hand-rolled rather than generated with dumb-pypi: dumb-pypi joins one
    ``--packages-url`` base with each filename, but GitHub release-asset URLs
    embed the release tag, so every file needs its own URL. Emitting the HTML
    here also keeps third-party code out of the job that controls what
    consumers' lockfiles hash-pin.
    """
    by_project: dict[str, list[Entry]] = {}
    for entry in entries:
        by_project.setdefault(entry.project, []).append(entry)

    simple = output_dir / "simple"
    simple.mkdir(parents=True, exist_ok=True)
    project_links = "".join(
        f'<a href="{name}/">{name}</a><br>\n' for name in sorted(by_project)
    )
    (simple / "index.html").write_text(_page("Simple index", project_links))
    for name, files in sorted(by_project.items()):
        file_links = ""
        for entry in files:
            yanked = (
                f' data-yanked="{html.escape(entry.yanked_reason, quote=True)}"'
                if entry.yanked_reason is not None
                else ""
            )
            file_links += (
                f'<a href="{entry.url}#sha256={entry.sha256}"{yanked}>'
                f"{entry.filename}</a><br>\n"
            )
        project_dir = simple / name
        project_dir.mkdir(exist_ok=True)
        (project_dir / "index.html").write_text(_page(name, file_links))

    (output_dir / "index.html").write_text(
        _page(
            "Dash0 Python package index",
            "<h1>Dash0 Python package index</h1>\n"
            f'<p>PEP 503 simple index: <a href="simple/">simple/</a>. '
            f"Artifacts are GitHub release assets of "
            f'<a href="https://github.com/{html.escape(repo)}">{html.escape(repo)}</a>.'
            f"</p>\n",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--yanked", type=Path, default=DEFAULT_YANKED)
    parser.add_argument("--excluded", type=Path, default=DEFAULT_EXCLUDED)
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="write newly indexed filenames back to the manifest file",
    )
    parser.add_argument(
        "--github-token",
        default=None,
        help="GitHub API token (defaults to unauthenticated access)",
    )
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    try:
        entries, additions = collect_entries(
            _github_api(args.repo, args.github_token),
            repo=args.repo,
            manifest=manifest,
            excluded=load_excluded(args.excluded),
            yanked=load_yanked(args.yanked),
            fetch_asset=_fetch_asset,
        )
    except IndexGenerationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    generate_site(entries, args.output_dir, args.repo)
    print(f"indexed {len(entries)} files, {len(additions)} new")
    if additions and args.update_manifest:
        write_manifest(args.manifest, {**manifest, **additions})
        print(f"manifest updated: {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
