# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry._configuration._common import load_entry_point
from opentelemetry._configuration.models import (
    Propagator as PropagatorConfig,
)
from opentelemetry._configuration.models import (
    TextMapPropagator as TextMapPropagatorConfig,
)
from opentelemetry.context.context import Context
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagators.textmap import (
    CarrierT,
    Getter,
    Setter,
    TextMapPropagator,
    default_getter,
    default_setter,
)
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

# Propagators bundled with the SDK — no entry point lookup needed.
_PROPAGATOR_REGISTRY: dict[str, type[TextMapPropagator]] = {
    "tracecontext": TraceContextTextMapPropagator,
    "baggage": W3CBaggagePropagator,
}


class _NoOpTextMapPropagator(TextMapPropagator):
    """A propagator that reads nothing from a carrier and writes nothing to it.

    The schema says a configuration file that omits ``propagator`` gets a noop
    propagator. ``CompositePropagator([])`` is not one. Its ``extract`` returns
    the context it was handed, so a caller that passes none gets ``None`` back
    where every other propagator returns a root context, and instrumentation
    that attaches the result then fails on every request.
    """

    def extract(
        self,
        carrier: CarrierT,
        context: Context | None = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> Context:
        return Context() if context is None else context

    def inject(
        self,
        carrier: CarrierT,
        context: Context | None = None,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        return None

    @property
    def fields(self) -> set[str]:
        return set()


def _propagators_from_textmap_config(
    config: TextMapPropagatorConfig,
) -> list[TextMapPropagator]:
    """Resolve a TextMapPropagator config to a list of propagators.

    Known names (tracecontext, baggage) are bootstrapped directly via
    _PROPAGATOR_REGISTRY. Known schema fields not in the registry (b3, b3multi)
    and unknown plugin names from additional_properties are loaded via the
    ``opentelemetry_propagator`` entry point group.
    """
    result: list[TextMapPropagator] = []
    for name, cls in _PROPAGATOR_REGISTRY.items():
        if getattr(config, name, None) is not None:
            result.append(cls())

    # Known schema fields not in registry (b3, b3multi) — loaded via entry point
    for name in ("b3", "b3multi"):
        if getattr(config, name, None) is not None:
            result.append(load_entry_point("opentelemetry_propagator", name)())

    # Plugin propagators from additional_properties
    for name, plugin_config in config.additional_properties.items():
        result.append(
            load_entry_point("opentelemetry_propagator", name)(
                **(plugin_config or {})
            )
        )

    return result


def create_propagator(
    config: PropagatorConfig | None,
) -> TextMapPropagator:
    """Create the propagator described by declarative config.

    If config is None or names no propagator, returns a noop propagator, which
    is what the schema specifies for a file that omits ``propagator``. Either
    way the env-var-based default propagators are not used, so "what you see is
    what you get" still holds.

    Args:
        config: Propagator config from the parsed config file, or None.

    Returns:
        A CompositePropagator wrapping all configured propagators, or a noop
        propagator when the config names none.
    """
    if config is None:
        return _NoOpTextMapPropagator()

    propagators: dict[type[TextMapPropagator], TextMapPropagator] = {}

    # Process structured composite list
    if config.composite:
        for entry in config.composite:
            for propagator in _propagators_from_textmap_config(entry):
                propagators.setdefault(type(propagator), propagator)

    # Process composite_list (comma-separated propagator names via entry_points)
    if config.composite_list:
        for name in config.composite_list.split(","):
            name = name.strip()
            if not name or name.lower() == "none":
                continue
            propagator = load_entry_point("opentelemetry_propagator", name)()
            propagators.setdefault(type(propagator), propagator)

    if not propagators:
        return _NoOpTextMapPropagator()

    return CompositePropagator(list(propagators.values()))


def configure_propagator(config: PropagatorConfig | None) -> None:
    """Configure the global text map propagator from declarative config.

    Always calls set_global_textmap to override any defaults (including the
    env-var-based tracecontext+baggage default set by the SDK).

    Args:
        config: Propagator config from the parsed config file, or None.
    """
    set_global_textmap(create_propagator(config))
