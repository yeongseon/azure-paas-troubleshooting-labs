---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-03"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Revision Label Collision: Traffic Not Routing to Expected Revision

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-03.

## 1. Question

Container Apps allows assigning labels to specific revisions for direct access via `https://<label>--<app>.<env>.azurecontainerapps.io`. When a label is reassigned to a new revision, what happens to the old revision (does it become unlabeled or does the assignment silently fail), and are there scenarios where the label points to an unexpected revision?

## 2. Why this matters

Revision labels are used for stable test endpoints, A/B testing, and canary deployments. Teams that use labels like `stable` or `canary` and expect them to point to a specific revision may be surprised when:

1. A new revision is created **without specifying a label** — the existing label stays on the old revision (expected, but often not understood).
2. A label is reassigned to a new revision via `az containerapp revision label add` — the CLI requires an **interactive confirmation prompt** in non-TTY environments, causing silent failure in CI/CD pipelines.
3. The `--yes` flag is required to bypass the prompt in automated scripts.

## 3. Customer symptom

"The `stable` endpoint is still routing to the old version even after we deployed a new revision" or "Label assignment fails in our pipeline with no error message" or "We deployed a new revision but the label URL still shows the old version."

## 4. Hypothesis

- H1: When a new revision is deployed without specifying a label, existing labels on other revisions are not affected — the label stays on the old revision. ✅ **Confirmed**
- H2: When `az containerapp revision label add` is run against a label already assigned to another revision, the CLI prompts for confirmation interactively. In a non-TTY environment (CI/CD), this raises `NoTTYException` and the command fails silently (exit code != 0). ✅ **Confirmed**
- H3: With `--yes`, the label is atomically moved to the new revision; the old revision becomes unlabeled. ✅ **Confirmed**
- H4: Label names are unique within a container app — the same label cannot point to two revisions simultaneously. ✅ **Confirmed** (the previous label is automatically removed from the old revision)

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Azure Container Apps Hello World image |
| OS | Linux |
| Date tested | 2026-05-03 |

## 6. Variables

**Experiment type**: Deployment / Routing

**Controlled:**

- Container app in multiple-revision mode
- Two revisions: `rev-a` (initially labeled `stable`) and `rev-b` (new deployment)
- Label assignment via `az containerapp revision label add`

**Observed:**

- Traffic configuration (`properties.configuration.ingress.traffic`) after each operation
- CLI error behavior in non-TTY environment (without `--yes`)
- Label assignment state after reassignment

**Scenarios:**

| Scenario | Action | Expected | Observed |
|----------|--------|----------|----------|
| S1 | Deploy `rev-b` without label | `stable` stays on `rev-a` | ✅ `stable` → `rev-a` unchanged |
| S2 (attempted) | `label add` without `--yes` in non-TTY | Label moved | ❌ `NoTTYException` — command fails |
| S3 | `label add --yes` to move `stable` → `rev-b` | Label moved atomically | ✅ `stable` → `rev-b`, `rev-a` unlabeled |
| S4 | `label add --yes` to move `stable` back → `rev-a` | Label moved back | ✅ `stable` → `rev-a`, `rev-b` unlabeled |

## 7. Instrumentation

- `az containerapp revision list` to observe revision existence and activity
- `az containerapp show --query "properties.configuration.ingress.traffic"` to observe label assignments
- `curl` to the label URL to test routing (HTTP status code)
- CLI stderr to capture `NoTTYException`

## 8. Procedure

1. Created Container App in multiple-revision mode with `rev-a`; assigned label `stable` to `rev-a`.
2. **S1**: Created `rev-b` (no label) → checked traffic config → `stable` still points to `rev-a`.
3. **S2 (attempted)**: Ran `az containerapp revision label add` without `--yes` in non-TTY → captured `NoTTYException`.
4. **S3**: Ran `az containerapp revision label add --yes` to move `stable` → `rev-b` → verified label moved.
5. **S4**: Moved `stable` back to `rev-a` with `--yes` → confirmed label is atomic (only one revision holds the label).

## 9. Expected signal

- S1: `stable` label remains on `rev-a` after creating `rev-b`.
- S2: CLI error due to missing TTY; label not moved.
- S3: Traffic config shows `stable` pointing to `rev-b`; `rev-a` has no label entry.
- S4: Traffic config shows `stable` pointing to `rev-a`; `rev-b` has no label entry.

## 10. Results

