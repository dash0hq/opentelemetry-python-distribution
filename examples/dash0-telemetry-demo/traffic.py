"""Continuous, uneven traffic, so the dashboards have a shape to show.

Even traffic produces flat charts. This spreads load across the catalog with
different weights, varies the rate over a slow cycle so panels show a rising
and falling line rather than a constant one, and restocks periodically so the
run does not degenerate into nothing but out-of-stock rejections.

It is a client, not a service, so it carries no OpenTelemetry code at all. The
distribution's requests instrumentation gives it client spans, and those join
the storefront's server spans into one trace through context propagation.
"""

from logging import INFO, basicConfig, getLogger
from math import pi, sin
from os import environ
from random import Random
from time import monotonic, sleep

from requests import RequestException, post

TARGET: str = environ.get(
    "TARGET", "http://storefront.dash0-demo.svc.cluster.local:8080"
)
CYCLE_SECONDS: float = float(environ.get("CYCLE_SECONDS", "180"))
BASE_DELAY: float = float(environ.get("BASE_DELAY", "0.35"))
RESTOCK_EVERY: int = int(environ.get("RESTOCK_EVERY", "120"))

WEIGHTED_CATALOG: tuple[tuple[str, int], ...] = (
    ("running-shoes", 30),
    ("cast-iron-pan", 22),
    ("desk-lamp", 18),
    ("rain-jacket", 14),
    ("espresso-machine", 10),
    ("standing-desk", 6),
)

logger = getLogger("traffic")
random = Random()


def _pick_sku() -> str:
    """Choose a product, with the popular ones chosen more often."""
    total = sum(weight for _, weight in WEIGHTED_CATALOG)
    threshold = random.randint(1, total)
    running = 0
    for sku, weight in WEIGHTED_CATALOG:
        running += weight
        if running >= threshold:
            return sku
    return WEIGHTED_CATALOG[0][0]


def main() -> None:
    basicConfig(level=INFO, format="%(levelname)s %(name)s %(message)s")
    logger.info("driving traffic at %s", TARGET)

    started = monotonic()
    sent = 0
    outcomes: dict[int, int] = {}

    while True:
        sku = _pick_sku()
        quantity = random.randint(1, 4)
        try:
            response = post(f"{TARGET}/checkout/{sku}?quantity={quantity}", timeout=10)
            outcomes[response.status_code] = outcomes.get(response.status_code, 0) + 1
        except RequestException as error:
            logger.warning("request to %s failed: %s", sku, error)
            sleep(2)
            continue

        sent += 1
        if sent % RESTOCK_EVERY == 0:
            try:
                post(f"{TARGET}/restock", timeout=10)
                logger.info(
                    "restocked after %s orders; outcomes so far %s", sent, outcomes
                )
            except RequestException as error:
                logger.warning("restock failed: %s", error)

        phase = sin((monotonic() - started) / CYCLE_SECONDS * 2 * pi)
        sleep(max(0.05, BASE_DELAY * (1.0 + 0.8 * phase)))


if __name__ == "__main__":
    main()
