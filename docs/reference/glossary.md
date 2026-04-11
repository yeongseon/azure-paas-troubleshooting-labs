---
hide:
  - toc
---

# Glossary

Key terms and concepts used throughout this troubleshooting lab site. Terms are grouped by category for quick reference.

## Azure Platform

| Term | Definition |
|------|-----------|
| **App Service Plan** | The compute resource allocation boundary for App Service apps. Defines available CPU, memory, and features. Multiple apps can share a single plan. |
| **ARR (Application Request Routing)** | The frontend load balancer and reverse proxy for Azure App Service. Handles SSL termination, session affinity, and request routing to worker instances. |
| **Container Apps Environment** | The secure boundary around a group of Container Apps. Provides a shared VNet, logging destination, and Dapr configuration. Analogous to a Kubernetes namespace. |
| **Consumption Plan** | A serverless hosting model (Functions or Container Apps) where compute resources are allocated on demand and scale to zero when idle. Pay-per-execution pricing. |
| **Flex Consumption** | A Functions hosting plan that combines scale-to-zero with per-function scaling, VNet support, and configurable instance sizes. |
| **Premium Plan** | A Functions hosting plan with pre-warmed instances (no cold start), VNet integration, and higher resource limits. Always-on pricing. |
| **Revision** | An immutable snapshot of a Container App's configuration and code. Traffic can be split across revisions for blue-green deployment or A/B testing. |
| **Worker** | A virtual machine instance that runs App Service application containers. Workers are shared across all apps in the same App Service Plan. |

## Networking

| Term | Definition |
|------|-----------|
| **SNAT (Source Network Address Translation)** | The mechanism Azure uses to translate outbound connections from private instance IPs to public IPs. Each instance has a limited pool of SNAT ports (typically 128). |
| **VNet Integration** | Connecting an Azure PaaS service to a Virtual Network, enabling access to private resources and custom DNS resolution. |
| **Private Endpoint** | A network interface that connects a PaaS service to a private IP address within a VNet. Eliminates public internet exposure. |
| **Private DNS Zone** | An Azure DNS zone for resolving private endpoint FQDNs to their private IP addresses within a VNet. |
| **DNS Negative Caching** | Caching of failed DNS lookup results (NXDOMAIN or SERVFAIL). Negative cache entries can extend outages because subsequent lookups return the cached failure without re-querying. |
| **Envoy Proxy** | The ingress proxy used by Azure Container Apps. Handles HTTP routing, TLS termination, and load balancing across replicas. |
| **SNI (Server Name Indication)** | A TLS extension that allows a client to specify the hostname during the TLS handshake, enabling the server to select the correct certificate. |

## Container & Process

| Term | Definition |
|------|-----------|
| **cgroup (Control Group)** | A Linux kernel feature that limits and isolates resource usage (CPU, memory, I/O) for a group of processes. Azure uses cgroups to enforce container memory limits. |
| **OOM Kill (Out of Memory Kill)** | When a process exceeds its cgroup memory limit, the Linux OOM killer sends SIGKILL to terminate the process. The kill target is selected based on the OOM score. |
| **PID 1** | The first process started inside a container. If PID 1 dies, the container restarts. Multi-process servers (gunicorn) use PID 1 as a master that spawns workers, so worker OOM kills don't restart the container. |
| **Writable Layer** | The thin overlay filesystem layer on top of read-only container image layers. Data written here is ephemeral — lost on container restart. |
| **CIFS/SMB Mount** | The network filesystem protocol used by App Service to mount the `/home` directory from Azure Storage. Provides persistent storage that survives container restarts. |
| **Overlay Filesystem** | A union filesystem that layers a writable directory on top of read-only image layers. Used by Docker and App Service for container filesystems. |

## Monitoring & Telemetry

| Term | Definition |
|------|-----------|
| **Application Insights** | Azure's application performance management (APM) service. Collects traces, metrics, exceptions, and dependency calls. |
| **ContainerAppConsoleLogs** | Log Analytics table containing stdout/stderr output from Container App containers. Often the only source of OOM kill evidence. |
| **ContainerAppSystemLogs** | Log Analytics table containing platform lifecycle events (container start, stop, crash, image pull) for Container Apps. Does NOT capture worker-level OOM kills. |
| **KQL (Kusto Query Language)** | The query language used in Azure Monitor, Log Analytics, and Application Insights. Used to analyze logs and metrics. |
| **WorkingSetBytes** | Azure Monitor metric showing container memory usage. Reports 1-minute averages, which can significantly underreport peak memory usage. |
| **RestartCount** | Azure Monitor metric tracking container-level restarts. Stays at 0 for worker-level OOM kills because the container itself (PID 1) never restarts. |
| **PT1M** | ISO 8601 duration notation for 1 minute. Azure Monitor metrics are typically aggregated at PT1M granularity, meaning peaks within a minute are averaged out. |

## Scaling

| Term | Definition |
|------|-----------|
| **KEDA (Kubernetes Event-Driven Autoscaling)** | The autoscaler used by Azure Container Apps. Monitors event sources (HTTP traffic, queue length) and adjusts replica count. |
| **Scale to Zero** | A feature of Consumption-tier services where all instances are deallocated when there is no traffic. The first request after idle requires cold start allocation. |
| **Cold Start** | The latency incurred when a new instance must be allocated, initialized, and loaded before it can handle requests. Occurs after scale-to-zero or during scale-out. |
| **Scale Controller** | The Azure Functions component that monitors event sources and makes scaling decisions (add/remove instances). |

## Identity & Security

| Term | Definition |
|------|-----------|
| **Managed Identity** | An Azure-managed service principal that provides automatic credential management for PaaS services. Eliminates the need to store secrets in code or configuration. |
| **RBAC (Role-Based Access Control)** | Azure's authorization system for granting permissions to resources. Role assignments propagate through Microsoft Entra ID with a delay (typically seconds to minutes). |
| **IMDS (Instance Metadata Service)** | The endpoint (`169.254.169.254`) running on Azure VMs that provides managed identity tokens and instance metadata. |
| **Microsoft Entra ID** | Azure's identity and access management service (formerly Azure Active Directory). Issues tokens for managed identity and user authentication. |

## Experiment Methodology

| Term | Definition |
|------|-----------|
| **Config Experiment** | An experiment where the outcome is deterministic (it works or it doesn't). A single valid run is sufficient. |
| **Performance Experiment** | An experiment where outcomes vary between runs. Requires multiple independent runs with statistical analysis. |
| **Evidence Level** | A calibrated tag (Observed, Measured, Correlated, Inferred, Strongly Suggested, Not Proven, Unknown) indicating the strength of evidence supporting a claim. |
| **Falsifiable Hypothesis** | A prediction stated before the experiment that can be proven wrong by the results. Required for every experiment in this repository. |
| **Independent Run** | A complete experiment execution with fresh resource deployment. Multiple probes within one deployment are NOT independent runs. |
