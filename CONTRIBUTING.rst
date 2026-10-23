============
Contributing
============

This repository is a `uv <https://docs.astral.sh/uv/>`_ workspace. All commands
below are run from the repository root.

Prerequisites
=============

- `uv <https://docs.astral.sh/uv/getting-started/installation/>`_
- Docker with the Compose plugin (only for the end-to-end example)


Project layout
==============

- ``packages/dash0-opentelemetry`` — the distribution: ``Dash0Distro``
  and ``Dash0Configurator`` plus resource detection and settings. **This is the
  Dash0-authored code.**
- ``packages/opentelemetry-*`` — the pure-Python (pyproto) OTLP exporter
  packages, vendored from ``packaging/common/python/vendor`` in
  `open-telemetry/opentelemetry-packaging
  <https://github.com/open-telemetry/opentelemetry-packaging>`_ and published
  under ``dash0-opentelemetry-*`` distribution names (the directories keep the
  upstream names). Treat these as vendored: keep them close to upstream and do
  not apply local style changes (they are excluded from linting).
- ``examples/`` — self-contained demos with their own Docker environments;
  excluded from the workspace.


Setup
=====

.. code-block:: bash

    uv sync --package dash0-opentelemetry

This creates ``.venv`` with the distribution, the in-repo pyproto exporters,
and the dev dependencies.


Running the tests
=================

Distribution unit tests (fast, no Docker):

.. code-block:: bash

    uv run --package dash0-opentelemetry \
      python -m pytest packages/dash0-opentelemetry/tests -v

End-to-end example (requires Docker; builds the distro into a container, runs a
Flask app under ``opentelemetry-instrument``, and asserts on the exported
telemetry):

.. code-block:: bash

    cd examples/dash0-distro-flask
    uv run --project . pytest tests/ -v

Both suites run in CI (see ``.github/workflows/``).


Linting and formatting
=====================

Lint and format checks apply to the Dash0-authored code only (the vendored
pyproto packages are excluded via ``ruff.toml``):

.. code-block:: bash

    uvx ruff@latest check packages/dash0-opentelemetry examples
    uvx ruff@latest format --check packages/dash0-opentelemetry examples

Apply fixes with ``ruff check --fix`` and ``ruff format`` (drop ``--check``).


Changelog
=========

Every pull request that affects end users must include a changelog entry.
``CHANGELOG.rst`` is managed with `chloggen
<https://github.com/open-telemetry/opentelemetry-go-build-tools/tree/main/chloggen>`_:
rather than editing ``CHANGELOG.rst`` directly, each user-facing change adds a
small YAML file under ``.chloggen/`` that is compiled into a dated version
section at release time. See ``docs/changelog-maintenance.rst`` for full
instructions on creating, validating, and previewing entries.

Quick start:

.. code-block:: bash

    make chlog-new        # create .chloggen/<branch-name>.yaml
    # edit the file
    make chlog-validate   # check it is well-formed

If the change does not affect end users (refactoring, CI, etc.), prefix the PR
title with ``chore`` or add the "Skip Changelog" label. CI validates all
pending entries on every pull request.


Generated files
===============

``packages/dash0-opentelemetry/src/dash0/opentelemetry/injector/all-dependencies.txt``
is generated rather than written by hand. Each line states what the packages in
the injected tree declare they support, and ``sitecustomize.py`` reads it at
interpreter startup to decide whether the application it was injected into
conflicts with the distribution.

Regenerate it whenever a pin in
``packages/dash0-opentelemetry/pyproject.toml`` moves::

    python3 scripts/refresh_injector_manifest.py

The ``injector-manifest`` job runs the same script with ``--check``, prints a
diff and fails when the checked-in file does not match.

The weekly Dependabot pull request for the ``opentelemetry`` group declared in
``.github/dependabot.yml`` moves those pins, and Dependabot does not run the
script, so that job fails until someone pushes the regenerated file to the
branch. Dependabot stops managing a pull request once the branch carries a
commit it did not write, so close and reopen the pull request if you need it to
take the branch back.


Coding conventions
=================

- Every function has a name that precisely describes what it does.
- Prefer ``from x import y`` over ``import x``.
- Keep the distribution vendor-neutral except where Dash0 behavior is
  intentional; see the README's configuration section.
