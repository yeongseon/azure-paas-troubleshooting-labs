# Memory Pressure on App Service

!!! info "Status: Planned"

## Question

Does plan-level memory pressure on a shared App Service plan degrade performance of individual apps, and can kernel page reclaim cause observable CPU increase even when application code is not CPU-intensive?

## Why this matters

Memory pressure on shared App Service plans is a frequent source of support tickets. Customers report slow responses or high CPU without obvious application-level causes. The challenge is determining whether the degradation is caused by one app's memory consumption affecting others on the same plan, or by platform-level memory management overhead (swap thrashing, page reclaim) that manifests as CPU usage.

Support engineers need to quickly distinguish between "your app is using too much memory" and "another app on your plan is causing plan-level pressure."

## Customer symptom

"My app is slow but CPU usage looks normal" or "All apps on the plan became slow at the same time."

## Planned approach

Deploy multiple applications on a shared App Service plan (B1/B2 Linux). Deliberately induce memory pressure from one application while monitoring the performance of a second, idle application. Measure CPU, memory, swap usage, and response latency across both apps using Azure Monitor, Application Insights, and procfs.

## Key variables

**Controlled:**

- Memory allocation rate and size in the pressure-inducing app
- Plan SKU and instance count
- Baseline load on the observer app

**Observed:**

- Response latency on the observer app
- CPU percentage (user vs. system) on the instance
- Swap usage and page fault rate
- OOM kill events

## Expected evidence tags

Measured, Correlated, Inferred

## Related resources

- [lab-memory-pressure](https://github.com/yeongseon/lab-memory-pressure) — earlier individual experiment
- [lab-node-memory-pressure](https://github.com/yeongseon/lab-node-memory-pressure) — Node.js-specific memory pressure experiment
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide) — App Service reference
- [Microsoft Learn: App Service diagnostics](https://learn.microsoft.com/en-us/azure/app-service/overview-diagnostics)
