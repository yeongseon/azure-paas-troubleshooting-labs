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

# Dapr Component Scoping and Isolation

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When multiple Container Apps share a Dapr component (e.g., a state store), does component scoping (`scopes` field) correctly prevent unscoped apps from accessing the component? What happens when an unscoped app attempts to use a scoped component — silent failure, error, or fallback?

## 2. Why this matters

Dapr in Container Apps is a shared infrastructure concern — components are registered at the environment level and are visible to all apps in that environment by default. Component scoping is the mechanism to restrict access, but the behavior when an app violates the scope is not well-documented. Support cases arise when:

- Multiple teams share a Container Apps environment and inadvertently use each other's state stores
- An app that should not have access to a component successfully reads data, indicating scoping is not enforced as expected
- An app that should have access is denied due to misconfigured scopes
- Dapr component updates (e.g., new `scopes` field added) affect running apps

## 3. Customer symptom

- "App B can read state that was written by App A — they should be isolated."
- "We added scopes to our Dapr component but App B is still using it."
- "Our Dapr state call is failing with a confusing error after we updated the component."
- "How do we isolate Dapr components between teams in a shared environment?"

## 4. Hypothesis

**H1 — Unscoped apps are blocked**: When a Dapr component has `scopes` configured, an app not in the scope list receives an error (likely HTTP 403 or Dapr error code) when attempting to use the component.

**H2 — Scope enforcement is at Dapr sidecar**: Scope enforcement occurs at the Dapr sidecar level, not at the external service level. The underlying Azure service (e.g., Storage Account for state store) may still be accessible via direct SDK calls from within the container.

**H3 — Component update affects running apps**: Adding or removing scopes on a running Dapr component affects immediately — no revision restart required. Running apps in the scope gain access; running apps removed from scope lose access.

**H4 — Missing component causes Dapr startup failure**: If an app references a Dapr component that does not exist, the Dapr sidecar fails to start, causing the entire replica to fail.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Container Apps |
| Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (dapr SDK) |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Config + Security

**Controlled:**

- Component `scopes` field: empty (all apps) vs. specific app IDs
- Test apps: App A (in scope) and App B (out of scope)
- Component type: state store (Azure Blob Storage)
- Component update timing: before start vs. after start

**Observed:**

- HTTP response code from Dapr sidecar for state operations
- Dapr sidecar logs for scope violation attempts
- Component update propagation time to running replicas
- Whether unscoped app can bypass Dapr via direct SDK call

## 7. Instrumentation

- App A and App B: Flask endpoints `POST /state/{key}` and `GET /state/{key}` using Dapr state API
- Dapr sidecar logs: `ContainerAppConsoleLogs` filtered for `dapr`
- Direct SDK test: App B also has an endpoint `GET /direct/{key}` accessing the same Azure Blob Storage directly (bypassing Dapr)

**Scope violation query:**

```kusto
ContainerAppConsoleLogs
| where ContainerAppName == "app-b"
| where Log contains "scope" or Log contains "403" or Log contains "forbidden"
| project TimeGenerated, Log
| order by TimeGenerated desc
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
# Create state store component with scope
az containerapp env dapr-component set \
  --name env-dapr-scope \
  --resource-group rg-dapr-scope \
  --dapr-component-name statestore \
  --yaml statestore.yaml  # includes scopes: [app-a]
```

### 8.2 Scenarios

**S1 — Scoped component, in-scope app**: App A writes and reads state. Confirm success.

**S2 — Scoped component, out-of-scope app**: App B attempts to write/read state. Record error code and message.

**S3 — Direct SDK bypass**: App B accesses Azure Storage directly (not via Dapr). Confirm whether scope enforcement prevents this.

**S4 — Dynamic scope update**: Remove App A from scope while it has active state sessions. Add App B to scope. Observe propagation without restart.

**S5 — Missing component**: Deploy an app with `dapr.io/app-id` annotation referencing a non-existent component in its code. Observe whether sidecar starts and what happens on the first state call.

## 9. Expected signal

- **S1**: App A: state operations succeed.
- **S2**: App B: receives Dapr error 403 or equivalent. Error message includes component name.
- **S3**: App B: direct SDK access succeeds if Azure RBAC allows it — scope enforcement is Dapr-only.
- **S4**: Scope updates propagate within ~30–60s to running replicas.
- **S5**: Dapr sidecar starts normally. Error occurs at first state API call (component not found error).

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Dapr component scoping only applies to the Dapr API layer. It does not prevent direct access to the underlying Azure service via SDK.
- Component update propagation timing may vary based on environment size and Dapr component controller refresh interval.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Scoped component blocks out-of-scope Dapr API calls | **Strongly Suggested** (documented behavior) |
| Direct SDK access bypasses Dapr scoping | **Inferred** |
| Scope updates propagate without revision restart | **Unknown** |

## 14. Related experiments

- [Dapr Sidecar Failures](../liveness-probe-failures/overview.md) — Dapr sidecar startup and failure modes
- [Secret Ref Provisioning Failure](../liveness-probe-failures/overview.md) — Dapr component secret configuration

## 15. References

- [Dapr component scopes in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/dapr-component-connection#component-scopes)
- [Dapr component types](https://learn.microsoft.com/en-us/azure/container-apps/dapr-overview#dapr-components)

## 16. Support takeaway

For Dapr component isolation issues in shared environments:

1. Component `scopes` field lists app IDs (not app names) that are allowed to use the component. Verify the `dapr.io/app-id` annotation matches exactly what's in the scope list.
2. Scope enforcement is Dapr API-level only. If a container has Azure RBAC permissions to the underlying storage directly, it can bypass Dapr scoping entirely.
3. When updating component scopes, changes propagate to running replicas without requiring a restart. Allow ~60s for propagation before testing.
4. A missing or misconfigured Dapr component does NOT prevent the sidecar from starting. The error occurs at the first API call to that component.
5. For strict isolation between teams, use separate Container Apps environments rather than relying on component scoping alone.
