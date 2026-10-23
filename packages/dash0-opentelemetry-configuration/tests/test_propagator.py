"""Checks on a deliberate divergence from upstream, not on configuration semantics.

Upstream builds ``CompositePropagator([])`` for a configuration file that omits
``propagator``. That object is not the noop propagator the schema promises: its
``extract`` returns the context it was handed, so a caller that passes none
receives ``None``. Instrumentation attaches that ``None`` as the current
context, and every later read of the context fails. The fork returns a real
noop propagator instead, and these tests pin that behavior until upstream does
the same.
"""

from opentelemetry._configuration._propagator import (
    configure_propagator,
    create_propagator,
)
from opentelemetry._configuration.models import Propagator as PropagatorConfig
from opentelemetry._configuration.models import (
    TextMapPropagator as TextMapPropagatorConfig,
)
from opentelemetry.context import attach, detach, get_current
from opentelemetry.context.context import Context
from opentelemetry.propagate import extract
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)


def test_a_config_without_a_propagator_extracts_a_root_context() -> None:
    propagator = create_propagator(None)

    extracted = propagator.extract({})

    assert extracted is not None
    assert isinstance(extracted, Context)


def test_a_config_whose_propagator_list_is_empty_extracts_a_root_context() -> None:
    propagator = create_propagator(PropagatorConfig(composite=[]))

    assert isinstance(propagator.extract({}), Context)


def test_a_composite_list_naming_none_extracts_a_root_context() -> None:
    propagator = create_propagator(PropagatorConfig(composite_list="none"))

    assert isinstance(propagator.extract({}), Context)


def test_the_noop_propagator_preserves_a_context_it_is_given() -> None:
    propagator = create_propagator(None)
    given: Context = Context({"key": "value"})

    assert propagator.extract({}, given) is given


def test_the_noop_propagator_writes_nothing_and_declares_no_fields() -> None:
    propagator = create_propagator(None)
    carrier: dict[str, str] = {}

    propagator.inject(carrier)

    assert carrier == {}
    assert propagator.fields == set()


def test_a_configured_propagator_is_still_composed() -> None:
    config = PropagatorConfig(composite=[TextMapPropagatorConfig(tracecontext={})])

    propagator = create_propagator(config)

    assert isinstance(propagator, CompositePropagator)
    assert [type(each) for each in propagator._propagators] == [
        TraceContextTextMapPropagator
    ]


def test_attaching_what_the_global_propagator_extracts_keeps_a_usable_context() -> None:
    """Reproduce the failure a configuration file without ``propagator`` caused.

    ``opentelemetry.instrumentation.utils._start_internal_or_server_span``
    attaches the result of ``extract`` and later code reads the current
    context. With ``None`` attached that read raised
    ``AttributeError: 'NoneType' object has no attribute 'get'``.
    """
    configure_propagator(None)
    token = attach(extract({}))
    try:
        current = get_current()
        assert current is not None
        assert current.get("missing") is None
    finally:
        detach(token)
