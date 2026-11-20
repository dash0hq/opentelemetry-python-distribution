"""The default ``tracecontext,baggage,xray`` propagators and how they treat headers an
AWS Application Load Balancer rewrites between two instrumented services."""

import os
import subprocess
import sys
from importlib.metadata import entry_points

import pytest
from dash0.opentelemetry._environment_variables import (
    DASH0_DISABLE,
    DASH0_OTEL_COLLECTOR_BASE_URL,
    OTEL_PROPAGATORS,
)
from dash0.opentelemetry.distro import Dash0Distro
from opentelemetry import baggage, trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.propagators.aws import AwsXRayPropagator
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

_TRACEPARENT_TRACE_ID = 0x0AF7651916CD43DD8448EB211C80319C
_TRACEPARENT_SPAN_ID = 0xB7AD6B7169203331
_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

_XRAY_TRACE_ID = 0x5759E988BD862E3FE1BE46A994272793
_XRAY_SPAN_ID = 0x53995C3F42CD8AD8
_XRAY_ROOT = "1-5759e988-bd862e3fe1be46a994272793"


@pytest.fixture(autouse=True)
def _restore_global_textmap(monkeypatch):
    for variable in (OTEL_PROPAGATORS, DASH0_DISABLE, DASH0_OTEL_COLLECTOR_BASE_URL):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "")
    previous = get_global_textmap()
    yield
    set_global_textmap(previous)


