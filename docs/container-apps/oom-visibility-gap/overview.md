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

# OOM Visibility Gap Across Metrics and Logs

!!! info "Status: Planned"

## 1. Question

When a Container App container is killed by the OOM (Out of Memory) killer, is this event visible in Azure Monitor metrics, Container Apps system logs, and Application Insights? Where are the gaps in observability?

## 2. Why this matters

OOM kills are a common cause of container restarts, but the visibility of these events varies dramatically across Azure's telemetry layers. If the OOM event is not surfaced in the monitoring tools that customers use, they see unexplained restarts with no clear cause. Understanding exactly where OOM events are visible (and where they are not) helps support engineers direct customers to the right diagnostic data.

## 3. Customer symptom

- "My container keeps restarting but I don't see any errors in Application Insights."
- "Container restarts happen randomly — no crash logs, no exceptions, just restart."
- "We think it might be memory but we can't find proof."

## 4. Hypothesis

When a Container App container is OOM-killed:

1. The container restart will be visible in Container Apps system logs with exit code 137
2. Azure Monitor `RestartCount` metric will increment but won't indicate the cause
3. Application Insights will show no trace of the OOM event because the process was killed before it could emit telemetry
4. The actual OOM event details (killed process, memory limit) are only visible in system-level logs

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (custom container) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Container memory limit: 0.5Gi, 1Gi
- Memory allocation pattern: gradual increase, sudden spike
- Application Insights SDK: configured vs not configured
- Logging: stdout vs structured logging to Application Insights

**Observed:**

- Container restart events and exit codes
- Azure Monitor metrics: `RestartCount`, `UsageNanoCores`, `UsageBytes`
- Container Apps system logs: OOM-related entries
- Application Insights: presence or absence of OOM evidence
- Log Analytics: container event queries

## 7. Instrumentation

- Container Apps system logs (Log Analytics)
- Azure Monitor: container metrics
- Application Insights: application traces and exceptions
- KQL queries: `ContainerAppSystemLogs_CL`, `ContainerAppConsoleLogs_CL`

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- `ContainerAppSystemLogs_CL`: container exit with code 137 (SIGKILL)
- Azure Monitor `RestartCount`: increment visible but no cause annotation
- Application Insights: NO OOM evidence (process killed before flush)
- `ContainerAppConsoleLogs_CL`: application logs stop abruptly before OOM

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

- Memory limits are set at the container level in the Container App revision
- Exit code 137 = SIGKILL (typically OOM), exit code 139 = SIGSEGV
- The OOM kill may not appear immediately in logs; check for ingestion delay

## 16. Related guide / official docs

- [Monitor Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/observability)
- [Azure Container Apps metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics)
- [Log monitoring in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
