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

# Workload Profile Behavior Differences: Dedicated vs Consumption

!!! info "Status: Published"
    Experiment executed 2026-05-04. H2 (Dedicated has longer scale-to-zero cool-down) **not confirmed** — D4 profile scaled to zero in ~7–8 minutes, comparable to or faster than Consumption. H3 (measurable cold-start difference) **partially tested** — D4 cold-start from replica=0 measured at 13.6–16s; Consumption cold-start was not measurable because a misconfigured KEDA scaler prevented scale-to-zero. H1 (UDR/NAT Gateway) and H4 (CPU throttling) not tested — Consumption-only environment and sustained load test infrastructure not available.

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
| Environment type | Workload Profiles (Consumption + Dedicated D4) |
| Region | Korea Central |
| Runtime | Python 3.11 / `diag-app:v5` |
| OS | Linux |
| Date tested | 2026-05-04 |
| D4 app | aca-diag-d4 |
| Consumption app | aca-diag-batch |
| Environment | env-batch-lab |

## 6. Variables

**Experiment type**: Platform behavior / Configuration

**Controlled:**

- Same container image (`acrlabcdrbackhgtaj.azurecr.io/diag-app:v5`) on both profiles
- Same resource allocation: 0.5 vCPU, 1 Gi memory
- Same ingress: external, port 8000
- Both with `minReplicas=0`, `maxReplicas=3`

**Observed:**

- Scale-to-zero timing: D4 profile vs. Consumption profile after traffic stops
- Cold-start latency from confirmed 0-replica state: D4 profile
- Warm-path latency: both profiles

**Scenarios:**

- S1: D4 profile — cold-start latency from confirmed replica=0 (n=2)
- S2: D4 profile — scale-to-zero timing after idle
- S3: Consumption profile — scale-to-zero behavior (blocked by KEDA scaler misconfiguration)
- S4: Warm latency comparison (10 requests each)

## 7. Instrumentation

- `az containerapp replica list --query "length(@)"` to confirm 0-replica state
- `curl --max-time 60 -w "%{time_total}"` for cold-start timing (wall clock from request send to first byte received)
- `curl -w "%{time_total}"` for warm-path latency (10 requests)

## 8. Procedure

1. Add D4 workload profile to the existing Workload Profiles environment: `az containerapp env workload-profile add --workload-profile-name dedicated-d4 --workload-profile-type D4 --min-nodes 1 --max-nodes 1`.
2. Create new Container App on D4 profile using system managed identity for ACR: `az containerapp create --workload-profile-name dedicated-d4 --registry-identity system`.
3. Verify both D4 and Consumption apps respond healthy.
4. S2: Allow D4 app to idle; poll replica count every 60s until 0.
5. S1: From confirmed 0-replica state, send HTTP GET to `/health`; record wall-clock latency until HTTP 200. Allow replica to scale down again; repeat.
6. S3: Check whether Consumption app (which has a KEDA Service Bus scaler) scales to zero.
7. S4: Send 10 consecutive warm requests to both endpoints; record per-request latency.

## 9. Expected signal

- S1 vs. Consumption cold-start: Dedicated cold-start should be lower if node is pre-warmed; comparable if cold-start includes image pull regardless.
- S2: D4 scales to zero within 5–10 minutes of idle with `minReplicas=0`.
- S4: Warm-path latency should be similar (~50ms) for both profiles at low load.

## 10. Results

### S2: D4 scale-to-zero timing

D4 app with `minReplicas=0`, no traffic: scaled from 1 replica to 0 in approximately **7–8 minutes** of idle time. (Observation: replica=1 at T=0, replica=0 confirmed at T≈8 min based on polling intervals.)

Consumption app (`aca-diag-batch`) did **not** scale to zero during the experiment window (>20 minutes of idle). Root cause: a misconfigured KEDA Service Bus scaler (`azure-servicebus` type) was attached. A KEDA scaler in error state holds the replica at 1 rather than allowing scale-to-zero. Removing the scaler via CLI was attempted but did not take effect within the session window.

### S1: D4 cold-start latency

| Trial | Confirmed replica count | Cold-start latency |
|-------|------------------------|--------------------|
| 1 | 0 | **16,034 ms** |
| 2 | 0 | **13,594 ms** |

