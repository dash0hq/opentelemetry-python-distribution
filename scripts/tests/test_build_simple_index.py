"""Unit tests for the index generator's trust and selection logic."""

import io
import json
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_simple_index as bsi  # noqa: E402

REPO = "dash0hq/opentelemetry-python-distribution"
URL_PREFIX = f"https://github.com/{REPO}/releases/download"

DISTRO_WHEEL = "dash0_opentelemetry_distro-0.1.0-py3-none-any.whl"
PYPROTO_WHEEL = "dash0_opentelemetry_pyproto-1.44.0-py3-none-any.whl"


def release(tag, filenames, *, draft=False, prerelease=False, url_prefix=None):
    prefix = url_prefix or f"{URL_PREFIX}/{tag}"
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": [
            {
                "name": name,
                "browser_download_url": f"{prefix}/{name}",
                "created_at": "2026-07-22T10:00:00Z",
            }
            for name in filenames
        ],
    }


def fetcher(contents_by_filename):
    def fetch(url):
        return contents_by_filename[url.rsplit("/", 1)[-1]]

    return fetch


def collect(releases, *, manifest=None, excluded=(), yanked=None, contents=None):
    contents = contents or {DISTRO_WHEEL: b"distro", PYPROTO_WHEEL: b"pyproto"}
    return bsi.collect_entries(
        releases,
        repo=REPO,
        manifest=manifest or {},
        excluded=frozenset(excluded),
        yanked=yanked or {},
        fetch_asset=fetcher(contents),
    )


def sha256(data):
    import hashlib

    return hashlib.sha256(data).hexdigest()


def test_identical_file_across_releases_is_indexed_once():
    entries, additions = collect(
        [
            release("v0.1.0", [DISTRO_WHEEL, PYPROTO_WHEEL]),
            release("v0.2.0", [PYPROTO_WHEEL]),
        ]
    )
    assert [e.filename for e in entries] == [DISTRO_WHEEL, PYPROTO_WHEEL]
    # The first release's URL wins for the deduplicated file.
    pyproto = next(e for e in entries if e.filename == PYPROTO_WHEEL)
    assert "/v0.1.0/" in pyproto.url
    assert set(additions) == {DISTRO_WHEEL, PYPROTO_WHEEL}


def test_hash_mismatch_with_manifest_aborts():
    manifest = {PYPROTO_WHEEL: sha256(b"previously published bytes")}
    with pytest.raises(bsi.IndexGenerationError) as excinfo:
        collect([release("v0.2.0", [PYPROTO_WHEEL])], manifest=manifest)
    message = str(excinfo.value)
    assert PYPROTO_WHEEL in message
    assert sha256(b"pyproto") in message
    assert manifest[PYPROTO_WHEEL] in message


def test_hash_mismatch_across_releases_in_same_run_aborts():
    def fetch(url):
        return b"one" if "/v0.1.0/" in url else b"two"

    with pytest.raises(bsi.IndexGenerationError):
        bsi.collect_entries(
            [release("v0.1.0", [PYPROTO_WHEEL]), release("v0.2.0", [PYPROTO_WHEEL])],
            repo=REPO,
            manifest={},
            excluded=frozenset(),
            yanked={},
            fetch_asset=fetch,
        )


def test_draft_releases_are_excluded():
    entries, additions = collect(
        [release("v0.1.0", [DISTRO_WHEEL], draft=True)],
    )
    assert entries == [] and additions == {}


def test_github_prerelease_requires_pep440_prerelease_version():
    rc_wheel = "dash0_opentelemetry_distro-0.1.0rc1-py3-none-any.whl"
    entries, _ = collect(
        [release("v0.1.0rc1", [rc_wheel], prerelease=True)],
        contents={rc_wheel: b"rc"},
    )
    assert [e.filename for e in entries] == [rc_wheel]

    with pytest.raises(bsi.IndexGenerationError):
        collect([release("v0.1.0", [DISTRO_WHEEL], prerelease=True)])


def test_unexpected_asset_names_are_ignored():
    entries, additions = collect(
        [release("v0.1.0", [DISTRO_WHEEL, "SHA256SUMS", "evil-1.0.tar.gz"])],
        contents={DISTRO_WHEEL: b"distro"},
    )
    assert [e.filename for e in entries] == [DISTRO_WHEEL]
    assert set(additions) == {DISTRO_WHEEL}


def test_unexpected_asset_url_origin_aborts():
    with pytest.raises(bsi.IndexGenerationError) as excinfo:
        collect(
            [
                release(
                    "v0.1.0",
                    [DISTRO_WHEEL],
                    url_prefix="https://evil.example.com/downloads",
                )
            ]
        )
    assert "outside the expected origin" in str(excinfo.value)


def test_excluded_filenames_skip_both_guard_and_index():
    manifest = {PYPROTO_WHEEL: sha256(b"different bytes")}
    entries, additions = collect(
        [release("v0.1.0", [DISTRO_WHEEL, PYPROTO_WHEEL])],
        manifest=manifest,
        excluded=[PYPROTO_WHEEL],
    )
    assert [e.filename for e in entries] == [DISTRO_WHEEL]
    assert set(additions) == {DISTRO_WHEEL}


def test_yanked_versions_carry_reason():
    yanked = {("dash0-opentelemetry-distro", "0.1.0"): "broken"}
    entries, _ = collect([release("v0.1.0", [DISTRO_WHEEL])], yanked=yanked)
    assert entries[0].yanked_reason == "broken"


def test_project_names_normalize_per_pep503():
    entries, _ = collect([release("v0.1.0", [DISTRO_WHEEL])])
    assert entries[0].project == "dash0-opentelemetry-distro"


def test_generated_site_shape(tmp_path):
    yanked = {("dash0-opentelemetry-pyproto", "1.44.0"): 'broken & "quoted"'}
    entries, _ = collect(
        [release("v0.1.0", [DISTRO_WHEEL, PYPROTO_WHEEL])], yanked=yanked
    )
    bsi.generate_site(entries, tmp_path, REPO)

    simple = (tmp_path / "simple" / "index.html").read_text()
    assert '<a href="dash0-opentelemetry-distro/">' in simple
    assert '<a href="dash0-opentelemetry-pyproto/">' in simple
    assert '<meta name="pypi:repository-version" content="1.0">' in simple

    distro = (
        tmp_path / "simple" / "dash0-opentelemetry-distro" / "index.html"
    ).read_text()
    assert f'href="{URL_PREFIX}/v0.1.0/{DISTRO_WHEEL}#sha256={sha256(b"distro")}"' in (
        distro
    )
    assert "data-yanked" not in distro

    pyproto = (
        tmp_path / "simple" / "dash0-opentelemetry-pyproto" / "index.html"
    ).read_text()
    assert 'data-yanked="broken &amp; &quot;quoted&quot;"' in pyproto

    assert (tmp_path / "index.html").exists()


def test_release_enumeration_paginates(monkeypatch):
    pages = {
        1: [release("v0.1.0", [])],
        2: [release("v0.2.0", [])],
        3: [],
    }

    def fake_urlopen(request):
        page = int(request.full_url.rsplit("page=", 1)[-1])
        return io.BytesIO(json.dumps(pages[page]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    releases = bsi._github_api(REPO, token=None)
    assert [r["tag_name"] for r in releases] == ["v0.1.0", "v0.2.0"]


def test_config_files_parse():
    assert bsi.load_excluded(bsi.DEFAULT_EXCLUDED) == frozenset()
    assert bsi.load_yanked(bsi.DEFAULT_YANKED) == {}
    assert bsi.load_manifest(bsi.DEFAULT_MANIFEST) == {}
