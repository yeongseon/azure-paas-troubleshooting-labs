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

# Environment Variable Injection Order

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

In Container Apps, when the same environment variable name is defined in multiple sources (container definition, secrets, Dapr component, and system-injected variables), which value wins? Is there a documented precedence order, and does it match observed behavior?

## 2. Why this matters

Container Apps injects environment variables from multiple sources: user-defined env vars in the container spec, secret references (`secretRef`), Dapr-injected variables, and platform-injected system variables. When a variable name collision occurs — either intentionally (override) or accidentally (shadowing a system variable) — the outcome is not always predictable. Support cases arise when:
- A customer defines an env var that shadows a system-injected variable, causing unexpected behavior
- A secret reference and a plain env var share the same name — which takes precedence?
- Dapr-injected variables (like `APP_PORT`) conflict with customer-defined variables

## 3. Customer symptom

- "I set `PORT=8080` but the app is still trying to listen on port 3000."
- "Our secret reference and the env var have the same name — which one does the app see?"
- "After enabling Dapr, some of our existing env vars stopped working."
- "We defined `DAPR_HTTP_PORT` ourselves but it's being overwritten."

## 4. Hypothesis

**H1 — Secret references override plain env vars**: When the same variable name is defined as both a plain value and a secret reference, the secret reference takes precedence (defined later in the container spec).

**H2 — System-injected variables have highest precedence**: Container Apps-injected system variables (`CONTAINER_APP_NAME`, `CONTAINER_APP_REVISION`, etc.) cannot be overridden by user-defined env vars.

**H3 — Dapr-injected variables are injected at sidecar level**: Dapr variables (`DAPR_HTTP_PORT`, `DAPR_GRPC_PORT`) are injected by the Dapr sidecar into the container's environment. They take precedence over user-defined values with the same name.

**H4 — Plain env var order matters**: If two plain env vars with the same name are defined in the container spec, the last one wins (standard POSIX env var behavior).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Container Apps |
| Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| Dapr | Enabled (for H3) |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Config + Precedence

**Controlled:**

- Variable name collision sources: plain env var vs. secret ref, plain vs. system-injected, plain vs. Dapr-injected
- Order of definition in container spec

**Observed:**

- Value seen by application at runtime (`os.environ.get(key)`)
- Platform documentation claims vs. observed behavior

## 7. Instrumentation

- Application endpoint: `GET /env/{key}` returning current value
- `/env/all` endpoint: dumps all environment variables sorted alphabetically
- Dapr-enabled deployment for H3

## 8. Procedure

### 8.1 Scenarios

**S1 — Plain value vs. secret reference (same name)**: Define `MY_VAR=plain` in env vars AND `MY_VAR` as a secret reference pointing to `secret-value`. Observe which value the app sees.

**S2 — Override system-injected variable**: Attempt to set `CONTAINER_APP_NAME=myname` as a plain env var. Observe whether the app sees the user value or the platform-injected value.

**S3 — Duplicate plain env vars**: Define `MY_VAR=first` and `MY_VAR=second` in the same container spec. Observe which value wins.

**S4 — Dapr port variable override**: Enable Dapr. Define `DAPR_HTTP_PORT=9999` in container spec. Dapr injects `DAPR_HTTP_PORT=3500`. Observe which value the app sees.

**S5 — Cross-container env var sharing**: Verify whether env vars defined on the main container are visible to sidecar containers (and vice versa).

## 9. Expected signal

- **S1**: Secret reference wins (defined later in spec; or platform resolves secrets after plain vars).
- **S2**: System-injected variables override user-defined values (platform injects after user definition).
- **S3**: Last-defined value wins (POSIX convention).
- **S4**: Dapr-injected value wins — `DAPR_HTTP_PORT=3500` regardless of user definition.
- **S5**: Env vars are per-container — not shared between main and sidecar containers.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Precedence behavior may be implementation-specific and subject to change across platform versions.
- The test uses Python `os.environ` — different runtimes may see env vars at different times (before vs. after Dapr sidecar init).

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| System-injected variables cannot be overridden | **Inferred** |
| Dapr injects variables that override user values | **Inferred** |
| Secret refs override plain vars with same name | **Unknown** |

## 14. Related experiments

- [App Setting Precedence (App Service)](../../app-service/zip-vs-container/overview.md) — similar precedence analysis for App Service
- [Dapr Component Scoping](../dapr-component-scoping/overview.md) — Dapr environment variable injection

## 15. References

- [Container Apps environment variables](https://learn.microsoft.com/en-us/azure/container-apps/containers#environment-variables)
- [Container Apps system environment variables](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables)

## 16. Support takeaway

For environment variable precedence issues in Container Apps:

1. System-injected variables (`CONTAINER_APP_NAME`, `CONTAINER_APP_REVISION`, `CONTAINER_APP_REPLICA_NAME`) cannot be overridden — they are injected by the platform after user-defined vars.
2. If a customer is defining `DAPR_HTTP_PORT` or `DAPR_GRPC_PORT` with Dapr enabled, those values will be overridden by the Dapr sidecar injection.
3. For debugging, use `az containerapp exec --command "env | sort"` to see all environment variables as seen by the running container.
4. Secret references (`secretRef`) and plain env vars with the same name — always check the container spec definition order and prefer explicit naming to avoid ambiguity.
