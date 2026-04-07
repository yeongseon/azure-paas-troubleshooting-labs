# Node.js Memory Pressure: Comparison Study

!!! info "Status: Evaluation"
    This page evaluates results from [lab-node-memory-pressure](https://github.com/yeongseon/lab-node-memory-pressure) for potential migration.

## Summary

The Node.js experiment was conducted alongside the Flask experiment (see [Memory Pressure Overview](overview.md)) to compare behavior across deployment models.

## Key Findings

### Deployment Model Differences

- Flask (ZIP Deploy): Memory reported 76-95%
- Node.js (Container): Memory reported 73-77%

### Stability Comparison

| Config | Flask Result | Node.js Result |
|--------|--------------|----------------|
| 8 apps × 50MB | 6 errors (503) | 0 errors |
| 4 apps × 175MB | Stable, 6min cold start | Stable, normal cold start |

### Why the Difference?

- Container memory accounting differs from process-level accounting
- Web App for Containers may have different memory isolation
- MemoryPercentage metric may not capture container memory the same way

## Migration Recommendation

**Recommendation**: Integrate as comparison section in main Memory Pressure experiment rather than separate experiment.

**Rationale**:

1. Same hypothesis tested
2. Same environment (B1, koreacentral)
3. Value is in the comparison, not standalone findings
4. Avoids duplication

## Action Items

- [x] Document Node.js results in main experiment
- [ ] Archive lab-node-memory-pressure repository
- [ ] Add cross-reference links

## See Also

- [Memory Pressure Overview](overview.md)
- [lab-node-memory-pressure](https://github.com/yeongseon/lab-node-memory-pressure)

## Sources

- [Microsoft Learn: Monitor App Service instances by using metrics](https://learn.microsoft.com/en-us/azure/app-service/web-sites-monitor)
- [Microsoft Learn: Configure a custom Linux container for Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container)
