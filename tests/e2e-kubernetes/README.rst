=============================
Kubernetes end-to-end test
=============================

What this proves that no unit test can
======================================

Every other test in this repository stubs the things that only exist in a real
cluster. The Kubernetes detector reads ``/etc/hosts`` and ``/proc/self/cgroup``,
the service-name fallback depends on how the process was actually started, and
the injected tree only exists once something has built it. This test builds the
tree, puts it on an application's ``PYTHONPATH`` through an init container, and
reads back what a collector actually received.

The application under test, ``app/checkout.py``, has no OpenTelemetry
dependency, imports nothing from the distribution, and is started with plain
``python /app/checkout.py``. Any span it produces therefore proves the injection
worked end to end. The file is named ``checkout.py`` so the entrypoint-derived
``service.name`` fallback has a value to find.

Both configuration paths run side by side
=========================================

``app-environment`` sets only ``PYTHONPATH`` and ``OTEL_EXPORTER_OTLP_ENDPOINT``.
It exercises the bridge in ``sitecustomize.py`` that copies
``OTEL_EXPORTER_OTLP_ENDPOINT`` into ``DASH0_OTEL_COLLECTOR_BASE_URL``, without
which the distribution deactivates itself.

``app-declarative`` adds ``OTEL_CONFIG_FILE`` pointing at a ConfigMap that names
the three ``dash0_*`` detectors. Running both against one collector is what lets
the suite compare the two resources key by key.

``app-installed`` runs the same program a third way. ``app-installed/`` carries
a ``pyproject.toml`` declaring the distribution ``checkout-service`` 2.4.0 with
a ``checkout`` console script, and the image installs it rather than copying a
file. The deployment reports ``service.name=checkout-service`` and
``service.version=2.4.0``, where ``app-environment`` running the identical
program as a plain script reports ``service.name=checkout`` and no version.
That pair is the proof for the package-metadata detection, and no unit test can
make it, because it depends on how the process was really started.

Why the declarative manifest declares a propagator
==================================================

``manifests/30-app-declarative.yaml`` declares a ``propagator`` with
``tracecontext`` and ``baggage``. The schema allows omitting it, and a file
without it installs a noop propagator, so no trace context is read from an
incoming request or written to an outgoing one, and traces break at every
service boundary. Every declarative config file shipped for this distribution
declares the block for that reason, which is what ``docs/resource-detection.md``
tells users to do, so the manifest here matches the documented example.

Running it
==========

``kubectl``, ``docker`` and ``kind`` must be available, and the Docker daemon
must be running. Nothing needs ``sudo``. From the repository root::

    make e2e-kubernetes

The cluster is created if it does not already exist and is left running
afterwards, so a second run reuses it and only rebuilds what changed. To remove
it::

    make e2e-kubernetes-clean

On NixOS, where ``kind`` is not on ``PATH``, point the suite at a store path::

    export KIND_BINARY=$(nix build nixpkgs#kind --no-link --print-out-paths)/bin/kind

In CI
=====

``.github/workflows/e2e-kubernetes.yml`` runs the same ``make e2e-kubernetes``
on every push to ``main``, on any pull request touching ``packages/``,
``tests/e2e-kubernetes/`` or the ``Makefile``, and on demand through
``workflow_dispatch``. ``helm/kind-action`` creates the cluster under the name
the ``E2E_CLUSTER`` default already uses, so the suite finds it and reuses it.
A failing run dumps the pod descriptions and the last 200 log lines of every
container before the job ends.

Every image the suite pulls names an exact tag, the collector included, and the
``docker`` entry in ``.github/dependabot.yml`` watches the three directories
that name one. The two ``dash0-e2e-*:test`` images are built from this checkout
and exist in no registry, so that entry ignores them.

Exporting to a real Dash0 organization
======================================

The assertions read a file the collector writes, so the suite is complete
without any credentials. Setting both ``DASH0_ENDPOINT`` and
``DASH0_AUTH_TOKEN`` adds a second ``otlphttp`` exporter to the collector
pipeline, so the same telemetry also reaches a real backend::

    export DASH0_ENDPOINT=https://ingress.eu-west-1.aws.dash0.com
    export DASH0_AUTH_TOKEN=auth_...
    make e2e-kubernetes

``collector_config`` in ``tests/cluster.py`` adds that exporter only when both
variables are set, so a missing token degrades to the file-only pipeline rather
than failing the run.

Known divergence between the two paths
======================================

``telemetry.auto.version`` appears on the environment path and not on the
declarative path. ``opentelemetry-instrument`` passes
``auto_instrumentation_version`` to the configurator, and with
``OTEL_CONFIG_FILE`` set the configurator logs that it is ignoring the argument
and builds the resource from the file alone.
``test_the_declarative_path_drops_telemetry_auto_version`` asserts the gap on
purpose, so that closing it anywhere upstream fails this test rather than
passing unnoticed.

``service.instance.id`` differs because it is generated per process, which
``test_both_paths_agree_on_service_instance_id_being_per_process`` asserts.

Layout
======

================================  ============================================
Path                              Contents
================================  ============================================
``app/``                          The uninstrumented Flask application and its
                                  image, run as a plain script.
``app-installed/``                The same application packaged as a
                                  distribution and started through its console
                                  script.
``instrumentation/Dockerfile``    Builds the injectable tree. Its build context
                                  is the repository root, so it installs the
                                  distribution from this checkout rather than
                                  from an index. It then copies
                                  ``sitecustomize.py`` and
                                  ``all-dependencies.txt`` out of the
                                  installed tree, the two copies a consumer
                                  makes.
``manifests/``                    Namespace, collector, both applications and
                                  the traffic job, applied in filename order.
``tests/cluster.py``              Wrappers over ``kind``, ``kubectl`` and
                                  ``docker``. No Kubernetes client dependency.
``tests/conftest.py``             The session fixture that brings all of it up
                                  once.
================================  ============================================

The collector Deployment carries a second ``busybox`` container sharing the
``output`` volume, because the collector image is distroless and has no shell to
read the exported file with.
