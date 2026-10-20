"""A storefront that emits all three signals on purpose.

The sibling example at ``examples/dash0-distro-flask`` shows the minimum: an
application with no OpenTelemetry code at all, instrumented entirely from the
outside. This one is the opposite end. It adds the custom telemetry that
auto-instrumentation cannot invent, because only the application knows what an
order is worth or which payment method failed.

It depends on ``opentelemetry-api`` and nothing else from OpenTelemetry. The
API alone records telemetry into a no-op implementation, so this file runs
uninstrumented without raising. The SDK, the exporters and the Flask
instrumentation all arrive from the injected tree at runtime, which is why
``opentelemetry-api`` and ``opentelemetry-semantic-conventions`` are the two
names the injector's double-instrumentation check ignores, at
``sitecustomize.py:42-44``.

Logs are plain ``logging``. There is no logs API for applications to call, by
design: the distribution's logging instrumentation bridges the standard library
into OTLP and stamps each record with the active trace and span id.
"""

from logging import INFO, Formatter, StreamHandler, getLogger
from os import environ
from random import Random
from sys import stdout
from time import sleep

from flask import Flask, jsonify, request
from opentelemetry.metrics import get_meter
from opentelemetry.trace import SpanKind, StatusCode, get_tracer

SERVICE_PORT: int = int(environ.get("PORT", "8080"))
SLOW_REQUEST_SECONDS: float = 1.4
LOW_STOCK_THRESHOLD: int = 12

CATALOG: dict[str, dict[str, object]] = {
    "espresso-machine": {"category": "kitchen", "price": 449.0, "stock": 40},
    "cast-iron-pan": {"category": "kitchen", "price": 59.5, "stock": 120},
    "running-shoes": {"category": "apparel", "price": 129.0, "stock": 80},
    "rain-jacket": {"category": "apparel", "price": 189.0, "stock": 25},
    "desk-lamp": {"category": "home-office", "price": 74.0, "stock": 60},
    "standing-desk": {"category": "home-office", "price": 899.0, "stock": 10},
}

PAYMENT_METHODS: tuple[str, ...] = ("card", "paypal", "bank-transfer")

DECLINE_REASONS: tuple[str, ...] = (
    "insufficient_funds",
    "card_expired",
    "issuer_unreachable",
    "fraud_suspected",
)

logger = getLogger("storefront")
tracer = get_tracer("storefront", "1.0.0")
meter = get_meter("storefront", "1.0.0")

orders_created = meter.create_counter(
    "storefront.orders.created",
    unit="{order}",
    description="Orders that reached a terminal state, successful or not",
)
order_value = meter.create_histogram(
    "storefront.order.value",
    unit="USD",
    description="Monetary value of each order that was paid for",
)
cart_size = meter.create_histogram(
    "storefront.cart.items",
    unit="{item}",
    description="Number of units in each submitted cart",
)
inventory_level = meter.create_up_down_counter(
    "storefront.inventory.level",
    unit="{item}",
    description="Units remaining in stock, decremented as orders are placed",
)
payment_declines = meter.create_counter(
    "storefront.payment.declines",
    unit="{decline}",
    description="Payment attempts refused, by the reason the processor gave",
)

app = Flask(__name__)
random = Random(20261020)


def _reserve_inventory(sku: str, quantity: int) -> bool:
    """Take units out of stock, reporting whether there were enough."""
    with tracer.start_as_current_span("reserve_inventory") as span:
        item = CATALOG[sku]
        stock = int(item["stock"])
        span.set_attribute("item.sku", sku)
        span.set_attribute("item.stock_before", stock)
        span.set_attribute("order.quantity", quantity)

        if stock < quantity:
            span.add_event(
                "inventory.exhausted", {"item.sku": sku, "item.stock": stock}
            )
            span.set_status(StatusCode.ERROR, "out of stock")
            logger.warning(
                "cannot reserve %s units of %s, only %s left", quantity, sku, stock
            )
            return False

        item["stock"] = stock - quantity
        inventory_level.add(-quantity, {"item.sku": sku})
        remaining = int(item["stock"])
        span.set_attribute("item.stock_after", remaining)

        if remaining < LOW_STOCK_THRESHOLD:
            span.add_event("inventory.low", {"item.sku": sku, "item.stock": remaining})
            logger.warning(
                "stock for %s is down to %s units, below the threshold of %s",
                sku,
                remaining,
                LOW_STOCK_THRESHOLD,
            )
        return True


