# Interpretation Guidelines

How to read experiment results, communicate findings, and avoid common reasoning errors.

## Separating observation from interpretation

Every experiment produces raw data (metrics, logs, traces) and an interpretation of what that data means. These must be kept separate.

**Observation** — what happened, in factual terms:

> "CPU percentage increased from 12% to 87% between 14:02 and 14:05 UTC."

**Interpretation** — what we believe it means:

> "The CPU increase was most likely caused by garbage collection pressure following the memory allocation spike."

Mixing the two leads to overconfident conclusions and untestable claims. When writing experiment results, present observations first (section 10), then interpretation (section 11).

## Confidence calibration

Use [evidence level tags](evidence-levels.md) to mark the confidence of each claim. Ask:

- Can another engineer verify this from the same data? → **Observed** or **Measured**
- Does this depend on domain knowledge or inference? → **Inferred**
- Are there plausible alternative explanations? → **Correlated** or **Strongly Suggested**
- Did the data fail to support the hypothesis? → **Not Proven**

## Common interpretation pitfalls

### Confirmation bias

Seeing what you expect to see. If the hypothesis predicts a CPU spike and you see a CPU spike, verify that the spike is actually related to the test condition and not a coincidental platform event.

**Mitigation:** Check for the same signal in a control period (no test load). Check for alternative causes in the platform event timeline.

### Single-run conclusions

One experiment run is not proof. A single observation could be an outlier, a timing artifact, or influenced by an uncontrolled variable.

**Mitigation:** Run experiments multiple times. Note whether results are consistent. State the number of runs in the results section.

### Metric misattribution

Blaming the wrong layer for an observed metric. Plan-level metrics aggregated across apps can suggest pressure that affects only one app. Instance-level metrics can hide problems that appear only on specific instances.

**Mitigation:** Always verify metric scope. Check per-instance and per-app views. Cross-reference with procfs/cgroup where available.

### Temporal coincidence vs. causation

Two events happening at the same time does not mean one caused the other. A deployment and a latency spike occurring together does not prove the deployment caused the latency spike.

**Mitigation:** Look for the mechanism. Can you explain how A would cause B? Test by reproducing A without B, or B without A.

## Writing for support context

When interpreting results for support scenarios, consider:

### What can you tell a customer?

Only conclusions supported by **Observed**, **Measured**, or **Strongly Suggested** evidence. State the evidence explicitly.

### What additional data would help?

If the conclusion is **Correlated** or **Inferred**, identify what additional data would strengthen it. This gives the customer a concrete next step.

### What should NOT be stated as fact?

**Not Proven** and **Unknown** items should never be presented as conclusions. They are open questions that require further investigation.

## Template phrases

For calibrated communication in support contexts:

| Confidence | Template |
|-----------|----------|
| High | "Based on the observed metrics, [X] is the most likely explanation." |
| Medium | "The data is consistent with [X], but we cannot rule out [Y]." |
| Low | "To confirm this, we would need [additional data source]." |
| Scoped | "This experiment demonstrates [X] under [conditions]. Behavior may differ under [other conditions]." |
| Negative | "The experiment did not confirm [hypothesis]. The observed behavior suggests [alternative]." |

## Environment-specific factors

Always note factors that may limit the generalizability of results:

- **SKU and plan tier** — behavior on B1 may differ from P1v3
- **Region** — infrastructure variations across regions
- **Runtime version** — framework or runtime updates can change behavior
- **Time of day** — shared infrastructure load varies
- **Recent platform changes** — Azure platform updates can alter behavior between experiment runs

These factors do not invalidate results, but they must be stated so readers can assess applicability to their own scenarios.
