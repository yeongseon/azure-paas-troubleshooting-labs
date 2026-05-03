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

# Revision Label Collision: Traffic Not Routing to Expected Revision

!!! info "Status: Planned"

## 1. Question

Container Apps allows assigning labels to specific revisions for direct access via `https://<label>--<app>.<env>.azurecontainerapps.io`. When a label is reassigned to a new revision, what happens to the old revision (does it become unlabeled or does the assignment silently fail), and are there scenarios where the label points to an unexpected revision?

## 2. Why this matters

Revision labels are used for stable test endpoints, A/B testing, and canary deployments. Teams that use labels like `stable` or `canary` and expect them to point to a specific revision may be surprised when deploying a new revision with the same label: the label may move to the new revision (expected) or the new revision may be created without the label (unexpected, if the label assignment fails or is not specified). Understanding the exact label lifecycle prevents routing bugs in staging environments.

## 3. Customer symptom

"The `stable` endpoint is still routing to the old version even after we deployed and labeled the new revision" or "Our test endpoint started serving unexpected traffic after a deployment" or "Label assignment seems to silently fail — the new revision has no label."

## 4. Hypothesis

- H1: When a new revision is deployed with the same label as an existing revision, the label is moved to the new revision and removed from the old revision. The old revision continues to exist but becomes unlabeled.
- H2: When a revision is deployed without specifying a label, existing labels on other revisions are not affected. A label previously assigned to revision A remains on revision A even if a newer revision B is the active one.
- H3: Label names are unique within a container app. Attempting to assign the same label to two revisions simultaneously fails; one assignment must be removed first.
- H4: The revision label URL (`https://<label>--<app>.<env>.azurecontainerapps.io`) is available immediately after label assignment and routes exclusively to the labeled revision, regardless of traffic split configuration.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Deployment / Routing

**Controlled:**

- Container app with multiple-revision mode enabled
- Two revisions: rev-a (labeled `stable`) and rev-b (new deployment)
- Label assignment scenarios

**Observed:**

- Which revision the `stable` label URL routes to
- Old revision label status after label reassignment

**Scenarios:**

- S1: Deploy rev-b with label `stable` → verify label moves from rev-a to rev-b
- S2: Deploy rev-c without label → verify `stable` label stays on rev-b
- S3: Assign `stable` label to rev-a (while rev-b has it) → verify label moves back

## 7. Instrumentation

- `az containerapp revision list` to observe label assignments per revision
- HTTP request to `https://stable--<app>.<env>.azurecontainerapps.io` and check response version
- Azure Container Apps portal **Revision management** blade

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy rev-a (returns "version: A"); assign label `stable`; verify `https://stable--...` returns "version: A".
2. S1: Deploy rev-b (returns "version: B") with `--revision-suffix rev-b --label stable`; verify label URL returns "version: B"; verify rev-a has no label.
3. S2: Deploy rev-c without specifying label; verify `stable` label URL still returns "version: B" (rev-c has no label).
4. S3: `az containerapp revision label add --label stable --revision rev-a`; verify label URL returns "version: A"; verify rev-b has no label.

## 9. Expected signal

- S1: Label URL returns "version: B" after new labeled deployment; `az containerapp revision list` shows rev-a has no label.
- S2: Rev-c exists without label; label URL still returns "version: B".
- S3: Label reassigned to rev-a; label URL returns "version: A"; rev-b unlabeled.

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

- Labels require `--revision-mode multiple` on the container app.
- Label URLs use the format `https://<label>--<app-name>.<env-default-domain>`.
- Label assignment command: `az containerapp revision label add --name <app> --resource-group <rg> --label <label-name> --revision <revision-name>`.

## 16. Related guide / official docs

- [Container Apps revision management](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
- [Traffic splitting in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/traffic-splitting)