def _charge_payment(method: str, amount: float) -> str | None:
    """Attempt the charge, returning the decline reason or ``None``."""
    with tracer.start_as_current_span("charge_payment", kind=SpanKind.CLIENT) as span:
        span.set_attribute("payment.method", method)
        span.set_attribute("payment.amount", amount)
        sleep(random.uniform(0.01, 0.06))

        if random.random() >= 0.08:
            span.set_attribute("payment.outcome", "approved")
            return None

        reason = random.choice(DECLINE_REASONS)
        span.set_attribute("payment.outcome", "declined")
        span.set_attribute("payment.decline_reason", reason)
        span.set_status(StatusCode.ERROR, f"payment declined: {reason}")
        payment_declines.add(1, {"payment.method": method, "decline.reason": reason})
        return reason


@app.get("/")
def health() -> tuple[str, int]:
    return "ok", 200


@app.get("/catalog")
def catalog() -> tuple[object, int]:
    with tracer.start_as_current_span("load_catalog") as span:
        span.set_attribute("catalog.size", len(CATALOG))
        return jsonify(CATALOG), 200


@app.post("/checkout/<sku>")
def checkout(sku: str) -> tuple[object, int]:
    """One order, start to finish, with every signal it can produce."""
    if sku not in CATALOG:
        logger.error("checkout requested for unknown sku %s", sku)
        return jsonify({"error": "unknown sku"}), 404

    quantity = int(request.args.get("quantity", random.randint(1, 4)))
    method = request.args.get("payment", random.choice(PAYMENT_METHODS))
    item = CATALOG[sku]
    category = str(item["category"])
    amount = round(float(item["price"]) * quantity, 2)

    with tracer.start_as_current_span("checkout_pipeline") as span:
        span.set_attribute("item.sku", sku)
        span.set_attribute("item.category", category)
        span.set_attribute("order.quantity", quantity)
        span.set_attribute("order.amount", amount)
        span.set_attribute("payment.method", method)

        cart_size.record(quantity, {"item.category": category})

        if not _reserve_inventory(sku, quantity):
            orders_created.add(
                1,
                {
                    "order.status": "rejected",
                    "item.category": category,
                    "payment.method": method,
                },
            )
            return jsonify({"error": "out of stock", "sku": sku}), 409

        if random.random() < 0.05:
            span.add_event(
                "checkout.slow_path", {"delay.seconds": SLOW_REQUEST_SECONDS}
            )
            logger.warning("checkout for %s hit the slow path", sku)
            sleep(SLOW_REQUEST_SECONDS)

        decline_reason = _charge_payment(method, amount)
        if decline_reason is not None:
            span.set_status(StatusCode.ERROR, "payment declined")
            orders_created.add(
                1,
                {
                    "order.status": "payment_declined",
                    "item.category": category,
                    "payment.method": method,
                },
            )
            logger.error(
                "payment of %.2f USD by %s declined for %s: %s",
                amount,
                method,
                sku,
                decline_reason,
            )
            return jsonify({"error": "payment declined", "reason": decline_reason}), 402

        order_value.record(
            amount, {"item.category": category, "payment.method": method}
        )
        orders_created.add(
            1,
            {
                "order.status": "confirmed",
                "item.category": category,
                "payment.method": method,
            },
        )
        logger.info(
            "order confirmed: %s x%s for %.2f USD via %s", sku, quantity, amount, method
        )
        return jsonify({"sku": sku, "quantity": quantity, "amount": amount}), 201


@app.post("/restock")
def restock() -> tuple[object, int]:
    """Put the catalog back, so a long run keeps producing orders."""
    with tracer.start_as_current_span("restock_catalog") as span:
        restored = 0
        for sku, item in CATALOG.items():
            target = 40 if item["category"] != "home-office" else 20
            missing = target - int(item["stock"])
            if missing > 0:
                item["stock"] = target
                inventory_level.add(missing, {"item.sku": sku})
                restored += missing
        span.set_attribute("inventory.units_restored", restored)
        logger.info("restocked %s units across %s skus", restored, len(CATALOG))
        return jsonify({"restored": restored}), 200


def main() -> None:
    handler = StreamHandler(stdout)
    handler.setFormatter(Formatter("%(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(INFO)

    for sku, item in CATALOG.items():
        inventory_level.add(int(item["stock"]), {"item.sku": sku})

    logger.info("storefront starting on port %s", SERVICE_PORT)
    app.run(host="0.0.0.0", port=SERVICE_PORT)


if __name__ == "__main__":
    main()
