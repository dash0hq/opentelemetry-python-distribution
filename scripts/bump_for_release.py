"""Bump package versions for a release.

For each vendored workspace package (in dependency order), bumps the version
to the next .postN if:
  - the package's source files changed since the last release tag, OR
  - a direct workspace dependency will be bumped (cascade through the chain)
AND the current version is already in the published index manifest.

Then updates all cross-package == pins and sets the distro version to the
value provided on the command line.

Usage:
    python3 scripts/bump_for_release.py <new_distro_version> [--base <ref>]

The --base ref defaults to the last release tag (git describe --tags).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from tomllib import loads

sys.path.insert(0, str(Path(__file__).parent))
from _workspace import package_version, workspace_packages

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "scripts" / "index-manifest.json"

# Vendored packages in dependency order: each entry comes after its deps.
VENDORED_ORDER = [
    "dash0-opentelemetry-pyproto",
    "dash0-opentelemetry-exporter-otlp-pyproto-common",
    "dash0-opentelemetry-exporter-otlp-pyproto-http",
    "dash0-opentelemetry-exporter-otlp-pyproto-grpc",
]

# Direct workspace == pins for each package (only those that need updating).
WORKSPACE_PINS = {
    "dash0-opentelemetry-exporter-otlp-pyproto-common": [
        "dash0-opentelemetry-pyproto",
    ],
    "dash0-opentelemetry-exporter-otlp-pyproto-http": [
        "dash0-opentelemetry-exporter-otlp-pyproto-common",
    ],
    "dash0-opentelemetry-exporter-otlp-pyproto-grpc": [
        "dash0-opentelemetry-exporter-otlp-pyproto-common",
    ],
    "dash0-opentelemetry": [
        "dash0-opentelemetry-exporter-otlp-pyproto-http",
        "dash0-opentelemetry-exporter-otlp-pyproto-grpc",
    ],
}


def next_post_version(version: str) -> str:
    """1.44.0 → 1.44.0.post1, 1.44.0.post3 → 1.44.0.post4."""
    m = re.fullmatch(r"(.+?)(?:\.post(\d+))?", version)
    base, n = m.group(1), int(m.group(2) or 0)
    return f"{base}.post{n + 1}"


def in_manifest(name: str, version: str, manifest: dict) -> bool:
    return f"{name.replace('-', '_')}-{version}-py3-none-any.whl" in manifest


# A release version is a plain PEP 440 string — X.Y.Z with an optional
# pre-release (aN/bN/rcN) or post-release (.postN) suffix — and never carries a
# leading "v" (that prefix belongs only on the git tag). Mirrors the version
# shape create-tag-for-release.sh accepts.
DISTRO_VERSION_RE = re.compile(
    r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+|\.post[0-9]+)?"
)


def is_valid_distro_version(version: str) -> bool:
    return DISTRO_VERSION_RE.fullmatch(version) is not None


def git_changed_paths(base: str) -> set[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {line for line in out.splitlines() if line}


def source_changed(pkg_dir: Path, changed: set[str]) -> bool:
    """True if any file that ships in the wheel changed since base."""
    prefix = f"{pkg_dir.relative_to(REPO_ROOT)}/"
    tests_prefix = f"{prefix}tests/"
    return any(p.startswith(prefix) and not p.startswith(tests_prefix) for p in changed)


def version_file(pkg_dir: Path) -> Path:
    data = loads((pkg_dir / "pyproject.toml").read_text())
    return pkg_dir / data["tool"]["hatch"]["version"]["path"]


def write_version(vf: Path, new_version: str) -> None:
    content = vf.read_text()
    new_content = re.sub(
        r'(__version__\s*=\s*")[^"]+(")',
        rf"\g<1>{new_version}\g<2>",
        content,
    )
    assert new_content != content, f"No __version__ assignment found in {vf}"
    vf.write_text(new_content)


def read_pin(pyproject: Path, dep: str) -> str:
    m = re.search(rf'"{dep}\s*==\s*([^"]+)"', pyproject.read_text())
    return m.group(1).strip() if m else ""


def write_pin(pyproject: Path, dep: str, new_version: str) -> None:
    content = pyproject.read_text()
    new_content = re.sub(
        rf'("{dep}\s*==\s*)[^"]+"',
        rf"\g<1>{new_version}\"",
        content,
    )
    assert new_content != content, f"No == pin for {dep!r} found in {pyproject}"
    pyproject.write_text(new_content)


def last_release_tag() -> str:
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_distro_version", help="e.g. 0.3.0 or 0.3.0rc1")
    parser.add_argument(
        "--base",
        default="",
        help="Git ref to diff against (default: last release tag)",
    )
    args = parser.parse_args(argv)

    # Reject a malformed version before any file is written: a leading "v"
    # (e.g. "v0.3.0") would otherwise corrupt version.py and produce the tag
    # "vv0.3.0", stalling the release.
    if not is_valid_distro_version(args.new_distro_version):
        parser.error(
            f"invalid distro version {args.new_distro_version!r}: expected a "
            "plain release version such as 0.3.0, 0.3.0rc1, or 0.3.0.post1 "
            "(no leading 'v' — that prefix belongs only on the git tag)"
        )

    base = args.base or last_release_tag()
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    packages = workspace_packages()

    if base:
        print(f"Base ref: {base}")
        changed = git_changed_paths(base)
    else:
        print("No base ref (first release?) — skipping vendored bumps")
        changed = set()

    # --- Pass 1: compute new versions (in-memory, no file writes yet) ---
    new_versions: dict[str, str] = {}

    for name in VENDORED_ORDER:
        pkg_dir = packages[name]
        current = package_version(pkg_dir)
        dep_bumped = any(
            new_versions.get(d, package_version(packages[d]))
            != package_version(packages[d])
            for d in WORKSPACE_PINS.get(name, [])
        )
        needs_bump = (source_changed(pkg_dir, changed) or dep_bumped) and in_manifest(
            name, current, manifest
        )

        new_versions[name] = next_post_version(current) if needs_bump else current

    new_versions["dash0-opentelemetry"] = args.new_distro_version

    # --- Report plan ---
    print("\nVersion plan:")
    for name in VENDORED_ORDER + ["dash0-opentelemetry"]:
        old = package_version(packages[name])
        new = new_versions[name]
        print(f"  {name}: {old} → {new}" + (" (bump)" if new != old else ""))

    # --- Pass 2: write version files ---
    print("\nWriting version files:")
    for name in VENDORED_ORDER + ["dash0-opentelemetry"]:
        pkg_dir = packages[name]
        old = package_version(pkg_dir)
        new = new_versions[name]
        if new != old:
            vf = version_file(pkg_dir)
            write_version(vf, new)
            print(f"  {vf.relative_to(REPO_ROOT)}: {old} → {new}")

    # --- Pass 3: update cross-package == pins ---
    print("\nUpdating cross-package pins:")
    any_pin_change = False
    for name in VENDORED_ORDER + ["dash0-opentelemetry"]:
        pkg_dir = packages[name]
        pyproject = pkg_dir / "pyproject.toml"
        for dep in WORKSPACE_PINS.get(name, []):
            new_dep_ver = new_versions[dep]
            old_pin = read_pin(pyproject, dep)
            if old_pin != new_dep_ver:
                write_pin(pyproject, dep, new_dep_ver)
                rel = pyproject.relative_to(REPO_ROOT)
                print(f"  {rel}: {dep} == {old_pin} → {new_dep_ver}")
                any_pin_change = True

    if not any_pin_change:
        print("  (all pins already up to date)")

    print("\nDone. Run 'make chlog-update' and 'uv lock' next.")


if __name__ == "__main__":
    main()
