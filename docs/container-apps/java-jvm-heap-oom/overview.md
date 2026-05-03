---
hide:
  - toc
validation:
  az_cli:
    last_tested: null
    result: not_tested
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Java Container JVM Heap OOM vs. Container Memory Limit

!!! info "Status: Planned"

## 1. Question

A Java container app on Container Apps has a configured memory limit (e.g., 2Gi). The JVM inside the container also has its own heap settings (`-Xmx`). When the JVM heap is set larger than the container memory limit, or when the JVM tries to expand beyond the container limit (due to off-heap memory: metaspace, thread stacks, native memory), what is the failure mode — JVM OutOfMemoryError or cgroup OOM kill?

## 2. Why this matters

Java applications have two memory boundaries: the JVM heap (`-Xmx`) and the total container memory limit enforced by cgroups. Off-heap memory (metaspace, native buffers, JIT compiled code cache, thread stacks) is not counted in the JVM heap but is counted by the cgroup. When the total JVM memory footprint (heap + off-heap) exceeds the cgroup limit, the container is OOM-killed by the OS, not by the JVM. The Java process never throws `OutOfMemoryError` — it is terminated externally, often without any meaningful log message. This confuses Java developers who expect to catch or log OOM conditions.

## 3. Customer symptom

"The Java app crashes with no error message — just disappears" or "No OutOfMemoryError in logs but the container restarts randomly" or "JVM heap is only at 60% but the container keeps getting OOM-killed."

## 4. Hypothesis

- H1: When `-Xmx` is set to the same value as the container memory limit (e.g., both 2Gi), off-heap memory (typically 200-500MB for a modern JVM) pushes total memory usage beyond the cgroup limit, causing an OOM kill without any Java-level exception.
- H2: The OOM kill is visible in Container Apps system logs (`ContainerAppSystemLogs`) as a container restart with exit code 137 (SIGKILL from OOM killer), not as a Java exception.
- H3: Setting `-Xmx` to 75-80% of the container memory limit leaves headroom for off-heap memory, preventing unexpected OOM kills while using the available memory efficiently.
- H4: Modern JVMs (Java 11+) support container-awareness via `-XX:+UseContainerSupport` (enabled by default), which reads cgroup limits and sets heap defaults accordingly. However, explicit `-Xmx` overrides this, potentially causing over-allocation.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Java 21 (OpenJDK) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Runtime / Resource limits

**Controlled:**

- Container memory limit: 1Gi
- JVM `-Xmx` settings: 1024m (100% of limit), 768m (75%), 512m (50%)
- Memory allocation endpoint that grows heap incrementally

**Observed:**

- Exit code when container is terminated (137 = OOM kill, 1 = JVM exception)
- JVM heap usage at time of termination
- Presence or absence of `OutOfMemoryError` in logs

**Scenarios:**

- S1: `-Xmx1024m`, 1Gi container limit → OOM kill (off-heap overflow)
- S2: `-Xmx768m`, 1Gi container limit → sufficient headroom (no kill)
- S3: Container-aware JVM without explicit `-Xmx` → JVM self-limits heap correctly

## 7. Instrumentation

- `ContainerAppSystemLogs` for container restart events and exit codes
- JVM GC logs (`-Xlog:gc*`) to observe heap pressure
- `/actuator/metrics/jvm.memory.used` (Spring Boot) or equivalent for heap monitoring
- `ContainerAppConsoleLogs` for `OutOfMemoryError` stack traces (if any)

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Spring Boot app with memory allocation endpoint; container limit 1Gi; `-Xmx1024m`.
2. S1: Allocate memory via endpoint until OOM; observe whether Java throws `OutOfMemoryError` or container is killed (exit 137).
3. S2: Change to `-Xmx768m`; repeat allocation; verify Java throws `OutOfMemoryError` at heap limit (container survives).
4. S3: Remove explicit `-Xmx`; deploy with `-XX:+UseContainerSupport`; observe JVM-chosen heap limit; repeat allocation.

## 9. Expected signal

- S1: Container restarts with exit code 137; no `OutOfMemoryError` in logs; JVM heap is not at 100%.
- S2: Java throws `OutOfMemoryError: Java heap space`; container stays running (exception is caught or app restarts gracefully).
- S3: JVM limits heap to approximately 50-75% of container limit automatically; `OutOfMemoryError` if heap is exhausted.

## 10. Results

_Awaiting execution._

## 11. Interpretation

_Awaiting execution._

## 12. What this proves

_Awaiting execution._

## 13. What this does NOT prove

_Awaiting execution._

## 14. Support takeaway

_Awaiting execution._

## 15. Reproduction notes

- OOM kill exit code: 137 (128 + 9/SIGKILL). Observable in `ContainerAppSystemLogs` as `exitCode: 137`.
- `UseContainerSupport` is enabled by default in Java 11+. Without explicit `-Xmx`, the JVM typically sets heap to 25% of available memory (at <256M) or up to 100% if MaxRAMPercentage is set.
- Recommended: set `-XX:MaxRAMPercentage=75.0` instead of explicit `-Xmx` for container-aware heap sizing.

## 16. Related guide / official docs

- [Container-aware JVM options](https://www.baeldung.com/java-jvm-parameters-tuning-containers)
- [Container Apps OOM visibility](https://learn.microsoft.com/en-us/azure/container-apps/observability)
- [JVM memory areas and off-heap](https://docs.oracle.com/en/java/javase/17/vm/garbage-collector-implementation.html)
