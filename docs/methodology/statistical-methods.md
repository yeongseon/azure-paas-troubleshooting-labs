---
hide:
  - toc
---

# Statistical Methods for Performance Experiments

This page defines the statistical methodology for experiments where outcomes vary across runs. It complements the [Experiment Framework](experiment-framework.md) and [Evidence Levels](evidence-levels.md).

## Experiment type classification

Every experiment must declare its type before execution begins.

| Type | Definition | Qualifying test | Repetition rule |
|------|-----------|----------------|-----------------|
| **Config** | Outcome is deterministic once preconditions are fixed | Given identical setup, the success/failure result is the same every time | Single run sufficient |
| **Performance** | Outcome varies across runs due to shared infrastructure, noisy neighbors, or timing | Same setup can produce different latency, throughput, or error rates across runs | Multiple independent runs required |
| **Hybrid** | Contains both deterministic and variable components | Config aspect determines if feature works; Performance aspect measures how well | Split: validate Config first (single run), then measure Performance (multiple runs) |

### Classification examples

| Experiment | Type | Reasoning |
|-----------|------|-----------|
| Custom DNS resolution drift | Config | DNS either resolves or it doesn't — deterministic |
| Target port auto-detection | Config | Port detection succeeds or fails based on configuration |
| SNAT exhaustion under load | Performance | Connection failure rate varies with platform load and timing |
| Cold start latency breakdown | Performance | Startup duration varies across invocations |
| Managed identity RBAC propagation | Hybrid | RBAC either works (Config), but propagation delay varies (Performance) |

## Run requirements

### Minimum independent runs

| Decision impact | Minimum runs | Recommended | Evidence level cap |
|----------------|-------------|-------------|-------------------|
| Informational (blog, knowledge base) | 3 | 5 | Directional at 3; Confirmed at 5+ |
| Operational (support playbook) | 5 | 7 | Confirmed at 5+ consistent |
| Critical (architecture decision) | 7 | 10+ | Confirmed at 7+ consistent |

!!! warning "Evidence ceiling"
    A performance experiment with fewer than 3 independent runs caps at **Correlated** evidence level regardless of how clear the signal appears. Single-run performance data is **Observed** only — never **Measured** or **Strongly Suggested**.

### What counts as an independent run

Each run must be independent in the statistical sense:

- **New deployment** or full container restart between runs (not just request replay)
- **Separated by at least 5 minutes** to avoid warm cache or connection pool carryover
- **Same stimulus profile**: identical request count, payload, concurrency, and duration
- **Logged independently**: each run produces its own raw data file

!!! note "Cold start experiments"
    For cold start measurements, each run must include a true cold event (scale from zero or fresh deployment). Warm follow-ups within the same run are part of that run's data, not separate runs.

## Metrics to report

### Primary metrics table

Every performance experiment must include this table in the Results section:

| Metric | Config A | Config B | Unit |
|--------|----------|----------|------|
| Runs (n) | | | count |
| Median (p50) | | | ms / % / count |
| p95 | | | ms / % / count |
| p99 | | | ms / % / count |
| IQR | | | ms / % / count |
| Min | | | ms / % / count |
| Max | | | ms / % / count |

### Why median over mean

Cloud workload latency distributions are typically right-skewed with heavy tails. The mean is distorted by outliers (a single 30-second timeout inflates the mean of 100 sub-second requests). The median is robust to these outliers and better represents "typical" behavior.

**Always report median as the primary central tendency.** Report mean only as a supplementary metric, with a note about skew if mean > 1.5× median.

### Per-run vs per-request metrics

| Granularity | Use when | Example |
|------------|----------|---------|
| **Per-run summary** | Comparing configurations | Median of each run's p95 latency |
| **Per-request detail** | Analyzing distributions | All individual request durations from a single run |

