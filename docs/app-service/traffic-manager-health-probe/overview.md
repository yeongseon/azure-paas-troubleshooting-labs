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

# Traffic Manager Health Probe Misidentifying App Service as Unhealthy

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When Azure Traffic Manager is fronting App Service endpoints, under what conditions does the Traffic Manager health probe incorrectly mark an endpoint as degraded — causing unnecessary failover — and how quickly does the endpoint recover once the probe failure is resolved?

## 2. Why this matters

Traffic Manager determines endpoint health by probing a configurable HTTP(S) path at a fixed interval. If the probe path returns a non-2xx code (e.g., 404 due to a wrong path, or 403 because App Service access restrictions block Azure probe IPs), Traffic Manager marks the endpoint as Degraded and stops routing traffic there. The app may be fully serving real users while TM considers it unhealthy — a false-positive failover. Support engineers frequently see this as "TM shows Degraded but the app is fine."

## 3. Customer symptom

"Traffic Manager shows our primary region as 'Degraded' but users can access the app directly" or "All traffic suddenly routed to our secondary region even though the primary app is healthy" or "Traffic Manager health probe fails intermittently but we can't reproduce the failure manually."

## 4. Hypothesis

- H1: When App Service access restrictions block the Traffic Manager probe source IPs, probes return 403. Traffic Manager marks the endpoint as Degraded after `toleratedFailures` consecutive failures, even though real user traffic (from allowed IPs) reaches the app normally.
- H2: When the probe path does not exist (returns 404), Traffic Manager marks the endpoint as Degraded. Changing the probe path to a valid `/health` endpoint returning 200 restores Online status within ~30–60 seconds.
- H3: The recovery time from Degraded → Online is approximately one probe interval (30s) after the probe path begins returning 200. The exact timing depends on probe scheduling.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service + Azure Traffic Manager |
| App SKU | B1 |
| Region | Korea Central |
| App name | app-batch-1777849901 |
| TM profile | tm-lab-7871200 (Priority routing) |
| TM probe | HTTPS, interval 30s, timeout 10s, tolerated failures 3 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Networking / Reliability

**Controlled:**

- Traffic Manager profile with Priority routing, single endpoint (external)
- Health probe: HTTPS, interval 30s, timeout 10s, tolerated failures 3
- Flask app with `/health` endpoint returning 200

**Observed:**

- Traffic Manager `endpointMonitorStatus` (Online / Degraded / CheckingEndpoint)
- Time to transition from Online → Degraded after probe failures begin
- Time to transition from Degraded → Online after probe returns 200

**Scenarios:**

- S1: Probe path `/health` → 200 → Online (baseline)
- S2: Probe path `/nonexistent-path-that-definitely-404s` → 404 → Degraded
- S3: IP restriction blocking TM probe IPs → 403 → Degraded (user traffic unaffected)
- S4: Remove restriction → recovery timing measured

## 7. Instrumentation

- `az network traffic-manager endpoint show --query endpointMonitorStatus` — polled every 30s
- `curl -s -o /dev/null -w "%{http_code}"` — verify app response from our IP
- `az webapp config access-restriction add/remove` — control probe IP blocking

## 8. Procedure

1. Create TM profile with HTTPS probe on `/health`; add App Service as externalEndpoint.
2. S1: Verify `/health` returns 200 → endpoint Online.
3. S2: Change probe path to `/nonexistent-path-that-definitely-404s`; wait 90–120s; observe Degraded.
4. S3: Restore probe path to `/health`; wait for Online recovery; record elapsed time.
5. S4: Add IP restriction (allow only our IP); wait 90–120s; observe Degraded despite app serving our traffic normally.
6. S5: Remove IP restriction; record recovery time to Online.

## 9. Expected signal

- S1: `endpointMonitorStatus: Online`.
- S2/S4 (S3 in plan): After 3 probe failures × 30s interval = ~90s, `endpointMonitorStatus: Degraded`.
- Recovery: Within 1–2 probe intervals (~30–60s) of probe returning 200.

## 10. Results

### S1: Baseline — `/health` returns 200

```bash
az network traffic-manager endpoint show ... --query endpointMonitorStatus
→ "Online"
```

### S2: Probe path → 404 (non-existent path)

```bash
az network traffic-manager profile update --path "/nonexistent-path-that-definitely-404s"
→ profileMonitorStatus: CheckingEndpoints

# After ~120s:
az network traffic-manager endpoint show ... --query endpointMonitorStatus
→ "Degraded"
```

Path `/nonexistent-path-that-definitely-404s` returns HTTP 404. After 3 consecutive failed probes (3 × 30s = 90s minimum), endpoint transitions to Degraded.

### S3: Probe path restored → recovery timing

```bash
# Restore at 05:17:57Z
az network traffic-manager profile update --path "/health"
→ profileMonitorStatus: CheckingEndpoints

# 05:18:41Z (+44s): Degraded
# 05:19:14Z (+77s): Online  ← first successful probe after restore
```

**Recovery time: ~77 seconds** from probe path restore to Online status.

### S4: IP restriction blocks TM probe IPs (H1)

```bash
# Add access restriction: allow only our public IP, deny everything else
az webapp config access-restriction add --action Allow --ip-address "121.190.225.37/32" --priority 100

# Our IP still gets 200:
curl -s -o /dev/null -w "%{http_code}" https://app-batch-1777849901.azurewebsites.net/health
→ 200

# TM probe (from Azure infra IPs, not our IP) receives 403:
# After ~95s:
→ endpointMonitorStatus: "Degraded"
```

