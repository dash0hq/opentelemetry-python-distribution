=========
Releasing
=========

This document describes how releases are built and published, the one-time
administrative setup, the recovery runbooks, and the contract consumers rely
on.

Publishing channel
==================

Each release publishes packages to **two channels**:

1. **Public PyPI** — via OIDC trusted publishing in the ``release.yml``
   ``publish-pypi`` job. Consumers can install with a plain
   ``pip install dash0-opentelemetry``.
2. **Dash0 package index** — a static `PEP 503
   <https://peps.python.org/pep-0503/>`_ "simple" index served from GitHub
   Pages, backed by GitHub release assets with ``#sha256=`` fragments:

       https://dash0hq.github.io/opentelemetry-python-distribution/simple/

   This index hosts all five workspace packages (including the vendored pyproto
   exporters) and is the authoritative source for production consumers that
   install with ``--require-hashes`` and ``--only-binary :all:``.

``.github/workflows/release.yml`` implements the pipeline; the index is
regenerated statelessly from all published releases by
``scripts/build_simple_index.py`` on every run.

Resolved decisions
==================

The three decisions that used to gate publishing are resolved:

1. **Naming.** The vendored pyproto packages are renamed at the
   distribution-name level to ``dash0-opentelemetry-pyproto`` and
   ``dash0-opentelemetry-exporter-otlp-pyproto-{common,http,grpc}``, so
   nothing is published under ``opentelemetry-*`` names the upstream
   OpenTelemetry project intends to release itself. Import paths and
   entry-point names stay upstream-shaped: when upstream publishes the
   official packages, the distribution switches its dependencies over and the
   renamed copies are deprecated. The ``dash0-opentelemetry-*`` names are
   claimed on public PyPI via the first real release.
2. **Scope.** All five workspace packages are published to the self-hosted
   index. The main ``dash0-opentelemetry`` package and the four supporting
   pyproto packages are also published to public PyPI.
3. **Versioning.** The distribution versions independently (semver). The
   vendored packages carry their upstream base version with ``.postN``
   increments for Dash0-side changes (e.g. ``1.44.0``, ``1.44.0.post1``).
   ``.dev`` versions never reach the index; the release workflow rejects
   them. Because the distro pins the vendored exporters exactly, a vendored
   ``.postN`` release requires a coordinated distro release that bumps the
   pins.

Cutting a release
=================

1. Add a ``.chloggen/`` entry for any user-visible changes (``make chlog-new``).
2. Trigger the **Prepare Release** workflow (``prepare-release.yml``) via
   ``workflow_dispatch`` with the new distro version (e.g. ``0.3.0``).
   The workflow:

   - Bumps any vendored package whose source changed since the last release
     tag to the next ``.postN`` version and cascades the ``==`` pins.
   - Sets the distro version in ``version.py``.
   - Folds pending ``.chloggen/`` entries into ``CHANGELOG.rst`` via
     ``make chlog-update``.
   - Relocks (``uv lock``).
   - Commits directly to ``main`` with the message
     ``docs: update changelog to prepare release v<version>``.

3. The **Automation - Create Tag for Release** workflow detects that commit
   message, creates the ``v<version>`` tag, and pushes it. The tag push
   triggers **Release**, which builds, attests, uploads the GitHub release,
   regenerates the index, and publishes to PyPI.

**Never create or publish releases from the GitHub UI.** The pipeline
assembles releases draft-first and publishes them itself; a release published
by hand is immutable before any asset is attached, cannot be repaired, and its
version must be burned. CI enforces the version side of this: a PR that
changes a package whose current version is already published fails
(``scripts/check_version_bumped.py``) — the release pipeline would otherwise
silently skip rebuilding it.

