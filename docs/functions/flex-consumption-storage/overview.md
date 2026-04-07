# Flex Consumption Storage Identity Edge Cases

!!! info "Status: Planned"

## Question

What happens when a Flex Consumption Function App has a misconfigured storage identity (managed identity for storage account access), and how does the failure manifest to the developer and in platform telemetry?

## Why this matters

Flex Consumption uses managed identity for storage account access instead of connection strings. When the identity is changed, revoked, or the role assignment is incorrect, the failure mode is not always obvious. Functions may deploy successfully but fail to discover triggers, or triggers may stop firing after an identity rotation. Support engineers need to recognize these failure patterns quickly.

## Customer symptom

"My Function App deploys but functions don't appear" or "Triggers stopped firing after I rotated the managed identity."

## Planned approach

Deploy a Flex Consumption Function App with managed identity storage access. Systematically test failure modes: revoke the identity, remove the role assignment, assign incorrect roles, and rotate to a new identity. Observe the behavior at each stage through the Azure Portal, runtime logs, and Application Insights.

## Key variables

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

## Expected evidence tags

Observed, Measured, Inferred

## Related resources

- [Microsoft Learn: Flex Consumption plan](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
