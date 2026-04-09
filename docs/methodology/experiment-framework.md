---
hide:
  - toc
---

# Experiment Framework

Every experiment in this repository follows a standardized structure. This consistency ensures that results are comparable, limits are stated, and readers can quickly locate the information they need.

## Template structure

### 1. Question

The specific question the experiment aims to answer. This should be narrow enough to test in a single experiment.

_Example: "Does plan-level memory pressure on a shared App Service plan cause measurable CPU increase due to kernel page reclaim?"_

### 2. Why this matters

The real-world support relevance. Why would a support engineer encounter this scenario, and what decision does the answer inform?

### 3. Customer symptom

What a customer would describe in a support ticket. This anchors the experiment in practical reality.

_Example: "My app is slow but CPU usage looks normal."_

### 4. Hypothesis

A testable prediction stated before the experiment runs. The results will either support or contradict this prediction.

_Example: "Under memory pressure, the kernel will reclaim pages, causing CPU usage to increase even if the application itself is idle."_

### 5. Environment

The specific configuration used for the experiment:

| Parameter | Value |
|-----------|-------|
| Service | App Service / Functions / Container Apps |
| SKU / Plan | e.g., B1, P1v3, Consumption, Flex Consumption |
| Region | e.g., East US 2 |
| Runtime | e.g., Node.js 20, Python 3.11, .NET 8 |
| OS | Linux / Windows |
| Date tested | YYYY-MM-DD |

### 6. Variables

**Controlled** — what is deliberately set or fixed (e.g., load pattern, memory allocation size).

**Observed** — what is measured (e.g., response time, CPU percentage, memory committed).

!!! info "Performance experiments — additional fields"
    For experiments classified as **Performance** (see [Statistical Methods](statistical-methods.md)), this section must also declare:

    - **Experiment type**: Config or Performance
    - **Independent run definition**: what constitutes a single independent run
    - **Planned runs per configuration**: target count (default: 5)
    - **Warm-up exclusion rule**: predeclared before execution
    - **Primary metric and meaningful-effect threshold**: e.g., "p95 latency, 20% relative change"
    - **Comparison method**: bootstrap CI, Mann-Whitney U, or directional only

    Many probes in one run do not replace repeated independent runs.
### 7. Instrumentation

Tools and data sources used: Azure Monitor metrics, Application Insights traces, KQL queries, procfs readings, cgroup stats, custom application logging, load testing tools.

### 8. Procedure

Step-by-step instructions for reproducing the experiment. Detailed enough that another engineer can follow without guessing.

### 9. Expected signal

What the hypothesis predicts will appear in the instrumentation. Written before results are collected.

!!! info "Performance experiments"
    For performance experiments, state the expected direction and approximate magnitude. Example: "Config B is expected to show ≥20% lower p95 latency than Config A."

### 10. Results

Raw observations: data, logs, metrics, screenshots. Presented without interpretation.

!!! info "Performance experiments — required reporting"
    Performance experiments must replace single-value summaries with a repeated-run summary block. See [Statistical Methods — Reporting Template](statistical-methods.md#reporting-template-for-performance-experiments) for the full format. Required fields:

    - Run count (planned, completed, valid)
    - Per-run summary table with median, p95, p99, IQR, failure rate
    - Excluded runs with documented reasons
    - Raw data link to `data/{service}/{experiment}/`
    - At minimum: box plot comparison + time series chart + summary statistics table

    Statements such as "avg latency 934ms" are prohibited unless paired with run count and spread metrics.

### 11. Interpretation

Analysis of the results using [evidence level tags](evidence-levels.md). This section explicitly separates what was observed from what is inferred.

!!! info "Performance experiments — required subsections"
    Performance experiments must include:

    **Comparison and Effect Size**: State the delta, direction consistency, confidence interval, and verdict (directional / supported / strong). Example: "Config B reduced p95 latency by 38%; direction was consistent in 5/5 runs; 95% CI [−45%, −28%]; verdict: Supported."

    **Confidence Statement**: State the evidence level achieved based on run count and consistency. See [Statistical Methods — Evidence Level Mapping](statistical-methods.md#evidence-level-mapping).

    **Limitations**: Disclose PT1M metric limitations, telemetry gaps, invalid runs, region/plan/runtime specificity, and whether outliers were kept or excluded.

    A single-run performance experiment cannot receive **Measured** or **Strongly Suggested** evidence levels.

### 12. What this proves

Evidence-based conclusions only. Each statement should be supportable by the data in section 10.

### 13. What this does NOT prove

Explicit limits. What cannot be concluded from this experiment, even if it might be tempting to generalize.

### 14. Support takeaway

Actionable guidance for a support engineer handling a similar case. What to check, what to ask the customer, and what to escalate.

### 15. Reproduction notes

Practical tips for repeating the experiment: timing sensitivity, region-specific behavior, SKU requirements, known environment variations.

### 16. Related guide / official docs

Links to relevant Microsoft Learn pages, practical guide sections, or other experiments in this repository.

## Usage

!!! note
    Not every experiment will fill every section. Some experiments may have minimal "Variables" or no "Reproduction notes." The framework is a guide for thoroughness, not a rigid checklist.

The canonical template file is available at [`experiments/templates/experiment-template.md`](https://github.com/yeongseon/azure-paas-troubleshooting-labs/blob/main/experiments/templates/experiment-template.md).

## Performance experiment requirements

Experiments are classified as either **Config** (deterministic) or **Performance** (variable outcomes). The classification determines the required reporting structure.

- **Config experiments**: Single valid run is acceptable when the outcome is deterministic (e.g., DNS resolves or it doesn't, RBAC grants access or it doesn't).
- **Performance experiments**: Multiple independent runs required. Default target is 5 runs per configuration. See [Statistical Methods](statistical-methods.md) for the complete methodology.

!!! warning "Evidence ceiling for performance experiments"
    A performance experiment with fewer than 3 independent runs caps at **Correlated** evidence level regardless of how clear the signal appears. Single-run performance data is **Observed** only.
