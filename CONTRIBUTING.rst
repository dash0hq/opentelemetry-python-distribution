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

- ``packages/dash0-opentelemetry-distro`` — the distribution: ``Dash0Distro``
  and ``Dash0Configurator`` plus resource detection and settings. **This is the
  Dash0-authored code.**
- ``packages/opentelemetry-*`` — the pure-Python (pyproto) OTLP exporter
  packages, vendored from ``packaging/common/python/vendor`` in
  `open-telemetry/opentelemetry-packaging
  <https://github.com/open-telemetry/opentelemetry-packaging>`_. Treat these as
  vendored: keep them close to upstream and do not apply local style changes
  (they are excluded from linting).
- ``examples/`` — self-contained demos with their own Docker environments;
  excluded from the workspace.


Setup
=====

.. code-block:: bash

    uv sync --package dash0-opentelemetry-distro

This creates ``.venv`` with the distribution, the in-repo pyproto exporters,
and the dev dependencies.


Running the tests
=================

Distribution unit tests (fast, no Docker):

.. code-block:: bash

    uv run --package dash0-opentelemetry-distro \
      python -m pytest packages/dash0-opentelemetry-distro/tests -v

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

    uvx ruff@latest check packages/dash0-opentelemetry-distro examples
    uvx ruff@latest format --check packages/dash0-opentelemetry-distro examples

Apply fixes with ``ruff check --fix`` and ``ruff format`` (drop ``--check``).


Coding conventions
=================

- Every function has a name that precisely describes what it does.
- Prefer ``from x import y`` over ``import x``.
- Keep the distribution vendor-neutral except where Dash0 behavior is
  intentional; see the README's configuration section.
