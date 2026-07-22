=========
Releasing
=========

This document describes how releases are built and published, the one-time
administrative setup, the recovery runbooks, and the contract consumers rely
on.

Publishing channel
==================

Packages are **not** published to public PyPI. Each release attaches wheels
and sdists as GitHub release assets, and a static `PEP 503
<https://peps.python.org/pep-0503/>`_ "simple" index served from GitHub Pages
points at them with ``#sha256=`` fragments:

    https://dash0hq.github.io/opentelemetry-python-distribution/simple/

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
   defensively registered on public PyPI (see `Name reservation`_).
2. **Scope.** All five workspace packages are published to the self-hosted
   index. Public PyPI publication of the real packages is deferred until
   there is a non-operator audience; the artifacts and the already-claimed
   names make that step additive.
3. **Versioning.** The distribution versions independently (semver). The
   vendored packages carry their upstream base version with ``.postN``
   increments for Dash0-side changes (e.g. ``1.44.0``, ``1.44.0.post1``).
   ``.dev`` versions never reach the index; the release workflow rejects
   them. Because the distro pins the vendored exporters exactly, a vendored
   ``.postN`` release requires a coordinated distro release that bumps the
   pins.

Cutting a release
=================

1. Bump the versions being released: the distro's ``version.py`` always
   (the tag is derived from it), plus any vendored package that changed
   (``.postN``) together with the distro's ``==`` pins on it.
2. Update ``CHANGELOG.rst`` and regenerate ``uv.lock`` (``uv lock``).
3. Land those changes on ``main`` through a PR.
4. Tag and push: ``git tag v<distro-version> && git push origin v<distro-version>``.

**Never create or publish releases from the GitHub UI.** The pipeline
assembles releases draft-first and publishes them itself; a release published
by hand is immutable before any asset is attached, cannot be repaired, and its
version must be burned. CI enforces the version side of this: a PR that
changes a package whose current version is already published fails
(``scripts/check_version_bumped.py``) — the release pipeline would otherwise
silently skip rebuilding it.

The workflow then: validates the tag against the distro version and rejects
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

**Rehearse without touching anything** — run the ``Release`` workflow manually
with ``mode: dry-run``. It regenerates the index from the current releases and
uploads it as a workflow artifact; nothing deploys and the manifest is not
updated.

**Rebuild the index without rebuilding artifacts** (Pages deploy failed, or
yank/exclusion metadata changed) — run with ``mode: rebuild-index``.

**A release run was cancelled by the concurrency queue** (GitHub keeps only
one pending run per group; publishing 3+ releases in quick succession cancels
the middle ones) — run with ``mode: rebuild-assets`` and the affected tag. The
release must still be a draft or missing; published releases are immutable.

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

1. The repository must be public — release-asset URLs and GitHub Pages depend
   on it.
2. Enable **immutable releases** (Settings → General → Releases).
3. Add a **tag ruleset** for ``v*`` forbidding tag updates and deletions.
4. Enable **GitHub Pages** with "GitHub Actions" as the source.
5. Configure the ``github-pages`` environment's deployment policy to allow
   the default branch **and the ``v*`` tag pattern** — release-triggered runs
   deploy from tag refs; a branch-only policy silently blocks every release
   deploy.
6. Create the **index deploy key**: generate an SSH keypair, add the public
   key as a repository deploy key with write access, store the private key as
   the ``INDEX_DEPLOY_KEY`` secret, and grant the deploy key bypass on the
   ``main`` branch ruleset. This is the only credential that can push the
   manifest commits; do not widen branch protection for the generic Actions
   token instead.
7. Create the ``pypi`` environment with **required reviewers** and a
   deployment policy restricted to the default branch (used only by the name
   reservation below).

.. _Name reservation:

Name reservation on public PyPI (an org admin, **before the rename lands on
the default branch** — the names are guessable from the public history the
moment it merges):

1. Create the Dash0 **organization account** on PyPI with enforced 2FA.
2. Check each of the five names is still unclaimed, then add a **pending
   trusted publisher** per name, bound to ``reserve-pypi-names.yml`` and the
   ``pypi`` environment of this repository. Pending publishers do not reserve
   names — only the first upload does — so proceed immediately.
3. Run the ``Reserve PyPI names`` workflow. It publishes ``0.0.0.devN`` stubs
   whose README points at the real index. Re-runs are safe
   (``skip-existing``).
4. **Mandatory:** remove the five trusted publishers on PyPI in the same
   session and verify in each project's Publishing settings that none remain.
   A standing publisher binding is a publish capability to the public names
   for anyone who can run the workflow. (Re-adding one takes two minutes if a
   stub ever needs refreshing; increment ``N`` — PyPI permanently forbids
   filename reuse.)
5. When the PEP 755 namespace-grant process goes live on PyPI, apply for a
   restricted grant on the ``dash0`` prefix through the organization account.

Consumer contract
=================

Consumers (today: the dash0-operator's instrumentation image build) install
with the index as an *extra* index and full hash pinning::

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
                dash0-opentelemetry-distro; do
      uv build --package "$name" --out-dir dist \
        --build-constraints scripts/build-constraints.txt
    done
