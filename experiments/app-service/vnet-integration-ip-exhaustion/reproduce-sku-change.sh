#!/bin/bash
# reproduce-sku-change.sh — Execute SKU change and observe IP transitions
# Usage: bash reproduce-sku-change.sh
# Run monitor-subnet.sh in a separate terminal before starting this script

set -euo pipefail

RESOURCE_GROUP="rg-vnet-ip-lab"
PLAN_NAME="plan-vnet-ip-lab"
VNET_NAME="vnet-lab"
SUBNET_NAME="subnet-asp"

log() { echo "[$(date -u +"%H:%M:%S")] $*"; }

snapshot_subnet() {
    az network vnet subnet show \
        --resource-group "$RESOURCE_GROUP" \
        --vnet-name "$VNET_NAME" \
        --name "$SUBNET_NAME" \
        --query "availableIPAddressCount" -o tsv
}

log "=== Phase 1: Baseline ==="
BASELINE=$(snapshot_subnet)
log "Available IPs before SKU change: $BASELINE"

log "=== Phase 2: SKU change P1v3 → P2v3 ==="
log "Start: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

az appservice plan update \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --sku P2V3

log "az command returned: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

log "=== Phase 3: Wait for Succeeded state ==="
while true; do
    STATE=$(az appservice plan show \
        --name "$PLAN_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.provisioningState" -o tsv)
    AVAILABLE=$(snapshot_subnet)
    log "ASP state: $STATE | available IPs: $AVAILABLE"
    [[ "$STATE" == "Succeeded" ]] && break
    sleep 15
done

log "=== Phase 4: Post-change snapshot ==="
AFTER=$(snapshot_subnet)
log "Available IPs after SKU change: $AFTER"
log "Delta from baseline: $((AFTER - BASELINE))"

log "=== Phase 5: Activity Log — scale operations in past hour ==="
az monitor activity-log list \
    --resource-group "$RESOURCE_GROUP" \
    --start-time "$(date -u -d '1 hour ago' +"%Y-%m-%dT%H:%M:%SZ")" \
    --query "[?contains(operationName.value, 'Microsoft.Web/serverfarms')].{time: eventTimestamp, op: operationName.value, status: status.value}" \
    -o table
