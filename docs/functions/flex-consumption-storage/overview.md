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

# Flex Consumption Storage Identity Edge Cases

!!! warning "Status: Draft - Blocked"
    Execution blocked: Flex Consumption plan creation blocked by Azure Policy.

## 1. Question

What happens when a Flex Consumption Function App has a misconfigured storage identity (managed identity for storage account access), and how does the failure manifest to the developer and in platform telemetry?

## 2. Why this matters

Flex Consumption uses managed identity for storage account access instead of connection strings. When the identity is changed, revoked, or the role assignment is incorrect, the failure mode is not always obvious. Functions may deploy successfully but fail to discover triggers, or triggers may stop firing after an identity rotation. Support engineers need to recognize these failure patterns quickly.

## 3. Customer symptom

"My Function App deploys but functions don't appear" or "Triggers stopped firing after I rotated the managed identity."

## 4. Hypothesis

When storage identity configuration is invalid on Flex Consumption, the app can remain deployed but runtime behaviors degrade in identifiable ways: trigger indexing/discovery and trigger execution will fail with storage-authorization-related signals until identity and role bindings are corrected.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Functions |
| SKU / Plan | Flex Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Managed identity configuration (system-assigned, user-assigned)
- Storage account role assignments
- Identity rotation timing

**Observed:**

- Function discovery behavior
- Trigger firing status
- Error messages in platform logs
- Runtime startup behavior
- Application Insights telemetry

## 7. Instrumentation

- Function host logs and startup diagnostics
- Azure Portal Function list and trigger status views
- Application Insights traces, exceptions, and operation logs
- Azure Activity Log and RBAC assignment history
- Azure CLI checks for identity principal IDs and role bindings

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Removing required storage roles causes trigger discovery and/or execution failures without necessarily failing deployment.
- Identity rotation without matching role updates produces immediate authorization errors in runtime logs.
- Restoring correct role assignment to the active identity returns trigger visibility and firing behavior.
- Failure symptoms are consistent with storage-access authorization patterns rather than application-code defects.

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

- Wait for RBAC propagation after each role change before recording final behavior.
- Capture principal ID before and after identity rotation to avoid misattributed permissions.
- Test one misconfiguration at a time so signals map to a single root condition.
- Keep storage account network rules stable during testing to isolate identity effects.

## 16. Related guide / official docs

- [Microsoft Learn: Flex Consumption plan](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
