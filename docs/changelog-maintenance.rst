=====================
Changelog maintenance
=====================

This project uses `chloggen
<https://github.com/open-telemetry/opentelemetry-go-build-tools/tree/main/chloggen>`_
to manage changelog entries. Rather than editing ``CHANGELOG.rst`` directly,
each user-facing change gets its own YAML file in ``.chloggen/``; those files
are compiled into a dated version section at release time (see
``RELEASING.rst``). ``CHANGELOG.rst`` stays reStructuredText — chloggen renders
into it via the custom ``.chloggen/summary.tmpl`` template rather than its
built-in Markdown.

chloggen is a Go tool. The ``make`` targets below invoke it with ``go run``, so
only a Go toolchain is required — no Go dependency is added to this Python
project.

Creating an entry
=================

1. Run ``make chlog-new`` — this creates ``.chloggen/<branch-name>.yaml`` from
   the template. (Without Go, copy ``.chloggen/TEMPLATE.yaml`` to
   ``.chloggen/<slug>.yaml`` by hand.)
2. Fill in the fields:

   - ``change_type`` — one of ``breaking``, ``deprecation``, ``new_component``,
     ``enhancement``, ``bug_fix``.
   - ``component`` — the area of concern (e.g. ``distro``, ``pyproto``,
     ``exporter``, ``resource-detectors``, ``deps``, ``ci``, ``release``,
     ``docs``).
   - ``note`` — a one-line description; wrap it in quotes if it needs to start
     with a backtick. reStructuredText inline markup (``code`` and links) is
     rendered as-is into the changelog.
   - ``issues`` — one or more related issue or PR numbers, e.g. ``[28]`` (at
     least one required).
   - ``subtext`` — (optional) additional lines; use ``|-`` for multi-line text
     to avoid a trailing blank line.

3. Run ``make chlog-validate`` to verify the entry is well-formed.
4. Run ``make chlog-preview`` to see how it will render in ``CHANGELOG.rst``.
5. Commit the ``.chloggen/<branch-name>.yaml`` file with the rest of the
   changes.

When to skip
============

Add an entry for anything a user of the distribution would notice — behavior,
dependencies, packaging. If a change doesn't affect end users (refactoring, CI
changes, test-only changes, etc.), prefix the PR title with ``chore`` or add
the "Skip Changelog" label instead of creating an entry.

Reference
=========

- Template: ``.chloggen/TEMPLATE.yaml``
- Config: ``.chloggen/config.yaml``
- Render template: ``.chloggen/summary.tmpl``
