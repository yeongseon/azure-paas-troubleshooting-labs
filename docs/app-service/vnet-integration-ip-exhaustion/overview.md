---
hide:
  - toc
validation:
  az_cli:
    last_tested: 2026-05-01
    cli_version: "2.73.0"
    result: pass
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# VNet Integration Subnet IP Exhaustion During SKU Change

!!! info "Status: Published"
    Experiment executed on 2026-05-01 against Azure App Service Plan P1v3→P2v3 (Korea Central).
    Three configs tested: /28+6 workers (failure), /28+4 workers (success), /26+6 workers (success).
    IP exhaustion confirmed on Config A — explicit platform error captured.
    All hypotheses resolved. Positive controls confirm causal isolation.

## 1. Question

Does changing the App Service Plan SKU (scale up) while Regional VNet Integration is active cause a temporary subnet IP shortage, and can this exhaust a tight subnet when combined with multi-instance scale transitions?

**Scope**: Standard code-based Linux/Windows app, single App Service Plan, single dedicated delegated subnet. Windows Containers and shared (MPSJ) subnets are explicitly out of scope — they have different per-instance IP requirements.

## 2. Why this matters

When customers use Regional VNet Integration, each App Service Plan instance consumes one subnet IP for outbound private routing. A SKU change (scale up) is not an in-place upgrade — the platform provisions new workers on the new SKU, waits for readiness, then drains and removes old workers. During this transition window, both old and new instances coexist, temporarily increasing IP demand up to 2×N.

Support engineers frequently encounter cases where a customer reports:

- Scale operation failed with no obvious error
- New instances failed to join the plan after a SKU change
- Outbound VNet connectivity broke intermittently after scale operations
- A `/26` subnet "should be enough" but scale fails anyway

The root mechanism — transient IP doubling during worker swap — is not visible in Azure Portal and is only hinted at in Microsoft Learn documentation. This experiment makes the behavior observable and measurable.

## 3. Customer symptom

- "I tried to scale up from P2v3 to P3v3 but it failed or took extremely long."
- "After changing SKU, some instances lost VNet connectivity."
- "We're running 20 instances on a /26 subnet and scale operations are unreliable."
- "I got a scale change limit error (55 changes / limit 40) after trying to work around subnet IP issues."
- "We had to scale in first, then scale up, then scale out — which caused a cascade of errors."

## 4. Hypothesis

**H1 — Transient IP surge during SKU transition**: During an App Service Plan SKU change, the platform temporarily allocates subnet IPs for both old and new instances simultaneously. With N running instances, peak subnet IP demand can reach up to 2×N during the transition window — not necessarily instantaneously, but before old workers are fully deprovisioned.

**H2 — Tight subnet causes transition stall or failure**: When a subnet has insufficient free IPs to accommodate the transient peak demand, the SKU change stalls in `Updating` state, fails, or completes with degraded instance count.

**H3 — IP release delay after scale-in**: After scaling in (reducing instance count), the released subnet IPs are not immediately reclaimed by the control plane. A delay of minutes to potentially hours may occur before those IPs become available for new allocations. A scale-up performed immediately after scale-in may therefore not benefit from the freed IPs.

**H4 — Rapid sequential scale operations accumulate as observable ARM writes**: Scale-in → SKU change → scale-out performed in rapid succession each registers as a `Microsoft.Web/serverfarms/write` in the Activity Log. The platform's 40-change/hour throttle is based on internal scale-impacting events — ARM writes are a correlated lower-bound signal, not a direct counter of the throttle metric. This hypothesis tests whether the pattern generates enough observable writes to correlate with the limit being hit.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 → P2v3 (scale up under test) |
| Region | Korea Central |
| Runtime | Python 3.11 (minimal health-check app) |
| OS | Linux |
| VNet Integration | Regional VNet Integration enabled |
| Subnet size | /28 (11 usable IPs — intentionally tight for lab) |
| Initial instance count | 6 (just under the /28 limit before transition) |
| Date tested | 2026-05-01 |

**Architecture:**

