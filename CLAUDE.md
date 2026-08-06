# CLAUDE.md

Coding conventions and agentic guidelines for the Dash0 OpenTelemetry Python distribution.

## Project overview

A `uv` workspace. The Dash0-authored code lives entirely in
`packages/dash0-opentelemetry/`. The vendored pyproto exporter packages
(`packages/opentelemetry-*/`) are kept close to upstream; do not apply local
style changes to them (they are excluded from linting).

## Coding conventions

- Every function has a name that precisely describes what it does.
- Prefer `from x import y` over `import x`.
- Keep the distribution vendor-neutral except where Dash0 behavior is intentional.

## Maintaining the website documentation

The `docs/` directory contains Markdown files that are synced to the Dash0
website via `.github/workflows/sync-docs.yml`. Keep them accurate whenever
the relevant source changes.

### Source-of-truth mapping

Each doc file has a single authoritative source. When those sources change,
update the corresponding doc.

| Doc file | Authoritative source(s) | What to check |
|---|---|---|
| `docs/overview.md` | `README.rst`, `packages/dash0-opentelemetry/README.rst` | Overall description, key capabilities, architecture |
| `docs/getting-started.md` | `README.rst` (Quick start section), `examples/dash0-distro-flask/` | Quick start commands, example setup |
| `docs/configuration.md` | `packages/dash0-opentelemetry/src/dash0/opentelemetry/_environment_variables.py`, `packages/dash0-opentelemetry/src/dash0/opentelemetry/distro.py`, `packages/dash0-opentelemetry/src/dash0/opentelemetry/settings.py` | All `DASH0_*` variables and the `OTEL_*` defaults the distro sets |
| `docs/auto-instrumentation.md` | `packages/dash0-opentelemetry/pyproject.toml` (the `[project].dependencies` block, approx. lines 50–115) | The exact list of `opentelemetry-instrumentation-*` packages |
| `docs/resource-detection.md` | `packages/dash0-opentelemetry/src/dash0/opentelemetry/resource.py`, `packages/dash0-opentelemetry/README.rst` | Detector names, attributes emitted, detection logic |
| `docs/kubernetes-injection.md` | `packages/dash0-opentelemetry/src/dash0/opentelemetry/injector/sitecustomize.py` | Safety checks, deactivation logic, PYTHONPATH bridge |
| `docs/exporters.md` | `packages/dash0-opentelemetry/src/dash0/opentelemetry/distro.py`, `packages/opentelemetry-exporter-otlp-proto-http/`, `packages/opentelemetry-exporter-otlp-proto-grpc/` | Exporter names, protocol selection, port-rewriting logic |

### When to update docs

Update the relevant doc file whenever a PR:

- Adds, renames, or removes a `DASH0_*` environment variable → `docs/configuration.md`
- Adds or removes an `opentelemetry-instrumentation-*` dependency → `docs/auto-instrumentation.md`
- Changes how a resource detector works or what attributes it emits → `docs/resource-detection.md`
- Changes the `sitecustomize.py` safety checks or deactivation flow → `docs/kubernetes-injection.md`
- Changes the exporter selection logic, port-rewriting, or protocol handling → `docs/exporters.md`
- Changes the overall architecture, entry points, or quick-start workflow → `docs/overview.md`, `docs/getting-started.md`

### Auto-instrumentation list: always derive from source

**Never maintain `docs/auto-instrumentation.md` by hand.** Always derive the
library table from the actual dependency block in
`packages/dash0-opentelemetry/pyproject.toml`.

To regenerate the list:

```bash
grep 'opentelemetry-instrumentation-' packages/dash0-opentelemetry/pyproject.toml \
  | sed 's/.*"\(opentelemetry-instrumentation-[a-z0-9_-]*\).*/\1/'
```

Map each package name to its target library using the
[opentelemetry-python-contrib instrumentation index](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation)
and update the tables in `docs/auto-instrumentation.md` to match.
Keep the same category groupings (Web frameworks, HTTP clients, Databases, etc.).
Add new packages to the appropriate category; remove packages that are no longer in `pyproject.toml`.

Also update the "What is not included" section whenever a package is deliberately
excluded (the comments in `pyproject.toml` explain the reason for each exclusion).

### Keeping transformations.yaml in sync

`.github/workflows/sync-docs/transformations.yaml` declares which `docs/*.md`
files are synced to the website. It has a `coverage` block that fails CI if a
file under `docs/*.md` is not explicitly listed.

When you add a new `docs/*.md` file, add a corresponding entry to the `files:`
block in `transformations.yaml` with:
- `source:` — path relative to the repo root (e.g., `docs/new-topic.md`)
- `target:` — destination path on the website (follow the `opentelemetry/python/<slug>.md` pattern)
- `title:` — short display title for the page
- `description:` — one-sentence description used as the page meta description

When you remove a `docs/*.md` file, remove the corresponding `files:` entry too.

### Doc style rules

- One sentence per line (semantic line breaks) — this is the project's RST convention carried into Markdown.
- Sentence-case headings: `## Getting started`, not `## Getting Started`.
- Active voice: "The distro sets" not "The value is set by".
- Inline code for all env var names, file paths, package names, and CLI commands.
- No em-dashes; use shorter sentences instead.
- Tables for environment variables: three columns (variable name, description, notes/default).
- Do not add comments explaining what the doc is or when it was updated.