The ``Release`` workflow: validates the tag (``vX.Y.Z`` with optional PEP 440
pre-release or ``.postN`` suffix) against the distro version and rejects
``.dev`` versions anywhere; builds **only** artifacts whose filenames are not
yet in ``scripts/index-manifest.json`` (published artifacts are immutable, and
rebuilds are not byte-stable across toolchain upgrades); writes a
``SHA256SUMS`` sidecar; attests provenance; uploads everything to a **draft**
release and publishes it as the final step (the immutable-releases setting
freezes assets at publish time, so a release can never go live with an
incomplete asset set); regenerates the index, commits the manifest additions
to ``main``, and deploys to Pages.

Use a PEP 440 pre-release version (e.g. ``0.2.0rc1``) for rehearsal releases;
the workflow marks the GitHub release as a pre-release automatically. The
GitHub pre-release flag itself is cosmetic — resolvers act on the PEP 440
version string per file, and vendored packages on a rehearsal release
legitimately carry their stable versions.

Runbooks
========

**Rebuild a release whose run was cancelled by the concurrency queue**
(GitHub keeps only one pending run per group; publishing 3+ releases in quick
succession cancels the middle ones) — run the ``Release`` workflow manually
via ``workflow_dispatch`` with the affected tag. The release must still be a
draft or missing; published releases are immutable.

**Withdraw a broken version** — never delete a release: its asset URLs are
baked into every consumer lockfile that pins the version, and pip re-resolves
via the index on every operator image build. Instead add the version to
``scripts/index-yanked.toml`` (PEP 592 yank) — using the version string
exactly as it appears in the artifact filename; the index rebuild fails
loudly on a yank entry that matches nothing — land it on ``main``, and run
``mode: rebuild-index``. Yanked versions stay installable for exact-pin
consumers but are skipped by resolvers otherwise.

**The immutability guard tripped** (an asset's bytes differ from the committed
manifest — every index run fails until resolved) — investigate first: this is
either an operational mistake (an artifact changed without a version bump) or
tampering. Then add the filename to ``scripts/index-excluded.toml`` (the index
and the guard skip it), land it on ``main``, cut a new version if needed, and
run ``mode: rebuild-index``. The exclusion commit is the audit record.

One-time administrative setup
=============================

Repository (an admin, before the first release):

1. Enable **immutable releases** (Settings → General → Releases).
3. Add a **tag ruleset** for ``v*`` forbidding tag updates and deletions.
4. Enable **GitHub Pages** with "GitHub Actions" as the source.
5. Configure the ``github-pages`` environment's deployment policy to allow
   the default branch **and the ``v*`` tag pattern** — release-triggered runs
   deploy from tag refs; a branch-only policy silently blocks every release
   deploy.
5. Create the **index deploy key**: generate an SSH keypair, add the public
   key as a repository deploy key with write access, store the private key as
   the ``INDEX_DEPLOY_KEY`` secret, and grant the deploy key bypass on the
   ``main`` branch ruleset. This is the only credential that can push the
   manifest commits; do not widen branch protection for the generic Actions
   token instead.
6. Create a **Personal Access Token** (classic or fine-grained, with
   ``Contents: write`` on this repository) for a maintainer account and store
   it as the ``REPOSITORY_FULL_ACCESS_GITHUB_TOKEN`` repository secret. The ``Automation - Create Tag
   for Release`` workflow uses this token so that the tag push fires
   ``Release`` — events triggered by the default ``GITHUB_TOKEN`` do not start
   new workflow runs.
7. Create **five** GitHub environments, one per published package, each with a
   deployment policy restricted to tag refs matching ``v*``:

   - ``pypi-dash0-opentelemetry``
   - ``pypi-dash0-opentelemetry-pyproto``
   - ``pypi-dash0-opentelemetry-exporter-otlp-pyproto-common``
   - ``pypi-dash0-opentelemetry-exporter-otlp-pyproto-http``
   - ``pypi-dash0-opentelemetry-exporter-otlp-pyproto-grpc``

PyPI trusted publishing (an org admin, once, before the first release):