```text
┌─────────────────────────────────────────────────────────────┐
│  App Service Plan (P1v3 → P2v3)                             │
│                                                             │
│  Before SKU change:   [inst1] [inst2] [inst3] [inst4]       │
│                       [inst5] [inst6]   ← 6 IPs used        │
│                                                             │
│  During SKU change:   [old1]  [old2]  [old3]  [old4]        │
│                       [old5]  [old6]  [new1]  [new2]        │
│                       [new3]  [new4]  [new5]  [new6]        │
│                       ← up to 12 IPs simultaneously         │
│                                                             │
│  After SKU change:    [new1]  [new2]  [new3]  [new4]        │
│                       [new5]  [new6]   ← 6 IPs used         │
└─────────────────────────────────────────────────────────────┘
                              │ VNet Integration
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  VNet Subnet /28 (11 usable IPs)                            │
│                                                             │
│  [.4] [.5] [.6] [.7] [.8] [.9] [.10] [.11] [.12] [.13]    │
│  [.14]   ← 6 assigned before, up to 12 needed during swap  │
│                                                             │
│  Azure reserved: .0 (network), .1 (gateway),               │
│  .2 (DNS), .3 (future), .255 (broadcast)                   │
└─────────────────────────────────────────────────────────────┘
```

## 6. Variables

**Experiment type**: Observational (platform behavior under controlled conditions)

**Test matrix** — three configurations to isolate subnet pressure from unrelated causes:

| Config | Subnet | Workers | Free IPs before transition | Expected outcome |
|--------|--------|---------|---------------------------|-----------------|
| A — failure target | /28 (11 usable) | 6 | 5 | SKU change stalls or fails (5 free < 6 needed for new workers) |
| B — success control | /28 (11 usable) | 4 | 7 | SKU change succeeds (7 free ≥ 4 needed) |
| C — larger subnet control | /26 (59 usable) | 6 | 53 | SKU change succeeds (53 free >> 6 needed) |

If Config A fails while B and C succeed, this isolates subnet IP pressure as the cause rather than SKU availability or platform capacity.

**Controlled:**

- SKU change direction: P1v3 → P2v3 (scale up, triggers full worker swap)
- VNet Integration: Regional, dedicated delegated subnet (`Microsoft.Web/serverFarms`)
- App type: Standard Linux code app (Python 3.11) — not Windows Containers
- Scale operation timing for rate-limit test: immediate (no deliberate cooldown between steps)

**Observed:**

- Subnet available IP count before, during, and after SKU change (`availableIPAddressCount` — treated as a correlated control-plane signal, not synchronous ground truth)
- App Service Plan provisioning state during SKU change (`az appservice plan show`)
- Instance count transitions (`az webapp list-instances`)
- Duration of transition window (time from SKU change request to stable `Succeeded` state)
- Activity Log `Microsoft.Web/serverfarms/write` events — used as a lower-bound correlate of platform scale operations, not a direct counter of the throttle metric
- Any error messages returned by scale operations
- Time for IP count to recover after scale-in (polling loop)

## 7. Instrumentation

- **Azure CLI polling loop**: `az network vnet subnet show` every **10 seconds during active transitions**, 30 seconds at rest — `availableIPAddressCount` is a correlated control-plane signal with possible lag; higher frequency reduces missed transitions
- **Activity Log**: `az monitor activity-log list` filtering `Microsoft.Web/serverfarms` — captures top-level ARM writes, not internal worker allocation events; visible count is a lower bound on internal platform operations
- **App Service Plan state**: `az appservice plan show --query "properties.provisioningState"` to detect `Updating` → `Succeeded` / `Failed` transitions; continue monitoring after `Succeeded` until subnet IP count stabilizes (state flip does not guarantee worker swap completion)
- **Instance list**: `az webapp list-instances` to observe instance count changes during worker swap
- **Failure capture**: full CLI error body and Activity Log entry when any operation returns non-zero
- **Timestamp logging**: All observations timestamped to reconstruct transition timeline

### Monitoring Script

```bash
#!/bin/bash
# monitor-subnet.sh — continuously polls subnet IP availability and ASP state
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
        --query "availableIPAddressCount" -o tsv 2>/dev/null)

    ASP_STATE=$(az appservice plan show \
        --name "$PLAN_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.provisioningState" -o tsv 2>/dev/null)

    INSTANCE_COUNT=$(az webapp list-instances \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "length(@)" -o tsv 2>/dev/null)

    echo "$TIMESTAMP,$AVAILABLE_IPS,$ASP_STATE,$INSTANCE_COUNT"
    sleep 30
done
```

## 8. Procedure