@pytest.fixture
def default_propagator(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    Dash0Distro().configure()
    return get_global_textmap()


def _span_context_of(context):
    return trace.get_current_span(context).get_span_context()


def test_xray_propagator_is_registered_as_xray():
    (entry_point,) = entry_points(group="opentelemetry_propagator", name="xray")
    assert entry_point.load() is AwsXRayPropagator


def test_configure_defaults_propagators_to_tracecontext_baggage_xray(
    default_propagator,
):
    assert OTEL_PROPAGATORS not in os.environ
    assert isinstance(default_propagator, CompositePropagator)
    assert [type(p) for p in default_propagator._propagators] == [
        TraceContextTextMapPropagator,
        W3CBaggagePropagator,
        AwsXRayPropagator,
    ]


def test_configure_treats_empty_propagators_as_unset(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_PROPAGATORS, "")

    Dash0Distro().configure()

    assert os.environ[OTEL_PROPAGATORS] == ""
    assert [type(p) for p in get_global_textmap()._propagators] == [
        TraceContextTextMapPropagator,
        W3CBaggagePropagator,
        AwsXRayPropagator,
    ]


def test_configure_does_not_override_explicit_propagators(monkeypatch):
    monkeypatch.setenv(DASH0_OTEL_COLLECTOR_BASE_URL, "http://collector:4318")
    monkeypatch.setenv(OTEL_PROPAGATORS, "tracecontext,baggage")
    installed = get_global_textmap()

    Dash0Distro().configure()

    assert os.environ[OTEL_PROPAGATORS] == "tracecontext,baggage"
    assert get_global_textmap() is installed


def test_configure_sets_no_propagators_when_disabled(monkeypatch):
    monkeypatch.setenv(DASH0_DISABLE, "true")
    installed = get_global_textmap()

    Dash0Distro().configure()

    assert OTEL_PROPAGATORS not in os.environ
    assert get_global_textmap() is installed


def _start_up(propagators):
    """Runs the real start-up sequence, which imports opentelemetry.propagate
    before the distro configures anything, and returns the installed
    propagator names and the OTEL_PROPAGATORS the process ends up with."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in (OTEL_PROPAGATORS, "OTEL_CONFIG_FILE")
    }
    env.update(
        {
            DASH0_OTEL_COLLECTOR_BASE_URL: "http://127.0.0.1:9",
            "OTEL_TRACES_EXPORTER": "none",
            "OTEL_METRICS_EXPORTER": "none",
            "OTEL_LOGS_EXPORTER": "none",
        }
    )
    if propagators is not None:
        env[OTEL_PROPAGATORS] = propagators
    script = (
        "import os\n"
        "from opentelemetry.instrumentation.auto_instrumentation import initialize\n"
        "initialize()\n"
        "from opentelemetry.propagate import get_global_textmap\n"
        "print(','.join(type(p).__name__ for p in get_global_textmap()._propagators))\n"
        "print(os.environ.get('OTEL_PROPAGATORS', '<unset>'))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )

    names, environment_value = result.stdout.strip().splitlines()[-2:]
    return names.split(","), environment_value


@pytest.mark.parametrize(
    ("propagators", "expected"),
    [
        (
            None,
            [
                "TraceContextTextMapPropagator",
                "W3CBaggagePropagator",
                "AwsXRayPropagator",
            ],
        ),
        (
            "tracecontext,baggage",
            ["TraceContextTextMapPropagator", "W3CBaggagePropagator"],
        ),
        ("xray", ["AwsXRayPropagator"]),
    ],
)
def test_auto_instrumentation_installs_effective_propagators(propagators, expected):
    names, _ = _start_up(propagators)

    assert names == expected


def test_auto_instrumentation_leaves_propagators_variable_unset():
    # Child processes inherit the environment and may not know "xray".
    _, environment_value = _start_up(None)

    assert environment_value == "<unset>"


def test_xray_wins_when_both_headers_are_present(default_propagator):
    context = default_propagator.extract(
        {
            "traceparent": _TRACEPARENT,
            "X-Amzn-Trace-Id": f"Root={_XRAY_ROOT};Parent=53995c3f42cd8ad8;Sampled=1",
        }
    )

    span_context = _span_context_of(context)
    assert span_context.trace_id == _XRAY_TRACE_ID
    assert span_context.span_id == _XRAY_SPAN_ID
    assert span_context.trace_flags.sampled


def test_xray_tolerates_alb_rewritten_header(default_propagator):
    # An ALB keeps Root and Parent from the incoming header and adds Self, and
    # other services may add fields such as Lineage.
    header = (
        "Self=1-67891234-12456789abcdef012345678;"
        f"Root={_XRAY_ROOT};Parent=53995c3f42cd8ad8;Sampled=1;"
        "Lineage=a87bd80c:1|68fd508a:5"
    )

    context = default_propagator.extract(
        {"traceparent": _TRACEPARENT, "X-Amzn-Trace-Id": header}
    )

    span_context = _span_context_of(context)
    assert span_context.trace_id == _XRAY_TRACE_ID
    assert span_context.span_id == _XRAY_SPAN_ID


def test_root_only_header_keeps_tracecontext(default_propagator):
    # An ALB adds a fresh Root without a Parent when the request arrives with
    # no X-Amzn-Trace-Id. That header must not replace the traceparent context.
    context = default_propagator.extract(
        {
            "traceparent": _TRACEPARENT,
            "X-Amzn-Trace-Id": "Root=1-67891233-abcdef012345678912345678",
        }
    )

    span_context = _span_context_of(context)
    assert span_context.trace_id == _TRACEPARENT_TRACE_ID
    assert span_context.span_id == _TRACEPARENT_SPAN_ID
    assert span_context.is_remote


def test_root_only_header_alone_extracts_no_parent(default_propagator):
    context = default_propagator.extract(
        {"X-Amzn-Trace-Id": "Root=1-67891233-abcdef012345678912345678"}
    )

    assert not _span_context_of(context).is_valid


def test_inject_writes_both_headers_with_a_parent(default_propagator):
    span_context = SpanContext(
        trace_id=_TRACEPARENT_TRACE_ID,
        span_id=_TRACEPARENT_SPAN_ID,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    carrier = {}

    default_propagator.inject(
        carrier, context=trace.set_span_in_context(NonRecordingSpan(span_context))
    )

    assert carrier["traceparent"] == _TRACEPARENT
    assert carrier["X-Amzn-Trace-Id"] == (
        "Root=1-0af76519-16cd43dd8448eb211c80319c;Parent=b7ad6b7169203331;Sampled=1"
    )


def test_trace_survives_an_alb_between_two_services(default_propagator):
    upstream = SpanContext(
        trace_id=_TRACEPARENT_TRACE_ID,
        span_id=_TRACEPARENT_SPAN_ID,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    carrier = {}
    default_propagator.inject(
        carrier, context=trace.set_span_in_context(NonRecordingSpan(upstream))
    )
    carrier["X-Amzn-Trace-Id"] = (
        "Self=1-67891234-12456789abcdef012345678;" + carrier["X-Amzn-Trace-Id"]
    )

    downstream = _span_context_of(default_propagator.extract(carrier))

    assert downstream.trace_id == upstream.trace_id
    assert downstream.span_id == upstream.span_id


def test_baggage_round_trips(default_propagator):
    carrier = {}
    default_propagator.inject(carrier, context=baggage.set_baggage("tenant", "acme"))

    assert carrier["baggage"] == "tenant=acme"
    assert baggage.get_baggage("tenant", default_propagator.extract(carrier)) == "acme"
