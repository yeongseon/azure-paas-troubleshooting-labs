# Zip Deploy vs Custom Container Behavior

!!! info "Status: Planned"

## Question

How do deployment method differences (zip deploy vs. custom container) affect startup time, file system behavior, and troubleshooting signal availability on App Service Linux?

## Why this matters

Customers migrating between deployment methods sometimes encounter behavioral differences that are not documented. An app that works with zip deploy may behave differently in a custom container — different file system layout, different environment variable handling, different log locations. Support engineers handling "it worked before I switched to containers" tickets need to understand these differences.

## Customer symptom

"My app works with zip deploy but fails with custom container" or "Startup takes much longer after switching to container deployment."

## Planned approach

Deploy the same application using both zip deploy and custom container on the same App Service plan and SKU. Compare startup time, file system structure (writable paths, volume mounts), environment variable availability, logging behavior, and diagnostic signal visibility (Kudu, SSH, log stream).

## Key variables

**Controlled:**

- Application code (identical across both methods)
- App Service SKU and plan
- Runtime version

**Observed:**

- Startup time (cold start to first successful response)
- File system layout and writable paths
- Environment variable exposure
- Available diagnostic tools (Kudu, SSH, log stream)
- Log format and location differences

## Expected evidence tags

Observed, Measured, Correlated

## Related resources

- [Microsoft Learn: Deploy a custom container](https://learn.microsoft.com/en-us/azure/app-service/quickstart-custom-container)
- [Microsoft Learn: Zip deploy](https://learn.microsoft.com/en-us/azure/app-service/deploy-zip)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