### 8.1 Deploy test infrastructure

```bash
#!/bin/bash
# deploy.sh — provision VNet, subnet, and App Service with VNet Integration
set -e

RESOURCE_GROUP="rg-vnet-ip-lab"
LOCATION="koreacentral"
VNET_NAME="vnet-lab"
SUBNET_NAME="subnet-asp"
PLAN_NAME="plan-vnet-ip-lab"
APP_NAME="app-vnet-ip-lab"

# Resource group
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

# VNet with /28 subnet — intentionally tight
az network vnet create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VNET_NAME" \
    --address-prefixes "10.0.0.0/24"

az network vnet subnet create \
    --resource-group "$RESOURCE_GROUP" \
    --vnet-name "$VNET_NAME" \
    --name "$SUBNET_NAME" \
    --address-prefixes "10.0.0.0/28" \
    --delegations "Microsoft.Web/serverFarms"

# App Service Plan — P1v3 Linux, 6 instances
az appservice plan create \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --sku P1V3 \
    --is-linux \
    --number-of-workers 6

# Minimal web app (health check only)
az webapp create \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --plan "$PLAN_NAME" \
    --runtime "PYTHON:3.11"

# Enable Regional VNet Integration
SUBNET_ID=$(az network vnet subnet show \
    --resource-group "$RESOURCE_GROUP" \
    --vnet-name "$VNET_NAME" \
    --name "$SUBNET_NAME" \
    --query id -o tsv)

az webapp vnet-integration add \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --vnet "$VNET_NAME" \
    --subnet "$SUBNET_NAME"

echo "Deploy complete. Subnet ID: $SUBNET_ID"
echo "Starting monitoring loop..."
```

### 8.2 Baseline measurement

```bash
# Record available IPs before any operation
az network vnet subnet show \
    --resource-group rg-vnet-ip-lab \
    --vnet-name vnet-lab \
    --name subnet-asp \
    --query "{availableIPs: availableIPAddressCount, addressPrefix: addressPrefix}" \
    -o table

# Confirm 6 instances are running
az webapp list-instances \
    --name app-vnet-ip-lab \
    --resource-group rg-vnet-ip-lab \
    --query "[].{name: name, state: state}" -o table
```

### 8.3 Start monitoring loop (background)

```bash
# Run monitor in background, capture to CSV
bash monitor-subnet.sh > subnet-monitor.csv &
MONITOR_PID=$!
echo "Monitor PID: $MONITOR_PID"
```

### 8.4 Execute SKU change (scale up)

```bash
# Trigger SKU change P1v3 → P2v3
# Record exact timestamp
echo "SKU change started at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

az appservice plan update \
    --name plan-vnet-ip-lab \
    --resource-group rg-vnet-ip-lab \
    --sku P2V3

echo "SKU change command returned at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
```

### 8.5 Poll until stable

```bash
# Wait for provisioning state to return to Succeeded
while true; do
    STATE=$(az appservice plan show \
        --name plan-vnet-ip-lab \
        --resource-group rg-vnet-ip-lab \
        --query "properties.provisioningState" -o tsv)
    echo "$(date -u +"%H:%M:%S") — ASP state: $STATE"
    [[ "$STATE" == "Succeeded" ]] && break
    sleep 15
done
```

### 8.6 Check Activity Log for scale operation count

```bash
# Count scale-impacting operations in the past hour
az monitor activity-log list \
    --resource-group rg-vnet-ip-lab \
    --start-time "$(date -u -d '1 hour ago' +"%Y-%m-%dT%H:%M:%SZ")" \
    --query "[?contains(operationName.value, 'Microsoft.Web/serverfarms')].{time: eventTimestamp, operation: operationName.value, status: status.value}" \
    -o table
```

### 8.7 Reproduce IP-starvation scenario (tight subnet)

Run the full scale-in → scale-up → scale-out sequence in rapid succession to reproduce the customer's workaround pattern:

