---
hide:
  - toc
validation:
  az_cli:
    last_tested: null
    result: not_tested
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Slot Swap Edge Cases: Connection Draining, Sticky Settings, and In-Flight Request Handling

!!! info "Status: Planned"

## 1. Question

During a production slot swap under active traffic, what happens to in-flight requests on the source slot, how long does connection draining extend the swap duration, and do slot-sticky app settings remain isolated to their original slot after the swap completes?

## 2. Why this matters

Slot swap is the standard zero-downtime deployment mechanism for App Service, but it is not truly zero-impact under all conditions. Long-running requests on the source slot may be terminated if they exceed the connection draining timeout. Slot-sticky settings (settings marked "deployment slot setting") are intended to stay with the slot, not the app version — but their behavior during a swap is often misunderstood. Customers who assume a swap is instantaneous and that all settings follow the code are surprised when post-swap behavior differs from their expectations.

## 3. Customer symptom

"We did a slot swap but some requests failed during the swap window" or "After the swap, the app is reading the wrong database connection string" or "The swap took much longer than usual and we're not sure why."

## 4. Hypothesis

- H1: Connection draining during a slot swap allows in-flight requests on the source slot to complete before the slot is taken out of rotation. The draining timeout is configurable (default: 30 seconds); requests that exceed this timeout are terminated. The swap duration increases proportionally to the draining timeout when long-running requests are active.
- H2: Slot-sticky app settings remain bound to the slot, not the code. After a swap, the production slot retains its own sticky settings (e.g., production database connection string) and the staging slot retains its sticky settings (e.g., staging database). Non-sticky settings swap with the code. If a non-sticky setting differs between slots, the production slot receives the staging slot's non-sticky value after the swap.
- H3: The swap operation performs a warmup of the target slot (new production) before redirecting traffic. If the target slot's health check does not pass within the warmup timeout, the swap is aborted and production continues to serve from the original slot. The swap abort is logged in the activity log.
- H4: During the swap, there is a brief window where the swap routing rules are being applied. Requests arriving during this window may be routed to either slot. Clients with ARR Affinity cookies pinned to the source slot continue to hit the source slot until the cookie expires or is cleared.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Deployment / Reliability

**Controlled:**

- App Service with a production slot and a staging slot
- Long-running request endpoint (`/slow?delay=60`) that holds a connection for 60 seconds
- Slot-sticky app setting: `DB_CONNECTION_STRING` (marked as deployment slot setting)
- Non-sticky app setting: `APP_VERSION` (not marked as deployment slot setting)
- Connection draining timeout: 30 seconds (default) and 90 seconds (extended)

**Observed:**

- Fate of in-flight requests during swap (completion vs. termination)
- Swap duration with and without active long-running requests
- App setting values post-swap (sticky vs. non-sticky)
- Health check behavior during warmup phase
- ARR Affinity cookie behavior during swap

**Scenarios:**

- S1: Swap with no active requests — baseline swap duration
- S2: Swap with active 60-second request, 30-second draining timeout — request termination
- S3: Swap with active 60-second request, 90-second draining timeout — request completion
- S4: Verify sticky vs. non-sticky setting values post-swap
- S5: Swap with failing health check on target slot — verify swap abort

**Independent run definition**: One slot swap per scenario.

**Planned runs per configuration**: 3

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy app to both slots; confirm app settings (sticky `DB_CONNECTION_STRING` differs between slots; non-sticky `APP_VERSION` differs between slots).
2. S1: Trigger swap with no active traffic; measure swap duration.
3. S2: Start a 60-second request to the source slot; immediately trigger swap with 30-second draining; observe whether the request completes or is terminated with a 503/reset.
4. S3: Repeat with 90-second draining timeout; verify 60-second request completes before swap redirects traffic.
5. S4: After swap completes, query `/config` endpoint on production slot; verify `DB_CONNECTION_STRING` is the original production value (sticky) and `APP_VERSION` is the staging value (non-sticky).
6. S5: Configure target slot health check to return 500; trigger swap; verify swap is aborted; check activity log for abort event.

## 9. Expected signal

- S1: Swap completes in 30–120 seconds with no traffic impact.
- S2: 60-second request is terminated after 30 seconds when draining timeout expires; client receives a connection reset or 503.
- S3: 60-second request completes successfully; swap takes longer by the draining window.
- S4: `DB_CONNECTION_STRING` on production slot retains its pre-swap value (sticky stays with slot); `APP_VERSION` reflects the staging slot's value (non-sticky swaps with code).
- S5: Swap is aborted; production continues serving from the original slot; activity log shows a `SwapWithPreviewFailed` or equivalent event.

## 10. Results

_Awaiting execution._

## 11. Interpretation

_Awaiting execution._

## 12. What this proves

_Awaiting execution._

## 13. What this does NOT prove

_Awaiting execution._

## 14. Support takeaway

_Awaiting execution._

## 15. Reproduction notes

- Connection draining timeout is configured per slot under **Configuration > General settings > Connection draining**. The default is 30 seconds (disabled means 0 seconds — no draining).
- Slot-sticky settings are marked via the checkbox "Deployment slot setting" in the portal or via `az webapp config appsettings set --slot-settings`. They do not swap with the app; they stay bound to the slot.
- The swap warmup phase sends requests to the target slot's root path and health check path. If both return 2xx within the timeout, the swap proceeds; otherwise it is aborted.
- Activity Log records slot swap events under the App Service resource: filter by `Operation name: Swap Web App Slots`.

## 16. Related guide / official docs

- [Set up staging environments in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots)
- [Swap operations in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#swap-operation-steps)
- [Connection draining in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#configure-auto-swap)
