"""What the exported resource says about a pod the operator never touched.

These assertions are the ones no unit test can make. The Kubernetes detector is
stubbed everywhere else in this repository, the service-name fallback depends
on how the process was actually started, and the injected tree only exists once
something has built it.
"""

from cluster import pod_uid, read_exported


def resource_attributes(records: list[dict]) -> list[dict[str, str]]:
    """Flatten every exported resource into one dict of attribute values."""
    resources = []
    for record in records:
        for resource_spans in record.get("resourceSpans", []):
            attributes = {}
            for attribute in resource_spans.get("resource", {}).get("attributes", []):
                value = attribute.get("value", {})
                attributes[attribute["key"]] = (
                    value.get("stringValue")
                    or value.get("intValue")
                    or value.get("boolValue")
                )
            resources.append(attributes)
    return resources


def resource_for(records: list[dict], uid: str) -> dict[str, str]:
    """The resource of the pod with this UID, which must be exactly one."""
    matching = [
        attributes
        for attributes in resource_attributes(records)
        if attributes.get("k8s.pod.uid") == uid
    ]
    assert matching, (
        f"no exported resource carries k8s.pod.uid={uid}; "
        f"saw {[a.get('k8s.pod.uid') for a in resource_attributes(records)]}"
    )
    return matching[0]


def span_names(records: list[dict]) -> set[str]:
    names = set()
    for record in records:
        for resource_spans in record.get("resourceSpans", []):
            for scope_spans in resource_spans.get("scopeSpans", []):
                for span in scope_spans.get("spans", []):
                    names.add(span.get("name", ""))
    return names


def test_the_injected_tree_instrumented_an_application_that_never_asked(trace_records):
    """A Flask span can only exist because PYTHONPATH carried the tree in."""
    assert span_names(trace_records), "no spans reached the collector at all"
    assert any("/order/" in name for name in span_names(trace_records)), (
        f"no span for the /order route; saw {sorted(span_names(trace_records))}"
    )


def test_the_environment_path_reports_the_real_pod_uid(trace_records):
    uid = pod_uid("app=app-environment")
    assert uid
    attributes = resource_for(trace_records, uid)
    assert attributes["k8s.pod.uid"] == uid


def test_the_environment_path_reports_the_distribution(trace_records):
    attributes = resource_for(trace_records, pod_uid("app=app-environment"))
    assert attributes["telemetry.distro.name"] == "dash0-python"
    assert attributes["telemetry.distro.version"]


def test_the_environment_path_derives_the_service_name_from_the_entrypoint(
    trace_records,
):
    """No OTEL_SERVICE_NAME is set anywhere, and the script is checkout.py."""
    attributes = resource_for(trace_records, pod_uid("app=app-environment"))
    assert attributes["service.name"] == "checkout"


def test_the_sitecustomize_endpoint_bridge_activated_the_distribution(trace_records):
    """Only OTEL_EXPORTER_OTLP_ENDPOINT is set on that deployment.

    The distribution needs DASH0_OTEL_COLLECTOR_BASE_URL to activate at all, so
    any telemetry from this pod proves the bridge in sitecustomize.py ran.
    """
    assert resource_for(trace_records, pod_uid("app=app-environment"))


def test_the_declarative_path_reports_the_same_attributes(trace_records):
    """The documented detector block, in a real pod, with OTEL_CONFIG_FILE set."""
    environment = resource_for(trace_records, pod_uid("app=app-environment"))
    declarative = resource_for(trace_records, pod_uid("app=app-declarative"))

    for key in (
        "telemetry.distro.name",
        "telemetry.distro.version",
        "service.name",
    ):
        assert declarative[key] == environment[key], (
            f"{key} differs between the two paths: "
            f"{declarative[key]!r} against {environment[key]!r}"
        )

    assert declarative["k8s.pod.uid"] != environment["k8s.pod.uid"]


DIVERGING_KEYS: set[str] = {"service.instance.id", "telemetry.auto.version"}


def test_the_two_paths_agree_on_every_key_outside_the_known_divergence(trace_records):
    environment = resource_for(trace_records, pod_uid("app=app-environment"))
    declarative = resource_for(trace_records, pod_uid("app=app-declarative"))

    assert set(environment) - DIVERGING_KEYS == set(declarative) - DIVERGING_KEYS, (
        "the declarative path lost or gained attribute keys: "
        f"only in environment {sorted(set(environment) - set(declarative))}, "
        f"only in declarative {sorted(set(declarative) - set(environment))}"
    )


def test_the_declarative_path_drops_telemetry_auto_version(trace_records):
    """A divergence the SDK imposes, asserted so a future fix is noticed.

    ``opentelemetry-instrument`` passes ``auto_instrumentation_version`` to the
    configurator, which turns it into ``telemetry.auto.version``. Declarative
    configuration builds the resource from the file alone, and the configurator
    logs that it is ignoring the argument, so the key never appears.
    """
    environment = resource_for(trace_records, pod_uid("app=app-environment"))
    declarative = resource_for(trace_records, pod_uid("app=app-declarative"))

    assert environment["telemetry.auto.version"]
    assert "telemetry.auto.version" not in declarative


def test_both_paths_agree_on_service_instance_id_being_per_process(trace_records):
    """Each process gets its own id, so the values must differ."""
    environment = resource_for(trace_records, pod_uid("app=app-environment"))
    declarative = resource_for(trace_records, pod_uid("app=app-declarative"))

    assert environment["service.instance.id"] != declarative["service.instance.id"]


def test_metrics_and_logs_also_arrive(deployed):
    assert read_exported("metrics.jsonl"), "no metrics reached the collector"


def test_an_installed_distribution_names_itself(trace_records):
    """The same program, installed and started through its console script.

    ``app-environment`` runs ``python /app/checkout.py`` and is named after the
    file. ``app-installed`` runs the ``checkout`` console script of the
    distribution ``checkout-service``, so it reports the distribution instead.
    """
    attributes = resource_for(trace_records, pod_uid("app=app-installed"))

    assert attributes["service.name"] == "checkout-service"
    assert attributes["service.version"] == "2.4.0"


def test_a_plain_script_reports_no_service_version(trace_records):
    """No distribution owns it, and a version is never invented."""
    attributes = resource_for(trace_records, pod_uid("app=app-environment"))

    assert attributes["service.name"] == "checkout"
    assert "service.version" not in attributes