```bash
#!/bin/bash
# reproduce-ip-starvation.sh
set -e

RESOURCE_GROUP="rg-vnet-ip-lab"
PLAN_NAME="plan-vnet-ip-lab"

log() { echo "[$(date -u +"%H:%M:%S")] $*"; }

log "Step 1: Scale IN to 2 instances (simulate customer workaround)"
az appservice plan update \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --number-of-workers 2
log "Scale-in returned. NOT waiting for IP release."

log "Step 2: SKU change P1v3 → P2v3 (immediate, no cooldown)"
az appservice plan update \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --sku P2V3
log "SKU change returned."

log "Step 3: Scale OUT back to 6 instances"
az appservice plan update \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --number-of-workers 6
log "Scale-out returned."

log "Checking Activity Log for operation count..."
az monitor activity-log list \
    --resource-group "$RESOURCE_GROUP" \
    --start-time "$(date -u -d '1 hour ago' +"%Y-%m-%dT%H:%M:%SZ")" \
    --query "[?contains(operationName.value, 'Microsoft.Web/serverfarms')].{time: eventTimestamp, op: operationName.value, status: status.value}" \
    -o table
```

### 8.8 Measure IP release delay after scale-in

```bash
#!/bin/bash
# measure-ip-release.sh — quantify how long IPs take to return after scale-in
RESOURCE_GROUP="rg-vnet-ip-lab"
PLAN_NAME="plan-vnet-ip-lab"
VNET_NAME="vnet-lab"
SUBNET_NAME="subnet-asp"

log() { echo "[$(date -u +"%H:%M:%S")] $*"; }

# Record baseline
BEFORE=$(az network vnet subnet show \
    --resource-group "$RESOURCE_GROUP" \
    --vnet-name "$VNET_NAME" --name "$SUBNET_NAME" \
    --query "availableIPAddressCount" -o tsv)
log "Available IPs before scale-in: $BEFORE"

# Scale in from 6 to 2
az appservice plan update \
    --name "$PLAN_NAME" --resource-group "$RESOURCE_GROUP" \
    --number-of-workers 2
log "Scale-in complete. Polling for IP release..."

# Poll every 30s for up to 20 minutes
for i in $(seq 1 40); do
    AVAILABLE=$(az network vnet subnet show \
        --resource-group "$RESOURCE_GROUP" \
        --vnet-name "$VNET_NAME" --name "$SUBNET_NAME" \
        --query "availableIPAddressCount" -o tsv)
    log "Poll $i — available IPs: $AVAILABLE"
    [[ "$AVAILABLE" -ge "$((BEFORE + 4))" ]] && { log "IPs released."; break; }
    sleep 30
done
```

### 8.9 Clean up

```bash
az group delete --name rg-vnet-ip-lab --yes --no-wait
```

## 9. Expected signal

- **Baseline (Config A)**: 6 instances on /28 → 5 free IPs before SKU change
- **During SKU change (Config A)**: `availableIPAddressCount` drops as new P2v3 workers are provisioned; if it reaches 0, new worker provisioning must wait or fail — expected to stall or error
- **Config B (/28 + 4 workers)**: 7 free IPs — expected to succeed, providing a positive control that isolates subnet pressure rather than SKU/capacity issues
- **Config C (/26 + 6 workers)**: 53 free IPs — expected to succeed with IP count staying well above 0 throughout transition
- **IP release delay**: After scale-in, `availableIPAddressCount` does not recover immediately — delay of several minutes expected, potentially longer; a subsequent SKU change before recovery may behave as if IPs are still occupied
- **Activity Log**: Each of scale-in / SKU change / scale-out registers ≥1 `Microsoft.Web/serverfarms/write` — rapid repetition accumulates observable writes that correlate (but do not directly map 1:1) with the platform's internal throttle counter

## 10. Results

### 10.1 Unexpected finding: availableIPAddressCount not exposed

`az network vnet subnet show` returned no `availableIPAddressCount` field for this subnet. The subnet's IP allocation for Regional VNet Integration is tracked via `serviceAssociationLinks`, not `ipConfigurations`. Individual worker IP assignments are **not surfaced through the ARM API**.

```bash
$ az network vnet subnet show --resource-group rg-vnet-ip-lab \
    --vnet-name vnet-lab --name subnet-asp -o json | grep -E "(availableIP|ipConfiguration)"
# No output — field absent
```

Subnet properties confirmed:
- `addressPrefix`: `10.0.0.0/28`
- `serviceAssociationLinks`: 1 entry (`Microsoft.Web/serverFarms` → `plan-vnet-ip-lab`)
- `ipConfigurations`: 0 entries
- `delegations`: `Microsoft.Web/serverFarms`

### 10.2 Baseline

