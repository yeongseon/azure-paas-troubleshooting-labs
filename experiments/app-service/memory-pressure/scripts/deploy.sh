#!/bin/bash
set -e

# Variables
RG="${RESOURCE_GROUP:-rg-memory-pressure-lab}"
LOCATION="${LOCATION:-koreacentral}"
PREFIX="${NAME_PREFIX:-memlabapp}"
SKU="${PLAN_SKU:-B1}"
COUNT="${APP_COUNT:-2}"
ALLOC="${ALLOC_MB:-100}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${SCRIPT_DIR}/../app"

echo "=== Memory Pressure Lab ==="
echo "Resource Group: $RG"
echo "Location:       $LOCATION"
echo "SKU:            $SKU"
echo "App Count:      $COUNT"
echo "Alloc MB:       $ALLOC"

# Create resource group
az group create --name "$RG" --location "$LOCATION"

# Create App Service Plan
az appservice plan create --name "${PREFIX}-plan" --resource-group "$RG" \
  --sku "$SKU" --is-linux

# Package app
pushd "$APP_DIR" > /dev/null
zip -r /tmp/app.zip . -x '__pycache__/*' '*.pyc'
popd > /dev/null

# Deploy apps
for i in $(seq 1 "$COUNT"); do
  APP_NAME="${PREFIX}-${i}"
  echo "--- Deploying $APP_NAME ---"

  az webapp create --name "$APP_NAME" --resource-group "$RG" \
    --plan "${PREFIX}-plan" --runtime "PYTHON:3.11"

  az webapp config appsettings set --name "$APP_NAME" --resource-group "$RG" \
    --settings ALLOC_MB="$ALLOC" SCM_DO_BUILD_DURING_DEPLOYMENT=false

  az webapp deploy --name "$APP_NAME" --resource-group "$RG" \
    --src-path /tmp/app.zip --type zip

  echo "Deployed: https://${APP_NAME}.azurewebsites.net"
done

echo "=== Deployment complete ==="
echo "Check health: curl https://${PREFIX}-1.azurewebsites.net/health"
