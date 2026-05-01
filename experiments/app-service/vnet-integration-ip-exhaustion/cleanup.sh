#!/bin/bash
# cleanup.sh — Delete all resources created by this experiment
# Usage: bash cleanup.sh

set -euo pipefail

RESOURCE_GROUP="rg-vnet-ip-lab"

az group delete --name "$RESOURCE_GROUP" --yes --no-wait
echo "Deletion initiated for resource group: $RESOURCE_GROUP"