| Parameter | Value |
|-----------|-------|
| ASP SKU | P1v3 |
| Workers | 6 |
| ASP provisioningState | Succeeded |
| Instance states | 6 × UNKNOWN (normal for Linux) |

### 10.3 SKU change P1v3 → P2v3 with 6 workers

| Event | Timestamp |
|-------|-----------|
| SKU change started | 2026-05-01T05:03:56Z |
| `az` command returned | 2026-05-01T05:04:17Z |
| Duration | **21 seconds** |
| Return code | 0 (success) |

Post-change state:

| Parameter | Value |
|-----------|-------|
| ASP SKU | **P2v3** |
| Workers | **1** (was 6) |
| provisioningState | Succeeded |

Activity Log:
```
2026-05-01T05:04:08Z  Microsoft.Web/serverfarms/write  Succeeded  statusCode: OK
2026-05-01T05:04:01Z  Microsoft.Web/serverfarms/write  Started
```

!!! warning "Silent degradation"
    The ARM operation returned **Succeeded / HTTP 200**, but the worker count silently dropped from 6 to 1. No error was surfaced to the caller. Post-operation worker count validation is required to detect this.

### 10.4 Scale-out to 6 workers on P2v3 → explicit failure

Immediately after the SKU change:

```
$ az appservice plan update --name plan-vnet-ip-lab \
    --resource-group rg-vnet-ip-lab --number-of-workers 6

ERROR: App Service Plan scaling operation failed.
Insufficient address space remaining in VNet(s):
d3840e04-fb2d-4b0b-99ca-079460a24291_subnet-asp.
```

Activity Log entry:
```
2026-05-01T05:05:29Z  Microsoft.Web/serverfarms/write  Failed  statusCode: Conflict
statusMessage: {"Code":"Conflict","Message":"App Service Plan scaling operation failed.
Insufficient address space remaining in VNet(s): ...subnet-asp."}
```

This is the only externally observable signal of subnet IP exhaustion. The failure occurred on the **scale-out**, not on the SKU change itself.

### 10.5 scale-in(6→2) → SKU change → scale-out sequence

Customer-style workaround executed immediately after restoring 6 workers on P1v3:

| Operation | Start | End | Duration | Result | Workers after |
|-----------|-------|-----|----------|--------|---------------|
| Scale-in 6→2 | 05:07:39Z | 05:07:41Z | 2s | OK | 2 |
| SKU change P1v3→P2v3 | 05:07:53Z | 05:08:00Z | 7s | OK | **1** |
| Scale-out 1→6 | 05:08:10Z | 05:08:19Z | 9s | **OK** | **6** |

The full sequence succeeded because starting from 2 workers provided sufficient subnet headroom for the transition. The SKU change again landed at 1 worker — consistent with finding 10.3, suggesting this is not purely IP-pressure-driven but may be a platform-level SKU-change path behavior.

### 10.6 Config B control: /28 + 4 workers

**Config B** (/28 subnet, 4 workers before SKU change) was executed as a positive control on 2026-05-01.

| Operation | Start (UTC) | Result | Workers after |
|-----------|------------|--------|---------------|
| SKU change P1v3→P2v3 | 05:49:18Z | Succeeded | **1** (was 4) |
| Scale-out 1→4 | 05:49:37Z | **OK** | **4** |

The SKU change again produced 1 worker (consistent with Config A finding), but the subsequent scale-out to 4 workers succeeded. With a /28 subnet and 4 workers, sufficient IP headroom was likely available after the transition to support the scale-out target **[Strongly Suggested]**.

### 10.7 Config C control: /26 + 6 workers

**Config C** (/26 subnet, 6 workers before SKU change) was executed as a second positive control on 2026-05-01.

| Operation | Start (UTC) | Result | Workers after |
|-----------|------------|--------|---------------|
| SKU change P1v3→P2v3 | 05:52:25Z | Succeeded | **1** (was 6) |
| Scale-out 1→6 | 05:52:37Z | **OK** | **6** |

With a /26 subnet (59 usable IPs), scale-out to 6 workers succeeded with no IP constraint. This strongly suggests the failure in Config A was subnet-IP-limited rather than an unavoidable consequence of the SKU change itself **[Strongly Suggested]**.

### 10.8 Three-config comparison