**Before S1 — initial state (`stable` → `rev-a`):**
```json
[
  {"latestRevision": true, "weight": 100},
  {"label": "stable", "revisionName": "app-label-lab--rev-a", "weight": 0}
]
```

**After S1 — `rev-b` created without label (no change):**
```json
[
  {"latestRevision": true, "weight": 100},
  {"label": "stable", "revisionName": "app-label-lab--rev-a", "weight": 0}
]
```

**S2 — `label add` without `--yes` in non-TTY:**
```
ERROR: knack.prompting.NoTTYException
```
Command fails; label not moved.

**After S3 — `label add --yes` moving `stable` → `rev-b`:**
```json
[
  {"latestRevision": true, "weight": 100},
  {"label": "stable", "revisionName": "app-label-lab--rev-b", "weight": 0}
]
```
`rev-a` no longer appears in the traffic label list — it is unlabeled.

**After S4 — `label add --yes` moving `stable` back → `rev-a`:**
```json
[
  {"latestRevision": true, "weight": 100},
  {"label": "stable", "revisionName": "app-label-lab--rev-a", "weight": 0}
]
```

## 11. Interpretation

**Observed**: Creating a new revision without specifying a label does not affect existing label assignments. The `stable` label remained on `rev-a` throughout `rev-b` creation. Labels are explicitly managed — they do not automatically follow the latest revision.

**Observed**: `az containerapp revision label add` prompts for confirmation when the label is already assigned to a different revision (`"Do you want to move the label from revision X to Y?"`). In non-TTY environments (CI/CD pipelines, scripts run without terminal), this prompt raises `knack.prompting.NoTTYException` and exits with a non-zero code, leaving the label unchanged. This is a common failure mode in automated deployments.

**Observed**: With `--yes`, the label reassignment is atomic — the label is removed from the previous revision and assigned to the new revision in a single API call. There is no window where both revisions hold the same label.

**Inferred**: Teams that manage labels in CI/CD pipelines without `--yes` will silently leave labels pointing to old revisions after deployments. The pipeline may exit with exit code 0 (if not checking the CLI return code properly) or non-zero — either way, the label URL keeps routing to the old revision.

## 12. What this proves

- **Proven**: Labels are NOT automatically moved to new revisions — they persist on the assigned revision until explicitly changed.
- **Proven**: `az containerapp revision label add` without `--yes` fails in non-TTY environments with `NoTTYException`.
- **Proven**: `--yes` enables non-interactive label reassignment and atomically moves the label.
- **Proven**: Label assignment is exclusive — one label maps to exactly one revision at any time.

## 13. What this does NOT prove

- The exact behavior of label URL routing latency after reassignment (not tested end-to-end due to hello-world image 404 behavior on the label subdomain).
- Whether label URL `https://<label>--<app>.<env>` works for apps using custom domain or internal ingress.
- Behavior when a labeled revision is deactivated (whether the label URL returns 404 or 503).

## 14. Support takeaway

When a customer reports that a label URL is still routing to an old revision after deployment:

1. **Check label assignment**: `az containerapp show -n <app> -g <rg> --query "properties.configuration.ingress.traffic[?label!=null]"`
2. **Verify the deployment script uses `--yes`**: `az containerapp revision label add --label stable --revision <new-rev> --yes`
3. **Check CI/CD pipeline** for `NoTTYException` in logs — this indicates label reassignment was attempted without `--yes` and silently failed.
4. **Manually reassign** if needed: `az containerapp revision label add -n <app> -g <rg> --label stable --revision <new-rev> --yes`

## 15. Reproduction notes

```bash
# Create app in multiple-revision mode
az containerapp create -n myapp -g myrg \
  --environment myenv \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --ingress external --target-port 80 \
  --revision-suffix rev-a \
  --revisions-mode multiple

# Assign label
az containerapp revision label add -n myapp -g myrg --label stable --revision myapp--rev-a

# Create new revision (label stays on rev-a)
az containerapp update -n myapp -g myrg --revision-suffix rev-b --set-env-vars VERSION=B

# Move label to rev-b (MUST use --yes in CI/CD)
az containerapp revision label add -n myapp -g myrg \
  --label stable --revision myapp--rev-b --yes

# Verify
az containerapp show -n myapp -g myrg \
  --query "properties.configuration.ingress.traffic[?label!=null]"
```

## 16. Related guide / official docs

- [Container Apps revision management](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
- [Traffic splitting in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/traffic-splitting)
- [`az containerapp revision label` CLI reference](https://learn.microsoft.com/en-us/cli/azure/containerapp/revision/label)
