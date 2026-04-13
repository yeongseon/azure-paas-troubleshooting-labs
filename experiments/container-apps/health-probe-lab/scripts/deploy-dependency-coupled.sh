#!/bin/bash
set -euo pipefail

RG="${RESOURCE_GROUP:-rg-health-probe-lab}"
LOCATION="${LOCATION:-koreacentral}"
ENV_NAME="${ENV_NAME:-cae-health-probe-lab}"
WORKSPACE_NAME="${WORKSPACE_NAME:-law-health-probe-lab}"
ACR_NAME="${ACR_NAME:-acrhealthprobelab$(openssl rand -hex 3)}"
IMAGE_NAME="${IMAGE_NAME:-health-probe-lab}"
IMAGE_TAG="${IMAGE_TAG:-v1}"
IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

DEPENDENCY_APP_NAME="ca-dependency"
DEPENDENCY_URL="http://${DEPENDENCY_APP_NAME}/health"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAB_DIR="${SCRIPT_DIR}/.."
APP_DIR="${LAB_DIR}/app"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "=== Container Apps health probe dependency-coupled lab ==="
echo "Resource group:      ${RG}"
echo "Location:            ${LOCATION}"
echo "Environment:         ${ENV_NAME}"
echo "Log Analytics:       ${WORKSPACE_NAME}"
echo "ACR:                 ${ACR_NAME}"
echo "Image:               ${IMAGE}"

render_env_yaml() {
    for env_var in "$@"; do
        local key="${env_var%%=*}"
        local value="${env_var#*=}"
        printf '            - name: %s\n' "${key}"
        printf '              value: "%s"\n' "${value}"
    done
}

render_probe_yaml() {
    local probe_type="$1"
    local path="$2"
    local initial_delay="$3"
    local period="$4"
    local timeout="$5"
    local failure="$6"

    cat <<EOF
          - type: ${probe_type}
            httpGet:
              path: ${path}
              port: 8080
            initialDelaySeconds: ${initial_delay}
            periodSeconds: ${period}
            timeoutSeconds: ${timeout}
            failureThreshold: ${failure}
EOF
}

write_containerapp_yaml() {
    local app_name="$1"
    local ingress_external="$2"
    shift 2
    local env_vars=("$@")
    local yaml_path="${TMP_DIR}/${app_name}.yaml"

    cat > "${yaml_path}" <<EOF
location: ${LOCATION}
name: ${app_name}
properties:
  managedEnvironmentId: ${ENV_ID}
  configuration:
    activeRevisionsMode: Single
    ingress:
      allowInsecure: false
      external: ${ingress_external}
      targetPort: 8080
      transport: auto
    registries:
      - server: ${ACR_SERVER}
        username: ${ACR_NAME}
        passwordSecretRef: acr-password
    secrets:
      - name: acr-password
        value: "${ACR_PASSWORD}"
  template:
    containers:
      - name: ${app_name}
        image: ${ACR_SERVER}/${IMAGE}
        env:
$(render_env_yaml "${env_vars[@]}")
        probes:
$(render_probe_yaml Startup /startup 5 5 2 12)
$(render_probe_yaml Readiness /ready 5 5 3 3)
$(render_probe_yaml Liveness /live 10 10 3 3)
    scale:
      minReplicas: 1
      maxReplicas: 1
type: Microsoft.App/containerApps
EOF

    printf '%s\n' "${yaml_path}"
}

deploy_from_yaml() {
    local app_name="$1"
    shift
    local ingress_external="$1"
    shift
    local yaml_path
    yaml_path="$(write_containerapp_yaml "${app_name}" "${ingress_external}" "$@")"

    echo "--- Deploying ${app_name} ---"
    az containerapp create \
        --name "${app_name}" \
        --resource-group "${RG}" \
        --environment "${ENV_NAME}" \
        --yaml "${yaml_path}" \
        --output none
}

