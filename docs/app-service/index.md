---
hide:
  - toc
---

# App Service Labs

Azure App Service troubleshooting experiments focused on worker behavior, memory management, networking, deployment patterns, and platform/application boundary interpretation.

## Architecture Overview

Azure App Service runs web applications inside Docker containers on shared or dedicated virtual machines (workers). Understanding the component architecture is essential for diagnosing where failures originate.

```mermaid
graph TB
    subgraph "Azure App Service Platform"
        Client([Client]) --> FE[Frontend<br/>ARR / Load Balancer]

        FE --> W1
        FE --> W2[Worker Instance 2]

        subgraph "Worker Instance 1"
            W1[Worker 1] --> SC[Site Container<br/>Application Code]
            SC --> HOME["/home<br/>CIFS Mount<br/>(Persistent)"]
            SC --> TMP["/tmp<br/>Writable Layer<br/>(Ephemeral)"]
        end

        W1 --> SNAT[SNAT Pool<br/>Outbound Connections]
        SNAT --> EXT([External Services])

        HC[Health Check<br/>Probe] --> W1
        HC --> W2

        subgraph "App Service Plan"
            CPU[Shared CPU]
            MEM[Shared Memory]
            SWAP[Swap Space]
        end
    end

    style FE fill:#4a9eff,color:#fff
    style HC fill:#ff9800,color:#fff
    style SNAT fill:#e91e63,color:#fff
    style HOME fill:#4caf50,color:#fff
    style TMP fill:#ff5722,color:#fff
```

### Key Components for Troubleshooting

| Component | Role | Why It Matters |
|-----------|------|---------------|
| **Frontend (ARR)** | HTTP load balancer and SSL termination | ARR affinity, timeout settings, and routing decisions affect request behavior before the app sees them |
| **Worker** | VM running the application container | Workers are shared across apps in the same plan; one app's resource usage affects others |
| **App Service Plan** | Resource allocation boundary (CPU, memory) | Plan SKU determines available memory, CPU, SNAT ports, and swap behavior |
| **Health Check** | Platform probe that monitors app health | Misconfigured health checks can cause instance eviction even when the app is partially functional |
| **SNAT** | Source Network Address Translation for outbound connections | Limited port pool (128 per instance); exhaustion causes connection failures with no CPU/memory signal |
| **/home mount** | Persistent CIFS (SMB) storage shared across instances | Data survives restarts and scale events; performance is network-dependent |
| **Writable layer** | Ephemeral container filesystem overlay | Data is lost on restart, deployment, or instance migration |

!!! note
    These experiments target Linux App Service plans unless otherwise noted. Windows-specific behavior may differ.

## Experiment Status

| Experiment | Status | Description |
|-----------|--------|-------------|
| [Filesystem Persistence](filesystem-persistence/overview.md) | **Published** | /home vs writable layer data survival across restarts |
| [Health Check Eviction](health-check-eviction/overview.md) | **Published** | Cascading outage from partial dependency failure |
| [SNAT Exhaustion](snat-exhaustion/overview.md) | **Published** | Connection failures without CPU/memory pressure |
| [Memory Pressure](memory-pressure/overview.md) | **Published** | Plan-level degradation, swap thrashing, kernel page reclaim |
| [Custom DNS Resolution](custom-dns-resolution/overview.md) | **Published** | Private name resolution drift after VNet changes |
| [procfs Interpretation](procfs-interpretation/overview.md) | **Published** | /proc reliability and limits in Linux containers |
| [Slow Requests](slow-requests/overview.md) | **Published** | Frontend timeout vs. worker-side delay vs. dependency latency |
| [Zip Deploy vs Container](zip-vs-container/overview.md) | **Published** | Deployment method behavioral differences |
| [Slot Swap Warmup](slot-swap-warmup/overview.md) | **Draft** | In-flight request handling during slot swap warmup |
| [Access Restrictions SCM](access-restrictions-scm/overview.md) | **Draft** | Access restriction behavior on SCM site |
| [Deployment Slot Cold Start](deployment-slots-cold-start/overview.md) | **Draft** | Post-swap cold-start when warming fails; ARR affinity uneven warming |
| [Environment Variable Limits](environment-variable-limits/overview.md) | **Draft** | App setting count/size limits; KV reference fallback behavior |
| [Connection Timeout Cascade](connection-timeout-cascade/overview.md) | **Draft** | Thread pool saturation from slow dependencies; recovery lag |
| [Log Stream Reliability](log-stream-reliability/overview.md) | **Draft** | Log Stream buffer limits; Log Stream vs. App Insights tradeoff |
| [Container Registry Auth Expiry](container-registry-auth-expiry/overview.md) | **Draft** | Registry credential rotation impact on running vs. restarting containers |

