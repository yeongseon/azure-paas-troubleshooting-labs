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

# Connection String Slot Override: Database Pointing to Wrong Environment

!!! info "Status: Planned"

## 1. Question

App Service connection strings can be configured as slot-sticky (deployment slot settings) or non-sticky. When a connection string is not marked sticky and a slot swap occurs, the production slot receives the staging slot's connection string — potentially pointing production traffic at the staging database. What are the exact conditions under which this occurs, and how quickly can it be detected and reversed?

## 2. Why this matters

Connection string misconfiguration after a slot swap is one of the most severe deployment incidents in App Service: production traffic may write data to the staging database or read stale staging data. The impact is silent — the app appears healthy (HTTP 200), but data is flowing to the wrong store. The connection string swap happens in seconds during the slot swap, and detecting it requires checking the connection string values post-swap rather than observing application errors. Recovery requires another swap or manual connection string update.

## 3. Customer symptom

"After a slot swap, production data appears in our staging database" or "Users are seeing staging data in the production app" or "We swapped to deploy a fix but now the app connects to the wrong database" or "The connection string in the portal shows the staging value after swap."

## 4. Hypothesis

- H1: When `DATABASE_URL` is set as a non-sticky connection string in both production and staging slots with different values, a slot swap causes the production slot to receive the staging slot's `DATABASE_URL` value. The production slot now points to the staging database.
- H2: When `DATABASE_URL` is marked as a deployment slot setting (sticky), it does not swap — each slot retains its own connection string value regardless of which code version is deployed to it.
- H3: The slot swap takes effect immediately after the swap operation completes (traffic shifts). There is no gradual rollout of connection string values — all instances in the slot receive the new connection string simultaneously on the next worker recycle.
- H4: The swap can be reversed by performing another slot swap, which restores the original connection string values. The recovery time is the same as the original swap duration.

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

**Experiment type**: Deployment / Data safety

**Controlled:**

- App Service with production and staging slots
- `DATABASE_URL` connection string set to different values in each slot
- Sticky and non-sticky configuration variants

**Observed:**

- `DATABASE_URL` value seen by the application post-swap
- Whether the app connects to production or staging database
- Recovery time via reverse swap

**Scenarios:**

- S1: `DATABASE_URL` non-sticky → verify swap causes cross-connection
- S2: `DATABASE_URL` sticky → verify swap does not change connection string
- S3: Reverse swap after S1 → verify connection strings restored

## 7. Instrumentation

- App `/db-info` endpoint returning the database hostname from the active connection string (not the password)
- App Service **Configuration > Connection strings** blade post-swap
- Database write audit log to observe which database received requests

## 8. Procedure

_To be defined during execution._

### Sketch

1. Set `DATABASE_URL=postgresql://prod-db/app` in production slot (non-sticky).
2. Set `DATABASE_URL=postgresql://staging-db/app` in staging slot (non-sticky).
3. S1: Perform slot swap; immediately check `/db-info` on production; confirm it now shows `staging-db`.
4. Write a test record to production after swap; verify it appears in staging database.
5. S2: Mark `DATABASE_URL` as deployment slot setting (sticky) in both slots; perform swap; verify each slot retains its original connection string.
6. S3: Perform reverse swap from S1 state; verify connection strings are restored.

## 9. Expected signal

- S1: Post-swap, production slot shows `DATABASE_URL=postgresql://staging-db/app`; writes go to staging database.
- S2: Post-swap, each slot retains its own `DATABASE_URL`; no cross-connection.
- S3: Reverse swap restores original connection strings within the standard swap duration (~30-120 seconds).

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

- Mark a connection string as sticky: **Configuration > Connection strings** → check "Deployment slot setting" for each entry, or use `az webapp config connection-string set --slot-settings`.
- Connection strings swap with the slot unless marked sticky. This is the same behavior as app settings.
- Best practice: ALL environment-specific connection strings (databases, storage accounts, service bus) should be marked sticky to prevent accidental cross-environment connections during slot swaps.

## 16. Related guide / official docs

- [Set up staging environments in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots)
- [Deployment slot settings](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#which-settings-are-swapped)