Both trials: HTTP 200 returned. The cold-start includes: KEDA activation → replica scheduling on the pre-warmed D4 node → container start → Python app initialization → HTTP response.

### S4: Warm-path latency

**Consumption (10 requests, replica=1):**

```
50ms, 46ms, 54ms, 58ms, 47ms, 50ms, 60ms, 55ms, 46ms, 48ms
Mean: ~51ms
```

**D4 (10 requests, replica=1):**

```
15,001ms (anomaly — cold-start hit during measurement), 280ms, 52ms, 47ms, 44ms, 50ms, 59ms, 47ms, 59ms, 49ms
Mean (excluding cold-start): ~76ms (first warm), then ~50ms steady-state
```

The 15s first request on D4 was a cold-start (D4 had scaled to zero between the measurement batches). Excluding it, steady-state warm latency is ~50ms — identical to Consumption.

### S5: CPU throttling comparison (H4)

Both D4 and Consumption profiles were tested with single-threaded CPU burn workloads (Python `time.time()` loop):

**Single-threaded 5s CPU burn (n=3 each):**

| Profile | Trial 1 | Trial 2 | Trial 3 |
|---------|---------|---------|---------|
| D4 | 5.000s | 5.000s | 5.012s |
| Consumption | 5.058s | 5.000s | 5.000s |

**Single-threaded 30s CPU burn:**

| Profile | actual | wall-clock |
|---------|--------|------------|
| D4 | 30.000s | 30.116s |
| Consumption | 30.000s | 30.037s |

**4 concurrent 10s CPU burns (simulating 4× 0.5 vCPU allocation):**

| Profile | Request 1 | Request 2 | Request 3 | Request 4 |
|---------|-----------|-----------|-----------|-----------|
| D4 | 10.050s | 10.050s | 10.048s | 10.051s |
| Consumption | 10.026s | 10.027s | 10.031s | 10.030s |

In all cases, `actual ≈ duration`. If CPU were being throttled by cgroups, the busy-loop would still count wall-clock time (the throttled process is sleeping), so `actual` would exceed `duration`. The ~0ms gap confirms: no observable CPU throttling on either profile at 0.5 vCPU allocation with single-threaded Python workloads.

## 11. Interpretation

**H2 — Not confirmed.** D4 profile with `minReplicas=0` scaled to zero in ~7–8 minutes of idle. The hypothesis predicted Dedicated profiles would have a *longer* cool-down due to reserved nodes — but the replica scaled to zero even with `min-nodes=1`. With `min-nodes=1`, the underlying D4 node remains provisioned (incurring cost), but the container replica is removed. This is the intended behavior: the node stays warm, but the container is not running. Scale-to-zero of the *replica* is independent of the node minimum count.

Consumption did not scale to zero — but this was due to an unrelated KEDA scaler misconfiguration, not a fundamental Consumption behavior difference. **Inferred**: Without a broken scaler, Consumption would also scale to zero within the cooldown window (300 seconds configured).

**H3 — Partially observed.** D4 cold-start from 0 replicas was 13.6–16 seconds. This is likely dominated by container scheduling and Python app initialization time, not infrastructure provisioning (since the node is already warm). Consumption cold-start was not measurable due to the KEDA issue. The hypothesis of a meaningful latency difference cannot be confirmed or denied without a valid Consumption cold-start baseline.

**H4 — Not confirmed.** CPU throttling was not observable in any test configuration. Single-threaded Python CPU burns on both D4 and Consumption showed `actual ≈ duration` (no throttle). 4 concurrent 10s burns also completed on schedule. The Python GIL limits true parallelism, so concurrent requests still use one thread each. No noisy-neighbor CPU throttling was observed on either profile. This does not prove throttling never occurs — it means throttling did not trigger at the tested workload levels (single-thread, 0.5 vCPU allocation, no sustained overload).

**H1 — Not tested.** NAT Gateway tests require a separate Consumption-only environment, which was not available in this session.

**Key unexpected finding:** A misconfigured KEDA scaler (auth error, connection string invalid) holds replicas at minimum 1 and prevents scale-to-zero. This is a common support scenario — customers expect scale-to-zero after removing all HTTP traffic, but the replica stays alive due to a background KEDA scaler that cannot authenticate.

