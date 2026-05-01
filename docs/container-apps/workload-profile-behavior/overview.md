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

# Workload Profile Behavior Differences: Dedicated vs Consumption

!!! info "Status: Planned"

## 1. Question

When the same Container App workload runs on a Dedicated workload profile versus the Consumption profile within the same environment, are there observable behavioral differences in startup latency, scaling responsiveness, networking capabilities (UDR, NAT Gateway), and resource limit enforcement?

## 2. Why this matters

Azure Container Apps supports two execution environments: Consumption-only (serverless) and Workload Profiles (which adds Dedicated profiles alongside Consumption). Customers migrating workloads between profiles, or choosing a profile type for the first time, encounter differences in UDR support, NAT Gateway attachment, CPU/memory limits, and cold-start behavior that are not always clear from documentation alone. Support engineers need concrete behavioral reference points to triage profile-related issues.

## 3. Customer symptom

"My Container App worked fine on Consumption but fails after moving to a Dedicated profile" or "I can't attach a NAT Gateway to my Consumption-only environment" or "Scale-to-zero works on Consumption but my Dedicated profile always keeps at least one replica."

## 4. Hypothesis

- H1: Dedicated workload profiles support UDR and NAT Gateway attachment at the environment level; Consumption-only environments do not — attempting to attach a NAT Gateway to a Consumption-only environment fails with a platform error.
- H2: Scale-to-zero (`minReplicas=0`) behaves differently between Consumption and Dedicated profiles: Consumption may scale to zero within seconds of idle; Dedicated profiles may have a longer cool-down window due to reserved node capacity.
- H3: Cold-start latency (time from first request to first HTTP 200 after scale-from-zero) may differ between Consumption and Dedicated profiles. Consumption cold-starts include infrastructure provisioning time; Dedicated profiles on pre-warmed nodes skip this step. Whether the latency difference is consistently measurable — and at what magnitude — is the subject of this experiment.
- H4: CPU throttling enforcement differs: Consumption workloads may be subject to noisy-neighbor effects on shared nodes; Dedicated workloads are isolated on reserved nodes with stricter but more predictable CPU limits.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption + Dedicated (D4 profile) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Platform behavior / Configuration

**Controlled:**

- Same container image deployed to both Consumption and Dedicated profile
- Same resource request/limit (`0.5 vCPU, 1 Gi`)
- Same scaling rules (`minReplicas=0, maxReplicas=5`)
- Same ingress configuration

**Observed:**

- Cold-start latency (first request after scale-to-zero)
- Scale-to-zero timing after traffic stops
- CPU burst behavior under sustained load
- UDR/NAT Gateway attachment success/failure per environment type

**Scenarios:**

- S1: Consumption profile — cold-start latency measurement (10 cold starts)
- S2: Dedicated (D4) profile — same cold-start measurement
- S3: Consumption — scale-to-zero timing after 0 req/s for 5 minutes
- S4: Dedicated — scale-to-zero timing under same idle condition
- S5: Attempt NAT Gateway attachment on Consumption-only environment

**Independent run definition**: One cold-start event = one request after confirmed 0-replica state.

**Planned runs per configuration**: 10 (cold-start), 3 (scale-to-zero timing)

## 7. Instrumentation

- `az containerapp replica list` — replica count over time
- Time measurement: HTTP request sent → HTTP 200 received (cold-start latency)
- `ContainerAppSystemLogs` — scaling events and replica state transitions
- CPU metrics: `UsageNanoCores` per replica during sustained load
- NAT Gateway attachment: `az network nat gateway` + Container Apps environment association (S5)
- Application Insights: `requests` table — response time distribution

## 8. Procedure

_To be defined during execution._

### Sketch

1. Create Workload Profiles environment with both Consumption and Dedicated (D4) profiles.
2. Deploy identical Container App to each profile.
3. Run 10 cold-start tests on Consumption (S1): confirm 0 replicas, send request, record latency.
4. Run same 10 cold-start tests on Dedicated (S2): record latency.
5. Apply 5-minute idle period to both; measure scale-to-zero timing (S3, S4).
6. Attempt NAT Gateway attachment on a separate Consumption-only environment (S5); record error.
7. Compare latency distributions between S1 and S2; compare scale-to-zero timing between S3 and S4.

## 9. Expected signal

- S1 vs S2: Dedicated cold-start latency is lower (~1–2s) vs. Consumption (~3–8s due to node provisioning).
- S3 vs S4: Both profiles scale to zero with `minReplicas=0`; Consumption may scale faster (~1–2 min); Dedicated may retain a node longer.
- S5: NAT Gateway attachment fails on Consumption-only environment with a platform-level error about unsupported networking feature.

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

- Workload Profiles environments require explicit creation (`az containerapp env create --enable-workload-profiles`); Consumption-only is the default.
- Dedicated profiles have a minimum cost even with 0 replicas (reserved node); factor this into cost comparisons.
- Cold-start tests must confirm 0 replicas before each measurement; use `az containerapp replica list` to verify.
- NAT Gateway tests require a separate Consumption-only environment; do not reuse the Workload Profiles environment.

## 16. Related guide / official docs

- [Workload profiles in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/workload-profiles-overview)
- [Networking in Azure Container Apps environment](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Set scaling rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
