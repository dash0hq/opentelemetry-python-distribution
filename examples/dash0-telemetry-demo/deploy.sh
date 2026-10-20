#!/usr/bin/env bash
set -euo pipefail

: "${DASH0_ENDPOINT:?set DASH0_ENDPOINT, e.g. https://ingress.eu-west-1.aws.dash0.com}"
: "${DASH0_AUTH_TOKEN:?set DASH0_AUTH_TOKEN}"
DASH0_DATASET="${DASH0_DATASET:-default}"

CLUSTER="${E2E_CLUSTER:-dash0-python-e2e}"
KIND="${KIND_BINARY:-kind}"
CONTEXT="kind-${CLUSTER}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"

if ! "${KIND}" get clusters | grep -qx "${CLUSTER}"; then
  "${KIND}" create cluster --name "${CLUSTER}" --wait 180s
fi

docker build -q -t dash0-demo-instrumentation:latest \
  -f "${REPO_ROOT}/tests/e2e-kubernetes/instrumentation/Dockerfile" "${REPO_ROOT}"
docker build -q -t dash0-demo-storefront:latest -f "${HERE}/Dockerfile" "${HERE}"
docker build -q -t dash0-demo-traffic:latest -f "${HERE}/Dockerfile.traffic" "${HERE}"

for image in dash0-demo-instrumentation dash0-demo-storefront dash0-demo-traffic; do
  "${KIND}" load docker-image --name "${CLUSTER}" "${image}:latest"
done

kubectl --context "${CONTEXT}" apply -f "${HERE}/k8s/00-namespace.yaml"

kubectl --context "${CONTEXT}" -n dash0-demo create secret generic dash0-credentials \
  --from-literal=DASH0_ENDPOINT="${DASH0_ENDPOINT}" \
  --from-literal=DASH0_AUTH_TOKEN="${DASH0_AUTH_TOKEN}" \
  --from-literal=DASH0_DATASET="${DASH0_DATASET}" \
  --dry-run=client -o yaml | kubectl --context "${CONTEXT}" apply -f -

kubectl --context "${CONTEXT}" apply -f "${HERE}/k8s/"
kubectl --context "${CONTEXT}" -n dash0-demo rollout restart deployment/collector
kubectl --context "${CONTEXT}" -n dash0-demo rollout status deployment/collector --timeout=180s
kubectl --context "${CONTEXT}" -n dash0-demo rollout status deployment/storefront --timeout=300s
kubectl --context "${CONTEXT}" -n dash0-demo rollout status deployment/traffic --timeout=180s

echo
echo "Deployed. Telemetry is flowing to ${DASH0_ENDPOINT} (dataset ${DASH0_DATASET})."
echo "Follow the storefront with:"
echo "  kubectl --context ${CONTEXT} -n dash0-demo logs -l app=storefront -f --tail=20"