When comparing configurations, compute per-run summaries first (e.g., each run's median latency), then compare those summaries across runs. This avoids pseudo-replication (treating 1000 requests from one run as 1000 independent observations).

## Warm-up exclusion

### Protocol

| Experiment type | Warm-up rule | Rationale |
|----------------|-------------|-----------|
| Steady-state latency | Exclude the **longer** of: first 2 minutes or first 100 successful requests | JIT compilation, connection pool warm-up, DNS cache population |
| Cold start / scale-to-zero | **No exclusion** — cold period IS the measurement | The cold event is the subject under study |
| Throughput / load test | Exclude ramp-up phase until target concurrency is reached | Load generator stabilization |

### Recording warm-up data

!!! important "Preserve, don't discard"
    Warm-up data must be **recorded and preserved** in raw data files. Exclusion happens at analysis time, not collection time. The raw data directory must contain the complete dataset. Mark the warm-up boundary in the analysis output:

    ```
    warm_up_boundary:
      method: "first 2 minutes"
      excluded_requests: 87
      excluded_until: "2026-04-10T14:02:00Z"
    ```

## Outlier policy

### Decision tree

```
Is the outlier consistent across multiple runs?
├── YES → It is a real tail behavior, not an outlier. INCLUDE it.
│         Report it in p99 and note its frequency.
└── NO  → Present in only 1 of N runs?
    ├── Identifiable external cause? (platform event, deployment, unrelated alert)
    │   └── YES → EXCLUDE the affected run. Note the exclusion reason.
    │             Replace with an additional run if below minimum run count.
    └── No identifiable cause?
        └── INCLUDE it. Outliers without explanation may be the finding.
            Report with and without the outlier for transparency.
```

### Documenting exclusions

Every excluded data point or run must be documented:

```markdown
### Excluded runs

| Run | Reason | Evidence |
|-----|--------|----------|
| Run 3 | Platform deployment event during measurement window | Activity log entry at 14:05 UTC |
```

## Comparison methodology

### When comparing two configurations (A vs B)

**Step 1: Visual comparison**

Create a box plot of per-run summaries (median or p95) for each configuration. If the boxes do not overlap, the difference is likely meaningful.

**Step 2: Effect size**

Calculate the difference in medians between configurations, expressed as a percentage:

```
Effect size = (Median_B - Median_A) / Median_A × 100%
```

| Effect size | Category | Interpretation |
|------------|----------|----------------|
| < 10% | Negligible | Within normal cloud variance |
| 10–25% | Small | Noticeable but may not warrant action |
| 25–50% | Medium | Likely operationally significant |
| > 50% | Large | Strong signal, high confidence in real difference |

!!! note "Tail-sensitive metrics"
    For SLO-relevant metrics (p95, p99), use a lower threshold: >10% difference in p95 is operationally significant even if medians differ by less.

**Step 3: Statistical test (when n ≥ 5 per group)**

Use the **Mann-Whitney U test** on per-run medians:

- Non-parametric — no assumption about distribution shape
- Appropriate for small sample sizes (5–10 runs per group)
- Report U statistic and p-value
- Significance threshold: p < 0.05

```python
from scipy.stats import mannwhitneyu

# per_run_medians_A = [median_latency for each run of config A]
# per_run_medians_B = [median_latency for each run of config B]

stat, p_value = mannwhitneyu(
    per_run_medians_A,
    per_run_medians_B,
    alternative='two-sided'
)
```

**Step 4: Confidence interval (bootstrap)**

When formal tests are not applicable (n < 5), compute a bootstrap 95% confidence interval on the difference in medians:

```python
import numpy as np

def bootstrap_ci(a, b, n_bootstrap=10000, ci=0.95):
    diffs = []
    for _ in range(n_bootstrap):
        sample_a = np.random.choice(a, size=len(a), replace=True)
        sample_b = np.random.choice(b, size=len(b), replace=True)
        diffs.append(np.median(sample_b) - np.median(sample_a))
    lower = np.percentile(diffs, (1 - ci) / 2 * 100)
    upper = np.percentile(diffs, (1 + ci) / 2 * 100)
    return lower, upper
```

If the 95% CI excludes zero, the difference is statistically meaningful.

### Reporting comparison results

Use this template in the Interpretation section:

```markdown
**Comparison: Config A vs Config B**

- Effect size: +42% increase in p50 latency (Medium)
- Mann-Whitney U: U=2.0, p=0.016 (n_A=5, n_B=5)
- Bootstrap 95% CI for difference in medians: [+85ms, +210ms]
- Conclusion: Config B shows statistically significant higher latency [Measured]
```

## Visualization standards

All charts use Vega-Lite. The following chart types are required for performance experiments:

### 1. Box plot — run-level comparison

Shows distribution of per-run summaries across configurations.

```vegalite
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "description": "Template: per-run metric comparison",
  "data": {"values": []},
  "mark": "boxplot",
  "encoding": {
    "x": {"field": "configuration", "type": "nominal", "title": "Configuration"},
    "y": {"field": "value", "type": "quantitative", "title": "Metric (unit)"},
    "color": {"field": "configuration", "type": "nominal"}
  }
}
```

### 2. Time series with percentile bands

Shows metric behavior over time with p50 line and p5–p95 shaded band.

```vegalite
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "description": "Template: time series with percentile bands",
  "layer": [
    {
      "mark": "area",
      "encoding": {
        "x": {"field": "timestamp", "type": "temporal"},
        "y": {"field": "p5", "type": "quantitative"},
        "y2": {"field": "p95"},
        "opacity": {"value": 0.2}
      }
    },
    {
      "mark": "line",
      "encoding": {
        "x": {"field": "timestamp", "type": "temporal"},
        "y": {"field": "p50", "type": "quantitative", "title": "Metric (unit)"}
      }
    }
  ],
  "data": {"values": []}
}
```

### 3. Scatter plot — individual runs

Shows each run as a point, useful for detecting clusters or outliers.

Use for: run-to-run variability, identifying if one run is clearly anomalous.

## Raw data preservation

### Directory structure

All raw data is stored in the repository under `data/`:

```text
data/
├── app-service/
│   └── {experiment-slug}/
│       ├── run-001/
│       │   ├── requests.csv          # Per-request data
│       │   ├── metrics.json          # Azure Monitor metrics export
│       │   ├── traces.json           # Application Insights traces
│       │   └── metadata.yaml         # Run metadata
│       ├── run-002/
│       └── analysis/
│           ├── summary.csv           # Aggregated per-run summaries
│           └── comparison.json       # Statistical test results
├── functions/
│   └── {experiment-slug}/
│       └── ...
├── container-apps/
│   └── {experiment-slug}/
│       └── ...
└── cross-cutting/
    └── {experiment-slug}/
        └── ...
```

### Run metadata schema

Each run directory must contain a `metadata.yaml` file:

```yaml
experiment: snat-exhaustion
service: app-service
run_number: 1
date: 2026-04-10
start_time: "14:00:00Z"
end_time: "14:45:00Z"
configuration:
  sku: P1v3
  region: koreacentral
  runtime: python-3.11
  custom: {}                  # experiment-specific settings
warm_up:
  method: "first 2 minutes"
  excluded_until: "14:02:00Z"
  excluded_requests: 87
environment:
  az_cli_version: "2.83.0"
  core_tools_version: "4.8.0"
  os: linux
notes: ""
```

### File format conventions

| Data type | Format | Reason |
|-----------|--------|--------|
| Per-request timings | CSV | Easy to load in pandas, Excel, R |
| Azure Monitor metrics | JSON | Native export format |
| Application Insights traces | JSON | Native KQL export format |
| Run metadata | YAML | Human-readable, git-friendly |
| Analysis summaries | CSV | Tabular, easy to aggregate |
| Statistical test results | JSON | Structured, machine-readable |

## Evidence level mapping

Performance experiment evidence levels depend on run count and consistency:

| Runs | Result consistency | Maximum evidence level |
|------|-------------------|----------------------|
| 1 | N/A | **Observed** — single data point, no statistical power |
| 2 | Both agree | **Correlated** — suggestive but insufficient |
| 3 | All agree | **Inferred** — directional evidence |
| 3 | 2 of 3 agree | **Correlated** — inconsistent signal |
| 5+ | All agree, effect size ≥ Medium | **Measured** — quantitatively confirmed |
| 5+ | Statistical test p < 0.05 | **Strongly Suggested** — strong evidence |
| 5+ | Inconsistent or small effect | **Correlated** — signal exists but weak |

!!! tip "Practical implication"
    Most experiments in this repository target 5 independent runs per configuration. This is the minimum threshold for using formal statistical tests and achieving **Measured** or **Strongly Suggested** evidence levels.

## Reporting template for performance experiments

The Results (section 10) and Interpretation (section 11) of performance experiments must include the following structure:

### Section 10: Results — performance experiment additions

```markdown
### Experiment type

**Performance** — results vary across runs due to [specific variance source].

### Run summary

| Run | Date | Duration | Requests (total) | Requests (after warm-up) | Notes |
|-----|------|----------|-------------------|--------------------------|-------|
| 1   | 2026-04-10 | 30 min | 1200 | 1113 | — |
| 2   | 2026-04-10 | 30 min | 1200 | 1108 | — |
| ...   | | | | | |

### Primary metrics

| Metric | Config A | Config B | Unit |
|--------|----------|----------|------|
| Runs (n) | 5 | 5 | count |
| Median (p50) | 142 | 203 | ms |
| p95 | 310 | 890 | ms |
| p99 | 580 | 2100 | ms |
| IQR | 85 | 340 | ms |

### Raw data

Raw data for all runs is available in [`data/{service}/{experiment}/`](link).
```

### Section 11: Interpretation — performance experiment additions

```markdown
### Statistical analysis

- **Effect size**: +43% increase in median latency (Medium)
- **Mann-Whitney U test**: U=2.0, p=0.016 (n_A=5, n_B=5)
- **Bootstrap 95% CI**: [+45ms, +78ms] for difference in medians
- **Conclusion**: The difference is statistically significant and operationally meaningful.

### Confidence statement

This finding is based on N=5 independent runs per configuration with consistent
results across all runs. Evidence level: [Measured].
```

## Retrofitting existing experiments

Published experiments that report single-run performance data should be annotated:

```markdown
!!! warning "Statistical limitation"
    This experiment reports results from a single execution run. Performance
    metrics are **Observed** (not **Measured**) and should be treated as
    directional only. Re-execution with multiple independent runs is planned
    to achieve statistical confidence.
```

This annotation does not invalidate existing results — it calibrates reader expectations.

## See Also

- [Experiment Framework](experiment-framework.md) — 16-section template
- [Evidence Levels](evidence-levels.md) — tag definitions
- [Interpretation Guidelines](interpretation-guidelines.md) — reasoning discipline