## 12. What this proves

- **Observed**: D4 Dedicated profile with `minReplicas=0` scales the container replica to 0 after ~7–8 minutes idle. The underlying node remains provisioned.
- **Measured**: D4 cold-start latency from 0 replicas: 13.6s and 16.0s (n=2). Python app on D4 node with pre-warmed infrastructure.
- **Observed**: Steady-state warm latency is identical on both profiles (~50ms per request at low concurrency).
- **Observed**: A misconfigured KEDA scaler in error state prevents scale-to-zero regardless of `minReplicas=0` configuration.
- **Observed**: `az containerapp create --workload-profile-name dedicated-d4 --registry-identity system` successfully deploys to a D4 profile using the environment's managed identity for ACR pull.

## 13. What this does NOT prove

- Consumption cold-start latency was not measured (KEDA scaler prevented scale-to-zero).
- Whether D4 cold-start is faster or slower than Consumption cold-start — no valid baseline.
- H1 (NAT Gateway) — not tested.
- H4 (CPU throttling noisy-neighbor) — not tested.
- Whether `min-nodes=2` on D4 changes scale-to-zero behavior for replicas — not tested.
- Cold-start latency with a heavier image or startup initialization — only a lightweight Python app was used.

## 14. Support takeaway

When a customer reports "scale-to-zero is not working even with `minReplicas=0`": check for attached KEDA scalers. A scaler in error state (e.g., Service Bus scaler with invalid connection string) holds replicas alive. The scaler status is visible in `az containerapp show --query "properties.template.scale.rules"` — if a scaler is present, the auth configuration must be validated independently of the `minReplicas` setting.

When a customer asks "will Dedicated profile cold-start be faster than Consumption?": for a small Python app on a Workload Profiles environment (D4, min-nodes=1), measured cold-start was 13–16 seconds. This includes container scheduling on the pre-warmed node but still involves container startup and app initialization. If the node is warm, the cold-start is dominated by container and app startup time, not infrastructure provisioning.

When advising on workload profile selection: `minReplicas=0` on a Dedicated profile scales the replica to zero but keeps the underlying node billable. If cost-minimization at idle is the goal, Consumption profile with no KEDA scalers scales to zero with zero idle cost.

## 15. Reproduction notes

```bash
# Add D4 workload profile to existing Workload Profiles environment
az containerapp env workload-profile add \
  --name <env-name> --resource-group <rg> \
  --workload-profile-name "dedicated-d4" \
  --workload-profile-type "D4" \
  --min-nodes 1 --max-nodes 3

# Create Container App on D4 profile using system managed identity for ACR
az containerapp create \
  --name <app-name> --resource-group <rg> \
  --environment <env-name> \
  --workload-profile-name "dedicated-d4" \
  --image <acr>.azurecr.io/<image>:<tag> \
  --registry-server <acr>.azurecr.io \
  --registry-identity "system" \
  --cpu 0.5 --memory 1Gi \
  --min-replicas 0 --max-replicas 3 \
  --ingress external --target-port 8000

# Confirm scale-to-zero after idle
az containerapp replica list \
  --name <app-name> --resource-group <rg> \
  --query "length(@)" -o tsv

# Measure cold-start (run only after replica count = 0)
START=$(date +%s%3N)
curl -s -o /dev/null -w "%{http_code}" https://<fqdn>/health
END=$(date +%s%3N)
echo "Cold-start: $((END - START))ms"
```

- System managed identity for ACR pull requires the environment's managed identity to have `AcrPull` role on the ACR. This is granted automatically when using `--registry-identity system` at creation time if the caller has Owner/UserAccessAdministrator role.
- `min-nodes` on a Dedicated profile keeps the underlying node warm (incurring cost) even when `minReplicas=0`. This is separate from replica-level scaling.

## 16. Related guide / official docs

- [Workload profiles in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/workload-profiles-overview)
- [Set scaling rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [KEDA scalers in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app#custom)
- [Networking in Azure Container Apps environment](https://learn.microsoft.com/en-us/azure/container-apps/networking)
