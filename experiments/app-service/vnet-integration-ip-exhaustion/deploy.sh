#!/bin/bash
# deploy.sh — Provision VNet, subnet, and App Service Plan with VNet Integration
# Usage: bash deploy.sh
# Prereqs: az login, subscription set

set -euo pipefail

RESOURCE_GROUP="rg-vnet-ip-lab"
LOCATION="koreacentral"
VNET_NAME="vnet-lab"
SUBNET_NAME="subnet-asp"
PLAN_NAME="plan-vnet-ip-lab"
APP_NAME="app-vnet-ip-lab"
INITIAL_WORKERS=6

log() { echo "[$(date -u +"%H:%M:%S")] $*"; }

log "Creating resource group: $RESOURCE_GROUP"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

log "Creating VNet with /28 subnet (11 usable IPs — intentionally tight)"
az network vnet create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VNET_NAME" \
    --address-prefixes "10.0.0.0/24" \
    --output none

az network vnet subnet create \
    --resource-group "$RESOURCE_GROUP" \
    --vnet-name "$VNET_NAME" \
    --name "$SUBNET_NAME" \
    --address-prefixes "10.0.0.0/28" \
    --delegations "Microsoft.Web/serverFarms" \
    --output none

log "Creating App Service Plan: P1v3 Linux, $INITIAL_WORKERS workers"
az appservice plan create \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --sku P1V3 \
    --is-linux \
    --number-of-workers "$INITIAL_WORKERS" \
    --output none

log "Creating web app"
az webapp create \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --plan "$PLAN_NAME" \
    --runtime "PYTHON:3.11" \
    --output none

log "Enabling Regional VNet Integration"
az webapp vnet-integration add \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --vnet "$VNET_NAME" \
    --subnet "$SUBNET_NAME" \
    --output none

log "=== Deploy complete ==="
az network vnet subnet show \
    --resource-group "$RESOURCE_GROUP" \
    --vnet-name "$VNET_NAME" \
    --name "$SUBNET_NAME" \
    --query "{addressPrefix: addressPrefix, availableIPs: availableIPAddressCount}" \
    -o table

az webapp list-instances \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "[].{name: name, state: state}" -o table
