"""Exercise the vendored asyncclick instrumentation and exit.

This is the only case whose instrumentor ships as source inside
``dash0-opentelemetry`` rather than as an ``opentelemetry-instrumentation-*``
dependency.
"""

from asyncclick import command, echo, option


@command()
@option("--item-id", type=int, required=True)
async def checkout(item_id: int) -> None:
    echo(f"checked out item {item_id}")


checkout(args=["--item-id", "7"], prog_name="checkout", standalone_mode=False)