## Published Experiments

### [Filesystem Persistence](filesystem-persistence/overview.md) — **Published**

/home mount vs writable layer persistence behavior across restarts, deployments, and scale operations. Confirms that /home (CIFS) survives all lifecycle events while the writable layer is lost on any container recreation.

??? success "Experiment Complete"
    Completed 2026-04 on B1 Linux (koreacentral). All three hypotheses confirmed with evidence from 4 trigger events across 2 instances.

### [Health Check Eviction](health-check-eviction/overview.md) — **Published**

How Health Check failures from partial dependency outages cause cascading instance eviction. Demonstrates that a single unhealthy dependency endpoint can trigger progressive instance removal.

??? success "Experiment Complete"
    Completed 2026-04 on B1 Linux (koreacentral). Documents the eviction cascade timeline and recovery behavior.

### [SNAT Exhaustion](snat-exhaustion/overview.md) — **Published**

Connection failures caused by SNAT port exhaustion without corresponding CPU or memory pressure. Shows how outbound connection patterns can exhaust the limited SNAT port pool (128 per instance) while all other metrics remain normal.

??? success "Experiment Complete"
    Completed 2026-04 on B1 Linux (koreacentral). Captures the characteristic signal pattern: connection failures with clean CPU/memory metrics.

### [Memory Pressure](memory-pressure/overview.md) — **Published**

Plan-level degradation under memory pressure. Investigates swap thrashing, kernel page reclaim effects, and cross-app impact on shared plans. Explores whether memory pressure manifests as CPU increase and how plan-level metrics can mislead per-app diagnosis.

??? success "Experiment Complete"
    Completed 2025-07. Covers B1/B2 Linux plans with multiple apps, measuring swap usage, page fault rates, CPU attribution, and cross-app latency impact.

## Planned Experiments

### [Custom DNS Resolution](custom-dns-resolution/overview.md) — **Published**

Private name resolution behavior after Private DNS Zone link changes on VNet-integrated App Service. Tests whether DNS cache drift causes intermittent failures. **Finding: DNS changes propagate immediately — the cache drift hypothesis is refuted.**

??? success "Experiment Complete"
    Completed 2026-04 on P1v3 Linux (koreacentral). Four phases tested: baseline, unlink, re-link, and rapid toggle. All DNS transitions were immediate across 80 total probes.

### [procfs Interpretation](procfs-interpretation/overview.md) — **Published**

Reliability and limits of reading `/proc` filesystem data inside App Service Linux containers. Examines where procfs values reflect the container vs. the host, and how cgroup v1/v2 boundaries affect metric interpretation.

??? success "Experiment Complete"
    Completed 2026-04 on B1/P1v3/P2v3 Linux (koreacentral). Key finding: cgroup memory and CPU limits are not enforced via cgroup (both return unlimited); `/proc/meminfo` MemTotal tracks SKU spec within 3-5%.
### [Slow Requests](slow-requests/overview.md) — **Published**

Diagnosing slow HTTP responses under pressure conditions. Distinguishes between frontend (ARR) timeout, worker-side processing delay, and downstream dependency latency. Tests how different bottleneck locations produce different diagnostic signals.

??? success "Experiment Complete"
    Completed 2026-04 on B1 Linux (koreacentral). Key finding: CPU-bound delays serialize on Node.js event loop (p50 inflates 2-3×); async dependency delays process in parallel at constant latency. ARR timeout confirmed at 230-240s.
### [Zip Deploy vs Container](zip-vs-container/overview.md) — **Published**

Behavioral differences between zip deployment and custom container deployment. Investigates startup time, file system behavior, environment variable handling, and troubleshooting signal availability across deployment methods.

??? success "Experiment Complete"
    Completed 2026-04 on B1/P1v3 Linux (koreacentral). Key finding: cold start timing is dominated by platform variance (>50% CV), not deployment method. Major differences are in filesystem layout (cwd, /home contents) and environment variables (PORT vs WEBSITES_PORT).
## Draft Experiments

### [Slot Swap Warmup](slot-swap-warmup/overview.md) — **Draft**

