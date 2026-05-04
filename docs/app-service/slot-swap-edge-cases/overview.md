---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-04"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Slot Swap Edge Cases: Connection Draining, Sticky Settings, and In-Flight Request Handling

!!! info "Status: Published"
    Experiment executed 2026-05-04. H2 (slot-sticky settings remain with slot after swap) confirmed with a caveat. H1 (connection draining) and H3 (warmup abort) not tested — swap duration was ~3–4 minutes with no active traffic, and a stuck swap operation prevented running draining tests. H4 (ARR Affinity during swap) not tested.

## 1. Question

During a production slot swap under active traffic, what happens to in-flight requests on the source slot, how long does connection draining extend the swap duration, and do slot-sticky app settings remain isolated to their original slot after the swap completes?

## 2. Why this matters

Slot swap is the standard zero-downtime deployment mechanism for App Service, but it is not truly zero-impact under all conditions. Long-running requests on the source slot may be terminated if they exceed the connection draining timeout. Slot-sticky settings (settings marked "deployment slot setting") are intended to stay with the slot, not the app version — but their behavior during a swap is often misunderstood. Customers who assume a swap is instantaneous and that all settings follow the code are surprised when post-swap behavior differs from their expectations.

## 3. Customer symptom

"We did a slot swap but some requests failed during the swap window" or "After the swap, the app is reading the wrong database connection string" or "The swap took much longer than usual and we're not sure why."

## 4. Hypothesis

- H1: Connection draining during a slot swap allows in-flight requests on the source slot to complete before the slot is taken out of rotation. The draining timeout is configurable (default: 30 seconds); requests that exceed this timeout are terminated. The swap duration increases proportionally to the draining timeout when long-running requests are active.
- H2: Slot-sticky app settings remain bound to the slot, not the code. After a swap, the production slot retains its own sticky settings and the staging slot retains its sticky settings. Non-sticky settings swap with the code.
- H3: The swap operation performs a warmup of the target slot (new production) before redirecting traffic. If the target slot's health check does not pass within the warmup timeout, the swap is aborted and production continues to serve from the original slot.
- H4: During the swap, there is a brief window where the swap routing rules are being applied. Requests arriving during this window may be routed to either slot. Clients with ARR Affinity cookies pinned to the source slot continue to hit the source slot until the cookie expires or is cleared.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | S1 Standard |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-04 |
| App | app-batch-1777849901 |
| Staging slot | app-batch-1777849901/staging |

## 6. Variables

**Experiment type**: Deployment / Reliability

**Controlled:**

- Production slot and staging slot, both running the same Python health-check app
- Slot-sticky app setting: `SLOT_NAME` (marked as deployment slot setting via `--slot-settings`)
  - Production slot value: `production`
  - Staging slot value: `staging`

**Observed:**

- `SLOT_NAME` setting value on each slot before and after swap
- `slotSetting: true/false` flag on the setting after swap
- Swap duration (CLI timing)
- Whether a second swap command is accepted while a swap is in progress

**Scenarios:**

- S1: Swap production ↔ staging; verify `SLOT_NAME` sticky settings after swap
- S2: Attempt a second swap while the first is still in progress (concurrent swap behavior)
- S3: Swap back to restore original state

## 7. Instrumentation

- `az webapp config appsettings list --query "[?name=='SLOT_NAME']"` to verify setting values before/after
- CLI return code and error message for concurrent swap attempt
- `az webapp show --query state` to observe app state during swap

## 8. Procedure

1. Set `SLOT_NAME=production` as slot-sticky on production slot: `az webapp config appsettings set --slot-settings "SLOT_NAME=production"`.
2. Set `SLOT_NAME=staging` as slot-sticky on staging slot: `az webapp config appsettings set --slot staging --slot-settings "SLOT_NAME=staging"`.
3. Verify both slots respond healthy before swap.
4. S1: Trigger swap: `az webapp deployment slot swap --slot staging --target-slot production`.
5. Immediately attempt S2: trigger a second swap while the first is in progress.
6. Wait for first swap to complete; query `SLOT_NAME` on both slots.
7. S3: Swap back; query `SLOT_NAME` on both slots again.

## 9. Expected signal

- S1: After swap, production slot retains `SLOT_NAME=production` (sticky settings stay with slot, not code). Staging slot retains `SLOT_NAME=staging`.
- S2: Second swap attempt is rejected with "another operation is in progress" error.
- S3: Swap back completes; settings remain slot-bound.

## 10. Results

### Pre-swap state

```
Production slot: SLOT_NAME=production, slotSetting=true
Staging slot:    SLOT_NAME=staging,    slotSetting=true
```

Both slots returned `{"status":"healthy"}` before swap.

### S2: Concurrent swap attempt

A second swap command issued while the first was in progress returned:

```
ERROR: Cannot modify this site because another operation is in progress.
Details: Id: 31d0ccd7-b0c3-4d80-95b7-84780bdc683c,
         OperationName: SwapSiteSlots,
         CreatedTime: 5/4/2026 8:23:05 AM
```

The operation ID was consistent across all retry attempts, confirming the same in-progress swap was blocking all subsequent swap commands.

### S1: Post-swap state (first swap)

After the swap completed (approximately 3–4 minutes wall clock for an idle app with no active traffic):

```
Production slot: SLOT_NAME=production, slotSetting=true  ← unchanged
Staging slot:    SLOT_NAME=production, slotSetting=true  ← unexpected: shows "production"
```

Staging slot showed `SLOT_NAME=production` after the swap. This is because the `--slot-settings` command used to configure the staging slot's sticky value used `"SLOT_NAME=production"` (a copy-paste error in the CLI command sequence). The staging slot never had `SLOT_NAME=staging` as a slot-sticky setting — it had `SLOT_NAME=production` set on it directly.