1. Create the Dash0 **organization account** on PyPI with enforced 2FA.
2. For each of the five package names, add a **pending trusted publisher**
   bound to ``release.yml``, the ``publish-pypi`` job, and the corresponding
   ``pypi-<package-name>`` environment of this repository. Pending publishers
   claim names on first upload without pre-registering them. PyPI limits
   pending publishers to three per ``repo + workflow + environment``
   combination; because each package uses a distinct environment this
   constraint does not apply, but PyPI also caps pending publishers per account
   — register in batches if needed, using the ``workflow_dispatch`` ``packages``
   input to publish each batch separately.
3. Verify by pushing a pre-release tag (e.g. ``v0.3.0rc1``) and confirming
   all five packages appear on PyPI under the Dash0 organization.
4. When the PEP 755 namespace-grant process goes live on PyPI, apply for a
   restricted grant on the ``dash0`` prefix through the organization account.

While the repository is private
===============================

The pipeline works unchanged on the private repository — releases, assets,
manifest commits, and attestations all function — but the *anonymous*
consumption paths do not: access-controlled Pages sites authenticate with
GitHub SSO cookies (no token/header auth exists for them, so pip can never
read the index), and release-asset ``browser_download_url``\ s do not honor
token auth from pip's fetcher. Until the repository goes public, consumers
must fetch the wheels with an authenticated client *before* pip runs::

    gh release download "v${VERSION}" --repo dash0hq/opentelemetry-python-distribution \
      --pattern '*.whl' --dir wheels/
    pip install --no-index --find-links wheels/ \
      --require-hashes --only-binary :all: -r requirements.txt

Renovate tracks versions with its ``github-releases`` datasource (same token)
instead of the ``pypi`` datasource below.

Going public later requires no re-publishing: asset URLs are stable across the
visibility flip, the Pages site moves from its obfuscated
``*.pages.github.io`` domain to the canonical URL below automatically, and the
index-based consumer contract takes over from this section.

Consumer contract
=================

Consumers (today: the dash0-operator's instrumentation image build) install
with the index as an *extra* index and full hash pinning (**requires the
repository to be public**; see the previous section until then)::

    pip install \
      --extra-index-url https://dash0hq.github.io/opentelemetry-python-distribution/simple/ \
      --require-hashes --only-binary :all: \
      -r requirements.txt

- ``--require-hashes`` (with a fully hashed lockfile generated by
  ``pip-compile --generate-hashes`` or ``uv export`` against both indexes)
  defeats dependency confusion regardless of index priority; the defensive
  PyPI registration closes the squatting hole at lock-generation time.
- ``--only-binary :all:`` closes the sdist build-dependency hole that
  ``--require-hashes`` does not cover; all five packages ship universal
  wheels.
- Renovate does not reliably pick up ``--extra-index-url`` from requirements
  files; configure the index explicitly (the ``/simple/`` suffix makes
  Renovate skip the JSON API)::

    {
      "packageRules": [{
        "matchDatasources": ["pypi"],
        "matchPackageNames": ["dash0-opentelemetry-*"],
        "registryUrls": [
          "https://dash0hq.github.io/opentelemetry-python-distribution/simple/"
        ]
      }]
    }

- Artifacts carry GitHub provenance attestations; lock regeneration can
  additionally verify them with ``gh attestation verify <file> --repo
  dash0hq/opentelemetry-python-distribution``.
- Caveat during the transition window: the renamed packages ship the same
  module files the future official ``opentelemetry-*`` pyproto packages will
  ship. Installing both in one environment silently overlaps files; the
  injected tree the operator builds is controlled, so this only concerns
  ad-hoc pip installs.

Local build (dry run)
=====================

.. code-block:: bash

    for name in dash0-opentelemetry-pyproto \
                dash0-opentelemetry-exporter-otlp-pyproto-common \
                dash0-opentelemetry-exporter-otlp-pyproto-http \
                dash0-opentelemetry-exporter-otlp-pyproto-grpc \
                dash0-opentelemetry; do
      uv build --package "$name" --out-dir dist \
        --build-constraints scripts/build-constraints.txt
    done
