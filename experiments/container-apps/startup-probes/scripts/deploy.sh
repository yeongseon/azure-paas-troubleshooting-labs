#!/bin/bash
set -e

RG="${RESOURCE_GROUP:-rg-startup-probe-lab}"
LOCATION="${LOCATION:-koreacentral}"
ENV_NAME="${ENV_NAME:-startup-probe-env}"
APP_NAME="${APP_NAME:-slow-starter}"
IMAGE_NAME="${IMAGE_NAME:-slow-starter}"
ACR_NAME="${ACR_NAME:-startupprobeacr$(openssl rand -hex 4)}"
STARTUP_DELAY="${STARTUP_DELAY_SECONDS:-10}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${SCRIPT_DIR}/../app"

echo "=== Startup Probe Lab ==="
echo "Resource Group:  $RG"
echo "Location:        $LOCATION"
echo "Startup Delay:   ${STARTUP_DELAY}s"

az group create --name "$RG" --location "$LOCATION"

az acr create --name "$ACR_NAME" --resource-group "$RG" --sku Basic --admin-enabled true

az acr build --registry "$ACR_NAME" --image "${IMAGE_NAME}:latest" "$APP_DIR"

ACR_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

az containerapp env create --name "$ENV_NAME" --resource-group "$RG" \
    --location "$LOCATION"

# Deploy WITHOUT startup probe (will fail/restart with high delay)
echo "--- Deploying without startup probe ---"
az containerapp create --name "${APP_NAME}-no-probe" --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/${IMAGE_NAME}:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --target-port 8080 \
    --ingress external \
    --env-vars "STARTUP_DELAY_SECONDS=${STARTUP_DELAY}" \
    --min-replicas 1 --max-replicas 1

# Deploy WITH startup probe (handles slow startup gracefully)
echo "--- Deploying with startup probe ---"
az containerapp create --name "${APP_NAME}-with-probe" --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/${IMAGE_NAME}:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --target-port 8080 \
    --ingress external \
    --env-vars "STARTUP_DELAY_SECONDS=${STARTUP_DELAY}" \
    --min-replicas 1 --max-replicas 1

# Configure startup probe on the second app via YAML update
FQDN_NO_PROBE=$(az containerapp show --name "${APP_NAME}-no-probe" --resource-group "$RG" \
    --query "properties.configuration.ingress.fqdn" -o tsv)
FQDN_WITH_PROBE=$(az containerapp show --name "${APP_NAME}-with-probe" --resource-group "$RG" \
    --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "=== Deployment complete ==="
echo "Without probe: https://${FQDN_NO_PROBE}/healthz"
echo "With probe:    https://${FQDN_WITH_PROBE}/healthz"
echo ""
echo "Compare restart counts:"
echo "  az containerapp show --name ${APP_NAME}-no-probe --resource-group $RG --query 'properties.runningStatus'"
echo "  az containerapp show --name ${APP_NAME}-with-probe --resource-group $RG --query 'properties.runningStatus'"
