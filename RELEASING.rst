=========
Releasing
=========

This document describes how releases are built and published, and the decisions
that must be made before the first public release.

Overview
========

The ``.github/workflows/release.yml`` workflow builds sdists and wheels for
every workspace package and publishes them to a Python index:

- **Publishing a GitHub Release** publishes to **PyPI**.
- **Manual run** (``workflow_dispatch``) publishes to **TestPyPI** by default,
  or PyPI if selected — useful for dry runs.

Publishing uses **PyPI Trusted Publishing** (OIDC): no API tokens or long-lived
secrets are stored in the repository.

Versioning
==========

Each package's version is read from its ``version.py`` (``[tool.hatch.version]``).
Bump the relevant ``version.py`` files, update ``CHANGELOG.rst``, commit, then
create a GitHub Release whose tag matches the version being shipped.

One-time prerequisites (admin)
==============================

Before the first release, an org/PyPI admin must:

1. Create the projects on PyPI (and TestPyPI for dry runs).
2. Configure a **Trusted Publisher** on each project pointing at this
   repository and workflow, and at the ``pypi`` / ``testpypi`` GitHub
   Environments referenced by the workflow.

Open decisions (must be resolved before publishing)
==================================================

These are intentionally left open; they are policy/ownership questions, not
mechanics:

1. **Package names under the ``opentelemetry-`` prefix.** The vendored exporters
   are named ``opentelemetry-pyproto`` and
   ``opentelemetry-exporter-otlp-pyproto-*``. Publishing packages under the
   ``opentelemetry-`` namespace that are not official OpenTelemetry project
   releases is likely to be contentious. Preferred resolution: **upstream the
   pyproto work** so these come from the OpenTelemetry project, and have the
   distribution depend on the published versions. Alternatively, rename them
   under a Dash0-owned namespace.
2. **What gets published.** The distribution depends on the pyproto exporters,
   so it cannot be installed from PyPI unless those are also available there (or
   upstreamed). Decide whether this repo publishes the full set, or only
   ``dash0-opentelemetry-distro`` once pyproto is available upstream.
3. **Distribution version scheme.** e.g. track the upstream OTel SDK version
   with a Dash0 suffix, or version the distribution independently.

Until (1) and (2) are resolved, run the workflow against **TestPyPI** only.

Local build (dry run)
=====================

.. code-block:: bash

    for name in opentelemetry-pyproto \
                opentelemetry-exporter-otlp-pyproto-common \
                opentelemetry-exporter-otlp-pyproto-http \
                opentelemetry-exporter-otlp-pyproto-grpc \
                dash0-opentelemetry-distro; do
      uv build --package "$name" --out-dir dist
    done
