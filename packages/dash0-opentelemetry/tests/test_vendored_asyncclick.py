"""The asyncclick instrumentation carried as source instead of as a dependency.

``opentelemetry-instrumentation-asyncclick`` 0.66b2 declares ``wrapt ~= 1.0``,
the only term in the injected tree that rejects wrapt 2.x, and one rejected
line in ``all-dependencies.txt`` stands the whole distribution down. The source
lives here until a release carrying
open-telemetry/opentelemetry-python-contrib#5117 exists; ``UPSTREAM`` beside it
records where it came from.

These tests cover what the swap has to preserve: the entry point keeps its
upstream name and target, the dependency gate still skips the instrumentor when
the application has no asyncclick, and the instrumentor still records a span.
"""

from asyncio import run as asyncio_run
from importlib.metadata import distribution, entry_points
from pathlib import Path
from re import match as re_match

from asyncclick import command, echo
from asyncclick.testing import CliRunner
from opentelemetry.instrumentation.asyncclick import AsyncClickInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

VENDORED: Path = (
    Path(__file__).resolve().parents[1] / "src/opentelemetry/instrumentation/asyncclick"
)


def upstream_fields() -> dict[str, str]:
    """The ``key = value`` lines of ``UPSTREAM``, ignoring continuation lines."""
    fields: dict[str, str] = {}
    for line in (VENDORED / "UPSTREAM").read_text(encoding="utf-8").splitlines():
        matched = re_match(r"^(\w+) = (.*)$", line)
        if matched:
            fields[matched.group(1)] = matched.group(2)
    return fields


def test_the_entry_point_keeps_its_upstream_name_and_target():
    """``opentelemetry-bootstrap`` and the docs both name the instrumentor
    ``asyncclick``, so the vendoring has to keep that name and that target.
    """
    declared = [
        entry_point
        for entry_point in entry_points(group="opentelemetry_instrumentor")
        if entry_point.name == "asyncclick"
    ]

    assert len(declared) == 1, (
        f"expected exactly one asyncclick entry point: {declared}"
    )
    assert (
        declared[0].value
        == "opentelemetry.instrumentation.asyncclick:AsyncClickInstrumentor"
    )


def test_upstream_records_where_the_source_came_from():
    """A vendored tree with no provenance cannot be diffed against its origin."""
    fields = upstream_fields()

    assert fields["repository"].endswith("opentelemetry-python-contrib")
    assert fields["tag"] == "v0.66b2"
    assert len(fields["commit"]) == 40
    assert fields["supersedes"].startswith("opentelemetry-instrumentation-asyncclick")


def test_the_instruments_extra_gates_the_instrumentor():
    """``get_dist_dependency_conflicts`` reads this extra to skip the instrumentor.

    Without it the gate finds nothing to check, the load reaches ``import
    asyncclick`` and raises, and every injected process without asyncclick logs
    a traceback.
    """
    requirements = distribution("dash0-opentelemetry").requires or []
    gating = [
        requirement
        for requirement in requirements
        if "asyncclick" in requirement and "instruments" in requirement
    ]

    assert len(gating) == 1, (
        f"dash0-opentelemetry must declare asyncclick under the 'instruments' "
        f"extra exactly once: {gating}"
    )


def test_the_instrumentor_records_a_span_for_a_command(monkeypatch):
    """``OTEL_SDK_DISABLED`` is cleared because ``test_distro.py`` leaves it set.

    ``Dash0Distro().configure()`` writes it into the real environment, and
    ``trace.get_tracer`` then hands back a no-op tracer that records nothing.
    """
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    exporter: InMemorySpanExporter = InMemorySpanExporter()
    provider: TracerProvider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    instrumentor: AsyncClickInstrumentor = AsyncClickInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:

        @command()
        async def greet() -> None:
            echo("hello")

        result = asyncio_run(CliRunner().invoke(greet, []))
    finally:
        instrumentor.uninstrument()

    assert result.exit_code == 0
    recorded = exporter.get_finished_spans()
    assert [span.name for span in recorded] == ["greet"]
    assert recorded[0].attributes["process.exit.code"] == 0
