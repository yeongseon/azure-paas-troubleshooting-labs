#!/bin/bash
# measure-ip-release.sh — Measure how long subnet IPs take to return after scale-in
# Usage: bash measure-ip-release.sh

set -euo pipefail

RESOURCE_GROUP="rg-vnet-ip-lab"
PLAN_NAME="plan-vnet-ip-lab"
VNET_NAME="vnet-lab"
SUBNET_NAME="subnet-asp"
TARGET_WORKERS=2
MAX_POLLS=40

log() { echo "[$(date -u +"%H:%M:%S")] $*"; }

snapshot_subnet() {
    az network vnet subnet show \
        --resource-group "$RESOURCE_GROUP" \
        --vnet-name "$VNET_NAME" \
        --name "$SUBNET_NAME" \
        --query "availableIPAddressCount" -o tsv
}

BEFORE=$(snapshot_subnet)
log "Available IPs before scale-in: $BEFORE"

log "Scaling in to $TARGET_WORKERS workers"
az appservice plan update \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --number-of-workers "$TARGET_WORKERS"
log "Scale-in complete at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

EXPECTED_RELEASE=$((BEFORE + 4))
log "Polling for IP release (expecting ≥ $EXPECTED_RELEASE available IPs)..."

for i in $(seq 1 "$MAX_POLLS"); do
    AVAILABLE=$(snapshot_subnet)
    log "Poll $i — available IPs: $AVAILABLE"
    if [[ "$AVAILABLE" -ge "$EXPECTED_RELEASE" ]]; then
        log "IPs released after poll $i (~$((i * 30))s)"
        break
    fi
    sleep 30
done

log "Final available IPs: $(snapshot_subnet)"
