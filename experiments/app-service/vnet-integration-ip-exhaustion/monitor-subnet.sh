#!/bin/bash
# monitor-subnet.sh — Poll subnet IP availability and ASP state every 30s
# Usage: bash monitor-subnet.sh | tee subnet-monitor.csv
# Stop with Ctrl+C

set -euo pipefail

RESOURCE_GROUP="rg-vnet-ip-lab"
VNET_NAME="vnet-lab"
SUBNET_NAME="subnet-asp"
PLAN_NAME="plan-vnet-ip-lab"
APP_NAME="app-vnet-ip-lab"

echo "timestamp,available_ips,asp_state,instance_count"

while true; do
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    AVAILABLE_IPS=$(az network vnet subnet show \
        --resource-group "$RESOURCE_GROUP" \
        --vnet-name "$VNET_NAME" \
        --name "$SUBNET_NAME" \
        --query "availableIPAddressCount" -o tsv 2>/dev/null || echo "error")

    ASP_STATE=$(az appservice plan show \
        --name "$PLAN_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.provisioningState" -o tsv 2>/dev/null || echo "error")

    INSTANCE_COUNT=$(az webapp list-instances \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "length(@)" -o tsv 2>/dev/null || echo "error")

    echo "$TIMESTAMP,$AVAILABLE_IPS,$ASP_STATE,$INSTANCE_COUNT"
    sleep 30
done
