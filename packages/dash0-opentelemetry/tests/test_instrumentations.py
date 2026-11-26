"""Keeps the curated instrumentation dependency set in sync with upstream.

Upstream enumerates every auto-instrumentation package in the
``bootstrap_gen`` module of ``opentelemetry-instrumentation`` (the list behind
``opentelemetry-bootstrap``). The distribution instead ships those packages as
regular dependencies (see pyproject.toml) so injected processes need no
bootstrap step. These tests fail when a contrib version bump adds, removes, or
re-pins instrumentations upstream and the dependency block was not re-synced.

An instrumentation listed in ``VENDORED_INSTRUMENTATIONS`` is carried as source
inside ``dash0-opentelemetry`` rather than depended on, so the upstream
distribution is absent from the tree and the two tests that read its metadata
skip it. The ``UPSTREAM`` file beside each vendored tree records where the
source came from and what has to happen before it goes away.
"""

from importlib.metadata import PackageNotFoundError, distribution, requires, version

from dash0.opentelemetry.injector._packaging.requirements import Requirement
from opentelemetry.instrumentation import bootstrap_gen

_DISTRO = "dash0-opentelemetry"

VENDORED_INSTRUMENTATIONS: dict[str, str] = {
    "opentelemetry-instrumentation-asyncclick": (
        "opentelemetry.instrumentation.asyncclick"
    ),
}


def _declared():
    return {
        requirement.name: requirement
        for requirement in map(Requirement, requires(_DISTRO))
    }


def _upstream():
    entries = set(bootstrap_gen.default_instrumentations)
    entries.update(library["instrumentation"] for library in bootstrap_gen.libraries)
    return {requirement.name: requirement for requirement in map(Requirement, entries)}


def test_every_upstream_instrumentation_is_shipped():
    missing = sorted(
        set(_upstream()) - set(_declared()) - set(VENDORED_INSTRUMENTATIONS)
    )

    assert not missing, (
        f"upstream added instrumentations not declared in pyproject.toml: {missing}"
    )


def test_no_stale_instrumentations_are_shipped():
    declared_instrumentations = {
        name
        for name in _declared()
        if name.startswith("opentelemetry-instrumentation-")
    }
    stale = sorted(declared_instrumentations - set(_upstream()))

    assert not stale, (
        f"pyproject.toml declares instrumentations upstream no longer lists: {stale}"
    )


def test_installed_versions_satisfy_upstream_pins():
    # Also guards the opentelemetry-instrumentation-vertexai PyPI name, which
    # Traceloop's openllmetry uses for an unrelated 0.x line: upstream pins
    # >= 2.0b0, so resolving Traceloop's package fails this test.
    mismatched = [
        f"{name}{requirement.specifier} (installed: {version(name)})"
        for name, requirement in _upstream().items()
        if name not in VENDORED_INSTRUMENTATIONS
        and not requirement.specifier.contains(version(name), prereleases=True)
    ]

    assert not mismatched, (
        f"installed instrumentations do not satisfy upstream pins: {mismatched}"
    )


def test_vendored_instrumentations_are_not_also_installed():
    """Two distributions owning one import path is what vendoring has to avoid."""
    installed = []
    for name in sorted(VENDORED_INSTRUMENTATIONS):
        try:
            installed.append(f"{name} {distribution(name).version}")
        except PackageNotFoundError:
            continue

    assert not installed, (
        f"vendored instrumentations are also installed as distributions, so the "
        f"import path and the entry point have two owners: {installed}"
    )
