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

### 7. Instrumentation

Tools and data sources used: Azure Monitor metrics, Application Insights traces, KQL queries, procfs readings, cgroup stats, custom application logging, load testing tools.

### 8. Procedure

Step-by-step instructions for reproducing the experiment. Detailed enough that another engineer can follow without guessing.

### 9. Expected signal

What the hypothesis predicts will appear in the instrumentation. Written before results are collected.

### 10. Results

Raw observations: data, logs, metrics, screenshots. Presented without interpretation.

### 11. Interpretation

Analysis of the results using [evidence level tags](evidence-levels.md). This section explicitly separates what was observed from what is inferred.

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