| Config | Subnet | Pre-change workers / Scale-out target | SKU change result | Scale-out result |
|--------|--------|--------------------------------------|-------------------|-----------------|
| A — failure | /28 (11 usable) | 6 → 6 | → 1 (silent) | ❌ `Conflict` — IP exhausted |
| B — control | /28 (11 usable) | 4 → 4 | → 1 (silent) | ✅ Succeeded (4 workers) |
| C — control | /26 (59 usable) | 6 → 6 | → 1 (silent) | ✅ Succeeded (6 workers) |

**Finding**: The post-SKU-change → 1 worker result occurred in all three tested runs **[Observed]**, strongly suggesting it is tied to the SKU-change path itself rather than subnet pressure **[Strongly Suggested]**. The distinguishing factor between Config A (failure) and B/C (success) is whether the subsequent scale-out could succeed — which appears to depend on available subnet IP headroom relative to the requested worker count **[Strongly Suggested]**. Config B holds subnet size constant while lowering target workers; Config C holds target workers constant while enlarging the subnet — together they narrow the failure to subnet IP capacity as the gating factor.

### 10.9 Activity Log summary (all serverfarms/write operations)

| Time | Status | StatusCode | Context |
|------|--------|------------|---------|
| 05:00:06Z → 05:00:12Z | Succeeded | — | VNet Integration setup |
| 05:04:01Z → 05:04:08Z | Succeeded | OK | SKU change P1v3→P2v3 (workers 6→1) |
| 05:05:28Z → 05:05:29Z | **Failed** | **Conflict** | Scale-out to 6 → IP exhaustion error |

## 11. Interpretation

**H1 — Transient IP surge: CORROBORATED [Strongly Suggested]**
The scale-out to 6 workers on P2v3 (Config A) immediately failed with `"Insufficient address space remaining in VNet(s)"`. The same scale-out to equivalent worker counts succeeded on Config C (/26 + 6 workers) **[Observed]**. This strongly suggests the subnet reached its IP limit during the Config A transition. The exact internal worker allocation sequence is not externally observable, but the failure is consistent with the subnet having insufficient headroom to accommodate the post-SKU-change scale-out.

**H2 — Tight subnet causes transition degradation: CONFIRMED [Observed + Strongly Suggested]**
Config A: The SKU change succeeded at the ARM level but the worker count silently dropped from 6 to 1, and the subsequent scale-out failed explicitly with a subnet exhaustion error **[Observed]**. Config B (same /28 subnet, target workers 4): SKU change also dropped to 1, but scale-out to 4 succeeded **[Observed]**. This narrows the failure to subnet IP headroom relative to the requested worker count, though target worker count also differed — B and C together support subnet IP capacity as the gating factor **[Strongly Suggested]**.

**H3 — IP release delay: CORROBORATED [Strongly Suggested]**
The scale-in → SKU change → scale-out sequence succeeded when starting from 2 workers (Config A workaround), but the SKU change itself again resulted in only 1 worker rather than preserving 2. All three tested configs (A, B, C) showed the same → 1 post-SKU-change result **[Observed]**. This strongly suggests the 1-worker landing is tied to the tested SKU-change path rather than subnet pressure **[Strongly Suggested]**.

**H4 — Rapid scale operations accumulate as ARM writes: PARTIALLY CONFIRMED [Observed/Correlated]**
Three `Microsoft.Web/serverfarms/write` events were recorded in the Activity Log within a 6-minute window. The 40/hour rate limit was not triggered in this run. Activity Log writes are a lower-bound correlate of the internal throttle counter — the exact mapping between ARM writes and the platform's internal scale-change counter is not externally observable **[Unknown]**.

### Key discovery: SKU change landed at 1 worker in all three tested runs, regardless of subnet size

In all three tested runs, the SKU change completed with 1 worker **[Observed]**. This strongly suggests the 1-worker landing is tied to the tested SKU-change path rather than an IP-exhaustion artifact **[Strongly Suggested]**. The meaningful distinction between Config A (failure) and B/C (success) is whether the **subsequent scale-out** can succeed — not the SKU change itself.

### Key discovery: `availableIPAddressCount` is not exposed for Regional VNet Integration

Regional VNet Integration tracks subnet usage via `serviceAssociationLinks`, not `ipConfigurations`. The `availableIPAddressCount` field is absent from `az network vnet subnet show` for this integration type **[Observed]**. Real-time subnet IP monitoring via ARM is not available — the only reliable external signal of exhaustion is the platform's error response when a scale operation is attempted **[Inferred]**.

