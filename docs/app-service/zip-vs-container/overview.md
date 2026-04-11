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

# Zip Deploy vs Custom Container Behavior

!!! info "Status: Planned"

## 1. Question

How do deployment method differences (zip deploy vs. custom container) affect startup time, file system behavior, and troubleshooting signal availability on App Service Linux?

## 2. Why this matters

Customers migrating between deployment methods sometimes encounter behavioral differences that are not documented. An app that works with zip deploy may behave differently in a custom container — different file system layout, different environment variable handling, different log locations. Support engineers handling "it worked before I switched to containers" tickets need to understand these differences.

## 3. Customer symptom

"My app works with zip deploy but fails with custom container" or "Startup takes much longer after switching to container deployment."

## 4. Hypothesis

For identical application code on the same App Service plan, deployment method changes the startup and diagnostics profile: custom container deployments will show different startup timing components, file system semantics, and troubleshooting surface compared with zip deploy.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 and P1v3 |
| Region | Korea Central |
| Runtime | Node.js 20 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance

**Controlled:**

- Application code (identical across both methods)
- App Service SKU and plan
- Runtime version

**Observed:**

- Startup time (cold start to first successful response)
- File system layout and writable paths
- Environment variable exposure
- Available diagnostic tools (Kudu, SSH, log stream)
- Log format and location differences

**Independent run definition**: Fresh deployment of one method, cold restart, and one complete startup-plus-verification capture cycle.

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: Exclude first deployment cache-population cycle; compare subsequent cold restarts under identical conditions.

**Primary metric and meaningful-effect threshold**: Time to first successful response; meaningful effect is >=20% relative difference between methods.

**Comparison method**: Bootstrap confidence interval on per-run startup medians with directional consistency across runs.

## 7. Instrumentation

- Application Insights request telemetry and custom startup checkpoints
- App Service platform logs and container startup logs
- Kudu/SSH inspection for file system and environment verification
- Azure Monitor metrics for restart events, CPU, and memory during startup windows
- External probe script recording first-success timestamp and HTTP readiness behavior

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Custom container and zip deploy reach healthy state through different startup sequences and timing envelopes.
- Writable path behavior and mounted volume visibility differ between deployment methods.
- Troubleshooting artifacts (log locations, access surfaces) differ even when application code is unchanged.
- Startup latency spread is higher for the method with more initialization steps.

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

- Keep image size and dependency set fixed when comparing custom container runs.
- Force cold restarts before each measured run to avoid warm-state carryover.
- Use the same health endpoint and readiness criteria for both deployment methods.
- Record log source paths during each run because path conventions differ by method.

## 16. Related guide / official docs

- [Microsoft Learn: Deploy a custom container](https://learn.microsoft.com/en-us/azure/app-service/quickstart-custom-container)
- [Microsoft Learn: Zip deploy](https://learn.microsoft.com/en-us/azure/app-service/deploy-zip)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
