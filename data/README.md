# Raw Experiment Data

This directory stores raw data from experiment runs for future visualization and statistical analysis.

## Directory Structure

```text
data/
├── app-service/
│   └── {experiment-slug}/
│       ├── run-001/
│       │   ├── requests.csv          # Per-request timing data
│       │   ├── metrics.json          # Azure Monitor metrics export
│       │   ├── traces.json           # Application Insights traces
│       │   └── metadata.yaml         # Run metadata (date, config, warm-up)
│       ├── run-002/
│       └── analysis/
│           ├── summary.csv           # Aggregated per-run summaries
│           └── comparison.json       # Statistical test results
├── functions/
│   └── {experiment-slug}/...
├── container-apps/
│   └── {experiment-slug}/...
└── cross-cutting/
    └── {experiment-slug}/...
```

## File Formats

| Data type | Format | Reason |
|-----------|--------|--------|
| Per-request timings | CSV | Easy to load in pandas, Excel, R |
| Azure Monitor metrics | JSON | Native export format |
| Application Insights traces | JSON | Native KQL export format |
| Run metadata | YAML | Human-readable, git-friendly |
| Analysis summaries | CSV | Tabular, easy to aggregate |
| Statistical test results | JSON | Structured, machine-readable |

## Usage

See [Statistical Methods](../docs/methodology/statistical-methods.md) for the full methodology on data collection, warm-up exclusion, and analysis requirements.

Raw data is preserved for:
- Reproducibility of statistical analysis
- Future visualization and reporting
- Cross-experiment comparison
- Re-analysis with improved methods