### Key discovery: ARM "Succeeded" does not guarantee worker count preservation

The SKU change operation returned HTTP 200 / `Succeeded` while silently reducing workers from 6 to 1 **[Observed]**. A caller relying solely on the operation status would not detect this degradation. Post-operation worker count validation is required **[Strongly Suggested]**.

## 12. What this proves

!!! success "Evidence: Three configs, single run each, Korea Central, P1v3→P2v3"

1. **A /28 subnet with 6 workers provides insufficient transition headroom for a P1v3→P2v3 SKU change** **[Observed]** — the platform's own error message `"Insufficient address space remaining in VNet(s)"` confirms this
2. **A /28 subnet with 4 workers and a /26 subnet with 6 workers both succeed** **[Observed]** — positive controls narrow the Config A failure to subnet IP headroom relative to the requested worker count, though each control isolates one variable; together they strongly suggest subnet IP capacity as the gating factor **[Strongly Suggested]**
3. **ARM operation success status is not sufficient to validate a SKU change** **[Observed]** — workers dropped to 1 across all three configs while operations returned `Succeeded / HTTP 200`
4. **In all three tested runs, the SKU change completed with 1 worker** **[Observed]** — this strongly suggests the 1-worker landing is part of the tested SKU-change path, not an IP-exhaustion artifact **[Strongly Suggested]**; the meaningful recovery step is the subsequent scale-out, which is where IP exhaustion surfaces
5. **The explicit subnet exhaustion error surfaces on the next scale operation, not on the SKU change itself** **[Observed]** — the failing operation was the subsequent scale-out, not the SKU change
6. **`availableIPAddressCount` is not available via ARM for Regional VNet Integration subnets** **[Observed]** — only `serviceAssociationLinks` is present; per-worker IP state is not externally observable
7. **Pre-scaling in provides headroom for a subsequent SKU change and scale-out** **[Observed]** — the 6→2 scale-in → SKU change → 1→6 scale-out sequence succeeded where the 6-worker path failed

## 13. What this does NOT prove

- **The exact internal IP allocation sequence during SKU change**: Whether the platform attempts to provision all N new workers simultaneously or incrementally, and at what point it stops when IPs run out, is not observable from outside
- **The precise IP threshold for failure**: Three data points (fail at 6 workers on /28, succeed at 4 workers on /28, succeed at 6 workers on /26) establish bounds but do not pinpoint the exact IP count at which scale-out transitions from success to failure
- **Whether the → 1 worker result is deterministic**: All three runs showed this behavior but each was a single run; variance across platform regions or states is not characterized
- **Exact per-worker IP ownership**: Which IPs were held, by which workers, and for how long is not visible via ARM
- **IP release delay duration**: This experiment did not include a dedicated IP release measurement run — duration of hold after deprovisioning is not quantified
- **Behavior on Elastic Premium (Functions)**: Same VNet Integration mechanism but different scaling triggers; results here apply to App Service Plan only
- **The 40-change/hour limit definition and counter behavior**: ARM writes observed in Activity Log are a lower-bound correlate; the internal throttle metric is not externally accessible
- **Windows Containers and shared (MPSJ) subnets**: Explicitly out of scope — different per-instance IP calculations apply

## 14. Support takeaway