echo "--- Creating resource group ---"
az group create --name "${RG}" --location "${LOCATION}" --output none

echo "--- Creating Log Analytics workspace ---"
az monitor log-analytics workspace create \
    --resource-group "${RG}" \
    --workspace-name "${WORKSPACE_NAME}" \
    --location "${LOCATION}" \
    --output none

WORKSPACE_ID="$(az monitor log-analytics workspace show --resource-group "${RG}" --workspace-name "${WORKSPACE_NAME}" --query customerId -o tsv)"
WORKSPACE_KEY="$(az monitor log-analytics workspace get-shared-keys --resource-group "${RG}" --workspace-name "${WORKSPACE_NAME}" --query primarySharedKey -o tsv)"

echo "--- Creating Azure Container Registry ---"
az acr create \
    --name "${ACR_NAME}" \
    --resource-group "${RG}" \
    --sku Basic \
    --admin-enabled true \
    --location "${LOCATION}" \
    --output none

echo "--- Building image in ACR ---"
az acr build --registry "${ACR_NAME}" --image "${IMAGE}" "${APP_DIR}" --output none

ACR_SERVER="$(az acr show --name "${ACR_NAME}" --resource-group "${RG}" --query loginServer -o tsv)"
ACR_PASSWORD="$(az acr credential show --name "${ACR_NAME}" --resource-group "${RG}" --query 'passwords[0].value' -o tsv)"

echo "--- Creating Container Apps environment ---"
az containerapp env create \
    --name "${ENV_NAME}" \
    --resource-group "${RG}" \
    --location "${LOCATION}" \
    --logs-destination log-analytics \
    --logs-workspace-id "${WORKSPACE_ID}" \
    --logs-workspace-key "${WORKSPACE_KEY}" \
    --output none

ENV_ID="$(az containerapp env show --name "${ENV_NAME}" --resource-group "${RG}" --query id -o tsv)"

deploy_from_yaml "${DEPENDENCY_APP_NAME}" false \
    "APP_NAME=${DEPENDENCY_APP_NAME}" \
    "APP_MODE=dependency" \
    "DEPENDENCY_HEALTHY=true" \
    "DEPENDENCY_DELAY_MS=0" \
    "DEPENDENCY_FAIL_RATE=0" \
    "STARTUP_DELAY_SECONDS=0"

deploy_from_yaml "ca-dep-baseline" true \
    "APP_NAME=ca-dep-baseline" \
    "APP_MODE=main" \
    "READINESS_CHECK_DEPENDENCY=true" \
    "LIVENESS_CHECK_DEPENDENCY=false" \
    "DEPENDENCY_URL=${DEPENDENCY_URL}" \
    "DEPENDENCY_TIMEOUT_MS=2000" \
    "STARTUP_DELAY_SECONDS=0"

deploy_from_yaml "ca-dep-ready-only" true \
    "APP_NAME=ca-dep-ready-only" \
    "APP_MODE=main" \
    "READINESS_CHECK_DEPENDENCY=true" \
    "LIVENESS_CHECK_DEPENDENCY=false" \
    "DEPENDENCY_URL=${DEPENDENCY_URL}" \
    "DEPENDENCY_TIMEOUT_MS=2000" \
    "STARTUP_DELAY_SECONDS=0"

deploy_from_yaml "ca-dep-both" true \
    "APP_NAME=ca-dep-both" \
    "APP_MODE=main" \
    "READINESS_CHECK_DEPENDENCY=true" \
    "LIVENESS_CHECK_DEPENDENCY=true" \
    "DEPENDENCY_URL=${DEPENDENCY_URL}" \
    "DEPENDENCY_TIMEOUT_MS=2000" \
    "STARTUP_DELAY_SECONDS=0"