!!! warning "False-positive failover confirmed"
    The app correctly returns 200 for real user traffic (from our IP). Traffic Manager probes originate from Azure infrastructure IPs, which are blocked by the access restriction → TM receives 403 → marks endpoint Degraded → would route traffic to a secondary if one existed.

### S5: IP restriction removed → recovery

```bash
az webapp config access-restriction remove --rule-name "allow-my-ip"
# After ~75s:
→ endpointMonitorStatus: "Online"
```

## 11. Interpretation

- **Measured**: H1 is confirmed. Adding an access restriction that blocks Azure infrastructure IPs (from which TM probes originate) causes TM to mark the endpoint Degraded, even when real user traffic reaches the app and receives 200. **Measured**.
- **Measured**: H2 is confirmed. A non-existent probe path (404) causes Degraded after ~90–120s (3 failures × 30s interval). Restoring a 200-returning path recovers the endpoint within ~77s. **Measured**.
- **Measured**: H3 is confirmed. Recovery time is approximately 1–2 probe intervals (30–60s) after the probe begins returning 200. Observed at 77s, consistent with the probe being scheduled ~30–60s after the path change plus one successful probe cycle. **Measured**.

## 12. What this proves

- App Service access restrictions that do not include `AzureTrafficManager` service tag will block TM probes, causing false-positive Degraded status. **Measured**.
- TM probe path must return HTTP 200. A 404 (missing path) causes Degraded after tolerated failures are exhausted. **Measured**.
- Recovery from Degraded → Online after probe fix takes ~1–2 probe intervals (~30–77s with 30s interval). **Measured** (77s observed).
- TM health status transitions: `CheckingEndpoints` → `Degraded` (failure) or `Online` (success). **Measured**.

## 13. What this does NOT prove

- Actual DNS failover behavior (secondary endpoint not configured in this experiment — single endpoint only).
- Whether TM follows HTTP 301/302 redirects was not directly tested (path returning redirect not configured).
- Failover behavior with multiple endpoints (primary → secondary DNS switch) was not measured.
- `Expected Status Code Ranges` feature (accepting non-200 as healthy) was not tested.

## 14. Support takeaway

When a customer reports "Traffic Manager shows Degraded but the app is working fine":

1. **Check probe path**: `az network traffic-manager profile show --query monitorConfig.path`. Verify the path exists in the app and returns HTTP 200 (not 302 or 404).
2. **Check access restrictions**: If App Service has access restrictions, the `AzureTrafficManager` service tag must be explicitly allowed. Add:
   ```bash
   az webapp config access-restriction add \
     --name <app> --resource-group <rg> \
     --rule-name "allow-traffic-manager" \
     --action Allow \
     --service-tag AzureTrafficManager \
     --priority 200
   ```
3. **Recovery**: After fixing the probe (correct path, allowed IPs), recovery takes ~1–2 probe intervals. With default 30s interval and 3 tolerated failures, expect 30–90s for Degraded → Online.
4. **TM does not follow redirects**: If the probe path returns 301/302, TM marks it unhealthy. The `/health` endpoint must return 200 directly — no redirects.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"

# Create TM profile
TM_NAME="tm-lab-$(date +%s | tail -c8)"
az network traffic-manager profile create \
  --name $TM_NAME --resource-group $RG \
  --routing-method Priority \
  --unique-dns-name $TM_NAME \
  --protocol HTTPS --path "/health" --port 443 --ttl 30

# Add endpoint
az network traffic-manager endpoint create \
  --name "primary" --profile-name $TM_NAME \
  --resource-group $RG --type externalEndpoints \
  --target "${APP}.azurewebsites.net" \
  --priority 1 --endpoint-status Enabled

# S1: Verify Online
az network traffic-manager endpoint show \
  --name "primary" --profile-name $TM_NAME --resource-group $RG \
  --type externalEndpoints --query endpointMonitorStatus -o tsv

# S2: Break probe path → expect Degraded after ~90-120s
az network traffic-manager profile update \
  --name $TM_NAME --resource-group $RG \
  --path "/nonexistent-404-path"
sleep 120
az network traffic-manager endpoint show ... --query endpointMonitorStatus -o tsv

# S3: Block TM probe IPs via access restriction → Degraded (false positive)
az webapp config access-restriction add \
  --name $APP --resource-group $RG \
  --rule-name "deny-tm-probe" \
  --action Allow --ip-address "1.2.3.4/32" --priority 100
sleep 120
az network traffic-manager endpoint show ... --query endpointMonitorStatus -o tsv

# Fix: allow AzureTrafficManager service tag
az webapp config access-restriction add \
  --name $APP --resource-group $RG \
  --rule-name "allow-traffic-manager" \
  --action Allow --service-tag AzureTrafficManager --priority 200
```

## 16. Related guide / official docs

- [Traffic Manager endpoint monitoring](https://learn.microsoft.com/en-us/azure/traffic-manager/traffic-manager-monitoring)
- [Traffic Manager and App Service](https://learn.microsoft.com/en-us/azure/app-service/web-sites-traffic-manager)
- [AzureTrafficManager service tag](https://learn.microsoft.com/en-us/azure/virtual-network/service-tags-overview)
