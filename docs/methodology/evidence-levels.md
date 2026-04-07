# Evidence Levels

A core differentiator of this repository is the explicit tagging of evidence levels. Every claim in an experiment is categorized by the strength of its supporting evidence.

## Tag definitions

| Tag | Definition | Usage |
|-----|-----------|-------|
| **Observed** | Directly seen in logs, metrics, or system behavior during the experiment | Facts that any observer would agree on |
| **Measured** | Quantitatively confirmed with specific numerical values | Precise data points with units and timestamps |
| **Correlated** | Two or more signals changed together, but a causal link is not established | Temporal or statistical association only |
| **Inferred** | A reasonable conclusion drawn from observations, using domain knowledge | Logical deduction, not direct observation |
| **Strongly Suggested** | Multiple evidence sources point to the same conclusion, but definitive proof is missing | High confidence, but alternative explanations exist |
| **Not Proven** | The hypothesis was tested but the evidence did not confirm it | Negative or inconclusive result |
| **Unknown** | The available data is insufficient to make any determination | Honest acknowledgment of a gap |

## Examples

**Observed:**
> "During the test window, the container restart count incremented from 0 to 3."

**Measured:**
> "p99 response time increased from 120 ms to 3,400 ms between 14:02 and 14:08 UTC."

**Correlated:**
> "The memory increase from 60% to 92% coincided with the response time degradation, but both could be caused by an independent third factor."

**Inferred:**
> "Given that the OOM killer log entry appeared 2 seconds before the container restart, the restart was most likely triggered by the OOM kill."

**Strongly Suggested:**
> "All observed indicators — swap usage increase, page fault rate spike, and CPU system time rise — are consistent with swap thrashing as the root cause. However, we did not directly measure disk I/O to the swap device."

**Not Proven:**
> "We hypothesized that the timeout was platform-side, but the experiment showed the worker was still processing the request at the time of the 504 response."

**Unknown:**
> "The root cause of the intermittent 10-second delay between request receipt and handler invocation could not be determined from the available telemetry."

## Why this matters

In support scenarios, the distinction between what is observed and what is inferred has direct consequences:

- **Over-claiming** erodes trust. Telling a customer "the platform caused this" when the evidence only suggests correlation can damage credibility and lead to incorrect remediation.
- **Under-claiming** wastes time. Refusing to draw any conclusion when the evidence strongly suggests a cause forces unnecessary data collection cycles.
- **Calibrated confidence** builds trust. Stating "the data is consistent with X, and we recommend investigating Y to confirm" gives customers a clear next step without overcommitting.

## Usage in experiments

In the **Interpretation** section of each experiment, tag significant claims:

```markdown
The response time increase [Measured] coincided with the memory pressure event [Correlated].
Based on the OOM kill log entry and subsequent restart timing, the restart was most likely
triggered by memory exhaustion [Inferred].
```

In the **What this proves** / **What this does NOT prove** sections, evidence tags help enforce discipline:

- "What this proves" should contain only **Observed**, **Measured**, or **Strongly Suggested** claims
- "What this does NOT prove" should reference **Correlated**, **Not Proven**, or **Unknown** items