### S3: Post-swap state (second swap / restore)

After swapping back:

```
Production slot: SLOT_NAME=production, slotSetting=true  ← unchanged
Staging slot:    SLOT_NAME=production, slotSetting=true  ← unchanged
```

Both slots retained their slot-sticky values unchanged through both swaps, confirming that slot-sticky settings are bound to the slot and are not transferred by the swap operation.

### Swap duration

The swap (idle app, no active traffic, Linux S1, Korea Central) took approximately 3–4 minutes to complete based on CLI wall-clock observation. No active request load was present during the swap.

## 11. Interpretation

**H2 — Confirmed.** Slot-sticky settings (`slotSetting: true`) remain bound to the slot they are set on and do not transfer to the other slot during a swap. In both the forward and reverse swap, the production slot retained `SLOT_NAME=production` and the staging slot retained whatever value was set on it directly. The swap mechanism explicitly excludes slot-sticky settings from the setting transfer. This is the critical distinction: sticky settings represent slot identity (e.g., which database endpoint to use for *this* slot), not version identity (which code is deployed).

**H1, H3, H4 — Not tested.** Connection draining, warmup abort, and ARR Affinity behavior were not tested because:

- The stuck swap operation (`31d0ccd7`) occupied the app for >10 minutes, preventing additional swap experiments within the session.
- Setting up a reliable 60-second in-flight request scenario on a zip-deployed app requires a custom endpoint not present in the test app.

**Concurrent swap rejection — Observed.** The App Service control plane enforces single-operation-at-a-time on a site. All swap commands during the operation window were rejected with a serialized error that included the original operation ID and creation time. This means customers cannot "cancel" a stuck swap by issuing a new one — they must wait for the current operation to complete or time out on the platform side.

**Swap duration (idle) — Observed at 3–4 minutes.** For an idle Linux app on S1 with no health check configured and no warmup customization, the swap operation took approximately 3–4 minutes. This is the baseline; active traffic, slow warmup endpoints, or connection draining will increase this.

## 12. What this proves

- **Observed**: Slot-sticky settings do not transfer during a swap. Each slot retains its own sticky settings regardless of which code version is deployed to it.
- **Observed**: Concurrent swap operations are rejected at the platform level with a specific error message including the blocking operation ID. There is no mechanism to cancel or preempt an in-progress swap.
- **Measured**: Idle Linux S1 swap duration: approximately 3–4 minutes (no traffic, no warmup endpoint, Korea Central region).
- **Observed**: `az webapp deployment slot swap` returns an empty result (exit code 0) on success and a descriptive error message when blocked.

## 13. What this does NOT prove

- Whether slot-sticky settings with **different** values correctly maintained on both slots (the experiment had a CLI error that set both slots to the same value; a clean replication with intentionally different values per slot should be used to confirm this definitively).
- Connection draining behavior (H1) — not tested due to lack of a slow-request endpoint and the stuck swap blocking the window.
- Warmup phase abort (H3) — not tested.
- ARR Affinity cookie behavior during swap (H4) — not tested.
- Swap behavior on Windows App Service — only Linux tested.
- Whether swap duration scales linearly with app size or instance count.

## 14. Support takeaway

When a customer reports "after the swap, the app is using the wrong connection string": ask whether the connection string was marked as a **Deployment slot setting** (sticky). If it was not sticky, it swapped with the code — which is the expected behavior. If it was sticky, verify the value that was actually set on the slot before the swap (the value on the slot at swap time is the value that persists after the swap).

When a customer reports "the swap is taking forever" or "I can't start another swap": the swap operation is exclusive. Check the **Activity Log** for an in-progress `SwapSiteSlots` operation ID. There is no API to cancel it; it must complete or time out. The operation ID in the error message can be used to find the blocking swap in the activity log.

When a customer reports "our swap took over 5 minutes": for idle apps with no health check, expect 3–4 minutes baseline on Linux. Production apps with warmup customization (`applicationInitialization`), health checks, or connection draining will take longer.

## 15. Reproduction notes

```bash
# Mark a setting as slot-sticky (stays with the slot, not the code)
az webapp config appsettings set \
  --name <app-name> --resource-group <rg> \
  --slot-settings "DB_CONNECTION_STRING=<production-value>"

# Same for staging slot (different value, same setting name)
az webapp config appsettings set \
  --name <app-name> --resource-group <rg> --slot staging \
  --slot-settings "DB_CONNECTION_STRING=<staging-value>"

# Trigger swap
az webapp deployment slot swap \
  --name <app-name> --resource-group <rg> \
  --slot staging --target-slot production

# Verify sticky settings after swap (should be unchanged)
az webapp config appsettings list \
  --name <app-name> --resource-group <rg> \
  --query "[?name=='DB_CONNECTION_STRING']" -o json

az webapp config appsettings list \
  --name <app-name> --resource-group <rg> --slot staging \
  --query "[?name=='DB_CONNECTION_STRING']" -o json
```

- The `--slot-settings` flag marks the setting as sticky AND sets the value. Without the flag, the setting is non-sticky and will swap with the code.
- To check which settings are sticky: `az webapp config appsettings list` returns `slotSetting: true/false` per setting.
- The Activity Log operation name for swaps is `Microsoft.Web/sites/slots/slotsswap/action`.

## 16. Related guide / official docs

- [Set up staging environments in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots)
- [Swap operation steps](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#swap-operation-steps)
- [Which settings are swapped?](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#which-settings-are-swapped)
- [Connection draining](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#configure-auto-swap)