How in-flight requests are handled during slot swap warmup phase. Investigates whether requests are dropped, queued, or routed to the old slot during the warmup period, and what signals indicate warmup completion.

!!! info "Status: Draft - Awaiting Execution"
    Designed based on Oracle recommendations. Awaiting execution.

### [Access Restrictions SCM](access-restrictions-scm/overview.md) — **Draft**

Behavior of access restrictions on the SCM (Kudu) site. Tests whether main site access restrictions automatically apply to SCM, whether SCM has independent restrictions, and edge cases with VNet integration.

!!! info "Status: Draft - Awaiting Execution"
    Designed based on Oracle recommendations. Awaiting execution.

### [Deployment Slot Cold Start](deployment-slots-cold-start/overview.md) — **Draft**

Post-swap cold-start latency when the warming phase fails or is incomplete. Investigates ARR affinity uneven warming across instances, Always On interaction with swap timing, and how `applicationInitialization` routes affect first-request latency.

!!! info "Status: Draft - Awaiting Execution"
    Designed to characterize the post-swap cold-start window that customers frequently report.

### [Environment Variable Limits](environment-variable-limits/overview.md) — **Draft**

App setting count and value size limits enforced by the ARM API. Tests Key Vault reference fallback behavior (literal reference string vs. empty value on resolution failure) and whether violations cause silent truncation or explicit errors.

!!! info "Status: Draft - Awaiting Execution"
    Important for diagnosing "setting change not reflected" cases and KV reference failures.

### [Connection Timeout Cascade](connection-timeout-cascade/overview.md) — **Draft**

Thread pool saturation pattern caused by slow or unavailable outbound dependencies. Characterizes the recovery lag after dependency recovery and the diagnostic signature (low CPU, high 5xx rate).

!!! info "Status: Draft - Awaiting Execution"
    Documents the most common cascading failure pattern in multi-tier App Service applications.

### [Log Stream Reliability](log-stream-reliability/overview.md) — **Draft**

Log Stream message drop behavior under high log volume. Compares Log Stream latency and completeness against Application Insights. Tests file log vs. stdout capture and disconnect behavior on instance restart.

!!! info "Status: Draft - Awaiting Execution"
    Clarifies the appropriate use of Log Stream vs. Application Insights during live incidents.

### [Container Registry Auth Expiry](container-registry-auth-expiry/overview.md) — **Draft**

Impact of container registry credential rotation on running App Service containers vs. containers that need to restart. Tests admin credentials, service principal secrets, and managed identity RBAC removal scenarios.

!!! info "Status: Draft - Awaiting Execution"
    Addresses a common support pattern: app works fine until a restart after credential rotation.

### [Windows vs Linux Behavioral Diff](windows-linux-behavioral-diff/overview.md) — **Draft**

Side-by-side behavioral differences between Windows and Linux hosting in App Service for the same application code. Tests path separator handling, environment variable casing, signal handling, and procfs availability differences.

!!! info "Status: Draft - Awaiting Execution"
    Documents behavioral gaps that surface when customers migrate workloads between OS tiers.

### [WebSocket Connection Limits](websocket-connection-limits/overview.md) — **Draft**

WebSocket connection limit behavior at the ARR (Application Request Routing) layer. Tests per-instance connection caps, idle timeout disconnection, ARR affinity interaction with WebSocket sessions, and instance count impact on total connection headroom.

!!! info "Status: Draft - Awaiting Execution"
    Addresses a common support pattern: WebSocket apps fail under scale without obvious CPU or memory pressure.

### [Managed Identity Scope Mismatch](managed-identity-scope-mismatch/overview.md) — **Draft**

Token acquisition failure when managed identity is used with incorrect resource scope or wrong identity type. Tests system-assigned vs user-assigned identity selection, wrong scope in token requests, and cross-tenant access failures.

!!! info "Status: Draft - Awaiting Execution"
    Documents the most common managed identity misconfiguration pattern in App Service deployments.

## Related Experiments in Other Services

- **Functions** — [Cold Start](../functions/cold-start/overview.md) explores startup phase breakdown, which shares diagnostic overlap with App Service container startup behavior.
- **Container Apps** — [OOM Visibility Gap](../container-apps/oom-visibility-gap/overview.md) investigates OOM kill observability, relevant when comparing App Service memory pressure signals.
- **Cross-cutting** — [MI RBAC Propagation](../cross-cutting/mi-rbac-propagation/overview.md) tests identity propagation delays that affect App Service managed identity usage.