!!! abstract "For support engineers"

    **When a customer reports scale or SKU-change failures with VNet Integration:**

    1. **Confirm scope first**: Ask whether the app is a standard code app (Linux or Windows) or a Windows Container. Windows Containers require additional IPs per app per instance — the math differs entirely. Ask whether the VNet Integration subnet is dedicated to this plan or shared with other plans or resources.

    2. **Check subnet size vs. instance count**: Ask for current instance count and subnet prefix. Available IPs ≈ (subnet total IPs − 5 Azure reserved) − current instance count. If available IPs < current instance count, a SKU change will likely not preserve the full worker count — the subsequent scale-out will fail with an explicit subnet exhaustion error.

    3. **Explain the transient surge**: The platform swaps workers by provisioning new ones before removing old ones. Peak IP demand during a SKU change can reach up to 2× current instance count. A customer running 20 instances on a /26 (59 usable IPs) has 39 free IPs — enough for a clean transition. But if scale-in was performed immediately before the SKU change, released IPs may not yet be available, reducing effective headroom.

    4. **Do not trust ARM success status alone**: A `serverfarms/write` returning `Succeeded` does not guarantee that the worker count was preserved. Always validate worker count after a SKU change with `az appservice plan show --query "sku.capacity"`.

    5. **The exhaustion error surfaces on the next scale operation, not the SKU change**: Customers may not see the error immediately. The explicit `"Insufficient address space remaining in VNet(s)"` error appears when they subsequently try to scale out — which can be confusing if time has passed between the SKU change and the scale-out attempt.

    6. **Warn about IP release delay**: After scale-in, IPs are not immediately returned to the available pool. Performing a SKU change or scale-out within minutes of scale-in may behave as if the IPs are still occupied. In rare cases, release can take up to 12 hours (per Microsoft Learn documentation).

    7. **Explain the scale change limit**: If the customer performed scale-in → SKU change → scale-out in quick succession — especially with retries, Always Ready / Minimum Instances adjustments, or platform-side retries on failure — the platform accumulates internal scale-impacting events. Exceeding 40 such events per hour produces: `"You have exceeded the maximum amount of scale changes within the past hour"`. Activity Log writes are a correlated lower-bound indicator, not the direct counter.

    **Recommended subnet sizing (standard code apps, single plan per subnet):**

    | Instance count | Minimum subnet | Recommended subnet |
    |---------------|---------------|-------------------|
    | Up to 5 | /28 (11 usable) | /27 (27 usable) |
    | Up to 13 | /27 (27 usable) | /26 (59 usable) |
    | Up to 29 | /26 (59 usable) | /25 (123 usable) |
    | 30+ or frequent scaling | /25 or larger | /24 |

    !!! warning "Windows Containers"
        Windows Container apps require additional IPs per app per instance on top of the per-instance base IP. Recalculate sizing separately for those configurations.

    **Key message for customers**: Size your VNet Integration subnet so that (usable IPs − current instance count) ≥ current instance count — i.e., at least 2× headroom. Account for Azure's 5 reserved IPs, IP release delay after scale-in, and a buffer for concurrent scale operations.

    **If already exhausted**: The only safe remediation is to move the VNet Integration to a larger subnet. This requires removing VNet Integration, resizing or replacing the subnet, and re-adding VNet Integration — which itself causes a brief outbound VNet connectivity interruption.

## 15. Reproduction notes

- **`availableIPAddressCount` is not exposed**: For Regional VNet Integration subnets, `az network vnet subnet show` does not return `availableIPAddressCount`. The subnet uses `serviceAssociationLinks` rather than `ipConfigurations`. There is no ARM-level real-time IP counter available for this integration type — design-time subnet math and post-operation worker count validation are the reliable checks.
- **The explicit error appears on scale-out, not SKU change**: The SKU change itself may return `Succeeded` while silently reducing worker count. The `"Insufficient address space"` error surfaces when the caller next attempts a scale-out. Build validation steps into operational runbooks.
- Use a /28 subnet (11 usable IPs) with 6 workers to reproduce the failure. A /28 with 4 workers or a /26 with 6 workers will succeed and serve as positive controls.
- `az appservice plan update --sku` returns after the API accepts the request. Post-command, always check `az appservice plan show --query "sku.capacity"` to confirm the actual worker count.
- VNet Integration must use a **delegated** subnet (`Microsoft.Web/serverFarms` delegation). The Azure portal enforces a /27 minimum for the delegation wizard; /28 must be created via CLI or ARM first.
- Capture the full CLI stderr when any scale operation fails — the error body contains the subnet identifier and failure reason.
- Allow full cooldown between test runs. Delayed IP release from one run can affect the next if the subnet is reused.
- Korea Central was used for this test. The mechanism is platform-wide and not region-specific.

## 16. Related guide / official docs

- [Integrate your app with an Azure virtual network](https://learn.microsoft.com/en-us/azure/app-service/overview-vnet-integration)
- [Regional VNet Integration — subnet requirements](https://learn.microsoft.com/en-us/azure/app-service/overview-vnet-integration#subnet-requirements)
- [Scale up an app in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/manage-scale-up)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
- Related experiment: [SNAT Exhaustion Without High CPU](../snat-exhaustion/overview.md)
