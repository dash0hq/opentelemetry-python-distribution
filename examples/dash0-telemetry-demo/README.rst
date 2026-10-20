============================================
Telemetry demo: all three signals on purpose
============================================

The sibling example at ``examples/dash0-distro-flask`` shows the minimum case,
an application with no OpenTelemetry code at all. This one is the other end: it
adds the telemetry that auto-instrumentation cannot invent, because only the
application knows what an order is worth or which payment method was refused.

It exists to give a Dash0 dashboard something worth charting.

What it emits
=============

**Five custom metrics**, none of which auto-instrumentation could produce:

=============================== ================= =========================================
Metric                          Instrument        Attributes
=============================== ================= =========================================
``storefront.orders.created``   Counter           ``order.status``, ``item.category``,
                                                  ``payment.method``
``storefront.order.value``      Histogram (USD)   ``item.category``, ``payment.method``
``storefront.cart.items``       Histogram         ``item.category``
``storefront.inventory.level``  UpDownCounter     ``item.sku``
``storefront.payment.declines`` Counter           ``payment.method``, ``decline.reason``
=============================== ================= =========================================

``order.status`` takes ``confirmed``, ``payment_declined`` or ``rejected``, so a
single counter answers both throughput and failure-rate questions.

**Nested traces.** Each checkout produces a ``checkout_pipeline`` span with
``reserve_inventory`` and ``charge_payment`` beneath it, carrying span
attributes, span events (``inventory.low``, ``inventory.exhausted``,
``checkout.slow_path``) and an error status on the failure paths. The traffic
generator is instrumented too, so its client span and the storefront's server
span join into one distributed trace.

**Logs at three severities**, bridged from the standard library and stamped
with the active trace and span id. A representative minute produced 321 INFO,
16 WARN and 8 ERROR records.

Traffic is deliberately uneven: the rate follows a slow sine cycle, products
are weighted so some sell more than others, roughly 8 percent of payments are
declined, 5 percent of checkouts take the slow path, and stock runs out until
the periodic restock. Flat inputs make flat dashboards.

The one rule an application using the API has to follow
=======================================================

``storefront.py`` depends on ``opentelemetry-api`` and nothing else from
OpenTelemetry. That is deliberate and it is allowed: ``opentelemetry-api`` and
``opentelemetry-semantic-conventions`` are the two names the injector's
double-instrumentation check ignores, at ``sitecustomize.py:42-44``. The API on
its own records into a no-op implementation, so this file also runs correctly
with no instrumentation at all.

**The version has to match the injected SDK.** ``pyproject.toml`` pins
``opentelemetry-api==1.44.0``. The first version of this example left it
unpinned, ``pip`` installed 1.45.1, and the distribution stood down completely
and silently: ``opentelemetry-sdk==1.44.0`` in the injected tree requires
``opentelemetry-api==1.44.0``, the conflict check saw 1.45.1 on the application
side, and it deactivated rather than risk importing mismatched halves. The
application kept serving traffic and produced no telemetry whatsoever.

Set ``OTEL_INJECTOR_LOG_LEVEL=debug`` to see which requirement decided it. This
is the cost of using the API directly, and it is why an application that only
wants auto-instrumentation should depend on no OpenTelemetry package at all.

Running it
==========

Needs ``kubectl``, ``docker`` and ``kind``, and a Dash0 auth token::

    export DASH0_ENDPOINT=https://ingress.eu-west-1.aws.dash0.com
    export DASH0_AUTH_TOKEN=auth_...
    export DASH0_DATASET=default
    ./deploy.sh

The script creates the cluster if it is missing, builds the three images, loads
them, writes the credentials into a Secret named ``dash0-credentials`` and
applies everything in ``k8s/``. The token only ever reaches the cluster through
that Secret, so it stays out of the manifests and out of git.

Follow it with::

    kubectl --context kind-dash0-python-e2e -n dash0-demo logs -l app=storefront -f --tail=20

Remove it with::

    kubectl --context kind-dash0-python-e2e delete namespace dash0-demo

What runs
=========

======================= ====================================================
Workload                Role
======================= ====================================================
``storefront``          Two replicas of the application, injected through an
                        init container, reporting
                        ``service.name=dash0-telemetry-demo`` and
                        ``service.version=1.0.0`` from its own package
                        metadata.
``traffic``             The load generator, instrumented as well, so traces
                        span both services.
``collector``           Receives OTLP and forwards to Dash0.
======================= ====================================================

``service.name`` is not configured anywhere for the storefront. It is read from
the installed distribution, because the container starts the ``storefront``
console script that ``pyproject.toml`` declares.