deploy_from_yaml "ca-dep-slow" true \
    "APP_NAME=ca-dep-slow" \
    "APP_MODE=main" \
    "READINESS_CHECK_DEPENDENCY=true" \
    "LIVENESS_CHECK_DEPENDENCY=false" \
    "DEPENDENCY_URL=${DEPENDENCY_URL}" \
    "DEPENDENCY_TIMEOUT_MS=1000" \
    "STARTUP_DELAY_SECONDS=0"

deploy_from_yaml "ca-dep-intermittent" true \
    "APP_NAME=ca-dep-intermittent" \
    "APP_MODE=main" \
    "READINESS_CHECK_DEPENDENCY=true" \
    "LIVENESS_CHECK_DEPENDENCY=false" \
    "DEPENDENCY_URL=${DEPENDENCY_URL}" \
    "DEPENDENCY_TIMEOUT_MS=2000" \
    "STARTUP_DELAY_SECONDS=0"

echo ""
echo "=== Deployment complete ==="
for app_name in "${DEPENDENCY_APP_NAME}" ca-dep-baseline ca-dep-ready-only ca-dep-both ca-dep-slow ca-dep-intermittent; do
    fqdn="$(az containerapp show --name "${app_name}" --resource-group "${RG}" --query properties.configuration.ingress.fqdn -o tsv)"
    if [ -n "${fqdn}" ]; then
        echo "${app_name}: https://${fqdn}"
    else
        echo "${app_name}: internal ingress only"
    fi
done

echo ""
echo "=== Dependency toggle commands ==="
echo "Set dependency unhealthy:"
echo "  az containerapp update -n ${DEPENDENCY_APP_NAME} -g ${RG} --set-env-vars APP_NAME=${DEPENDENCY_APP_NAME} APP_MODE=dependency DEPENDENCY_HEALTHY=false DEPENDENCY_DELAY_MS=0 DEPENDENCY_FAIL_RATE=0"
echo "Set dependency slow (2s):"
echo "  az containerapp update -n ${DEPENDENCY_APP_NAME} -g ${RG} --set-env-vars APP_NAME=${DEPENDENCY_APP_NAME} APP_MODE=dependency DEPENDENCY_HEALTHY=true DEPENDENCY_DELAY_MS=2000 DEPENDENCY_FAIL_RATE=0"
echo "Set dependency intermittent (50% failures):"
echo "  az containerapp update -n ${DEPENDENCY_APP_NAME} -g ${RG} --set-env-vars APP_NAME=${DEPENDENCY_APP_NAME} APP_MODE=dependency DEPENDENCY_HEALTHY=true DEPENDENCY_DELAY_MS=0 DEPENDENCY_FAIL_RATE=50"
echo "Restore dependency healthy:"
echo "  az containerapp update -n ${DEPENDENCY_APP_NAME} -g ${RG} --set-env-vars APP_NAME=${DEPENDENCY_APP_NAME} APP_MODE=dependency DEPENDENCY_HEALTHY=true DEPENDENCY_DELAY_MS=0 DEPENDENCY_FAIL_RATE=0"

echo ""
echo "=== Suggested KQL queries ==="
cat <<'EOF'
ContainerAppConsoleLogs_CL
| where ContainerAppName_s in ("ca-dependency", "ca-dep-baseline", "ca-dep-ready-only", "ca-dep-both", "ca-dep-slow", "ca-dep-intermittent")
| where Log_s has_any ("BOOT_START", "STARTUP_COMPLETE", "DEPENDENCY_CHECK_OK", "DEPENDENCY_CHECK_FAIL")
| project TimeGenerated, ContainerAppName_s, RevisionName_s, Log_s
| order by TimeGenerated asc

ContainerAppSystemLogs_CL
| where ContainerAppName_s in ("ca-dependency", "ca-dep-baseline", "ca-dep-ready-only", "ca-dep-both", "ca-dep-slow", "ca-dep-intermittent")
| where Reason_s has_any ("Unhealthy", "Probe", "BackOff", "Restart")
| project TimeGenerated, ContainerAppName_s, Reason_s, Log_s
| order by TimeGenerated desc
EOF
