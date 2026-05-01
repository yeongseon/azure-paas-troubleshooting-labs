#!/bin/bash
# reproduce-scale-limit.sh — Rapid scale-in + SKU change + scale-out to trigger rate limit
# Usage: bash reproduce-scale-limit.sh
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

count_scale_ops() {
    az monitor activity-log list \
        --resource-group "$RESOURCE_GROUP" \
        --start-time "$(date -u -d '1 hour ago' +"%Y-%m-%dT%H:%M:%SZ")" \
        --query "[?contains(operationName.value, 'Microsoft.Web/serverfarms')] | length(@)" \
        -o tsv
}

log "=== Baseline ==="
log "Available IPs: $(snapshot_subnet)"
log "Scale ops in past hour: $(count_scale_ops)"

log "=== Step 1: Scale IN to 2 instances (no cooldown) ==="
log "Start: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
az appservice plan update \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --number-of-workers 2
log "Scale-in returned. Available IPs: $(snapshot_subnet) | ops: $(count_scale_ops)"

log "=== Step 2: SKU change P1v3 → P2v3 (immediate, no cooldown) ==="
log "Start: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
az appservice plan update \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --sku P2V3 || log "ERROR on SKU change (expected if IPs not released yet)"
log "SKU change returned. Available IPs: $(snapshot_subnet) | ops: $(count_scale_ops)"

log "=== Step 3: Scale OUT to 6 instances (immediate) ==="
log "Start: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
az appservice plan update \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --number-of-workers 6 || log "ERROR on scale-out"
log "Scale-out returned. Available IPs: $(snapshot_subnet) | ops: $(count_scale_ops)"

log "=== Final Activity Log ==="
az monitor activity-log list \
    --resource-group "$RESOURCE_GROUP" \
    --start-time "$(date -u -d '1 hour ago' +"%Y-%m-%dT%H:%M:%SZ")" \
    --query "[?contains(operationName.value, 'Microsoft.Web/serverfarms')].{time: eventTimestamp, op: operationName.value, status: status.value}" \
    -o table
