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

# Target Port Auto-Detection Trap

!!! info "Status: Planned"

## 1. Question

When deploying a Container App without explicitly specifying the target port in the ingress configuration, does the platform auto-detect the correct port, and what failure modes occur when the detection fails or picks the wrong port?

## 2. Why this matters

Container Apps can auto-detect the listening port for some frameworks, but this detection is not reliable across all runtimes and frameworks. When the detected port doesn't match the actual application port, the app appears healthy (container is running) but all HTTP requests fail with 502 or connection refused. This is confusing because the container logs show the app is listening, but ingress can't reach it.

## 3. Customer symptom

- "My container is running and logs show it's listening on port 8080, but I get 502 errors."
- "The app works locally in Docker but not on Container Apps."
- "I didn't set a target port because the docs said it auto-detects."

## 4. Hypothesis

1. Auto-detection works for common frameworks (Express.js on 3000, Flask on 5000, ASP.NET on 80/8080) but fails for custom or non-standard ports.
2. When auto-detection picks the wrong port, the container runs successfully but ingress returns 502.
3. Container logs and health checks may show the app as healthy even though ingress can't route to it.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (Gunicorn), Node.js 20 (Express), .NET 8 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Target port configuration: auto-detect (omitted), explicitly correct, explicitly wrong
- Application frameworks: Flask/Gunicorn (8000), Express (3000), ASP.NET (8080), custom (9999)
- Ingress configuration: external, internal

**Observed:**

- HTTP response status from ingress endpoint
- Container log output (listening port)
- Ingress target port value (after auto-detection)
- Container health status vs actual reachability

## 7. Instrumentation

- Azure CLI: `az containerapp show` to inspect detected port
- External HTTP client: request to ingress endpoint
- Container Apps system logs: ingress routing events
- Container logs: application startup with port binding

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Auto-detect works: Flask default (5000→5000), Express default (3000→3000)
- Auto-detect fails: custom port (9999) → platform picks wrong port → 502
- Explicit correct port: always works regardless of framework
- Container shows running/healthy even when port mismatch causes 502

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

- Target port auto-detection behavior may change across Container Apps platform versions
- Some frameworks use environment variables (`PORT`) that Container Apps may or may not set
- Multi-container scenarios add additional port-mapping complexity

## 16. Related guide / official docs

- [Ingress in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [Azure Container Apps image configuration](https://learn.microsoft.com/en-us/azure/container-apps/containers)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
