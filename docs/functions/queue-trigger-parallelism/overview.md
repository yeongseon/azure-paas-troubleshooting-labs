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

# Queue Trigger Parallelism and Backlog Processing

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When an Azure Functions queue trigger processes a large message backlog, how does parallelism scale across instances and workers? What are the effective throughput limits, and how do `batchSize` and `newBatchThreshold` settings affect backlog clearance rate vs. error amplification during failures?

## 2. Why this matters

Storage Queue and Service Bus queue triggers are among the most common Azure Functions trigger types. When a large backlog accumulates (e.g., after a downstream dependency was unavailable), understanding the recovery throughput is critical:
- Too-aggressive parallelism during backlog clearance causes downstream service overload
- Too-conservative settings mean slow recovery and extended customer impact
- Poison queue behavior (message repeated failure) amplifies problems during dependency outages
- Customers often misunderstand that `batchSize` is per-instance (not total)

## 3. Customer symptom

- "We had a backlog of 100,000 messages and it took 6 hours to clear."
- "After our database came back, our Functions started hammering it and caused another outage."
- "Messages keep going to the poison queue even though they would have worked if retried later."
- "We set batchSize=32 but the function is only processing 4 messages at a time."

## 4. Hypothesis

**H1 — batchSize is per-instance**: The `batchSize` setting determines how many messages each instance fetches per cycle. With 5 instances and `batchSize=16`, up to 80 messages can be in-flight simultaneously.

**H2 — Scale-out during backlog is bounded**: The scale controller will scale out aggressively during large backlogs, but will plateau at a plan-specific maximum instance count. The effective throughput ceiling is `maxInstances × batchSize × (1/messageProcessingTime)`.

**H3 — Poison queue amplification**: If a dependency is unavailable and each message fails, the message is retried `maxDequeueCount` times before going to the poison queue. During an outage, all messages may exhaust their retries and land in the poison queue, requiring manual reprocessing.

**H4 — newBatchThreshold controls fetch frequency**: `newBatchThreshold` determines at what remaining message count the instance fetches the next batch. A value of 0 means batches are fetched one at a time; a higher value means more aggressively pre-fetching.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Functions |
| Plan | Consumption |
| Region | Korea Central |
| Trigger | Azure Storage Queue |
| Runtime | Python 3.11 |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Scale + Throughput

**Controlled:**

- Message backlog size: 100, 1,000, 10,000 messages
- `batchSize`: 4, 16, 32
- `newBatchThreshold`: 1, 4, 16
- Message processing time: 100ms, 1s (simulated via sleep)
- Dependency failure: all messages fail vs. 10% fail

**Observed:**

- Time to clear backlog (messages visible = 0)
- Number of function instances during backlog clearance
- Poison queue message count after failure scenarios
- Downstream service request rate during clearance

## 7. Instrumentation

- App Insights: function invocations per minute, instance count
- Azure Storage Queue: approximate message count metric
- Custom metric: processing rate (messages/second) vs. time

**Backlog clearance KQL:**

```kusto
requests
| where name == "QueueTrigger"
| summarize invocations = count() by bin(timestamp, 1m)
| order by timestamp asc
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az storage queue create --name workqueue --account-name <storage>
az storage queue create --name workqueue-poison --account-name <storage>

# Enqueue test messages
for i in $(seq 1 1000); do
  az storage message put --queue-name workqueue \
    --content "{\"id\": $i, \"sleep_ms\": 100}" \
    --account-name <storage>
done
```

### 8.2 host.json Configuration

```json
{
  "extensions": {
    "queues": {
      "batchSize": 16,
      "newBatchThreshold": 8,
      "maxDequeueCount": 5,
      "visibilityTimeout": "00:01:30"
    }
  }
}
```

### 8.3 Scenarios

**S1 — 1,000 message backlog, batchSize=16, fast processing (100ms)**: Measure time to clearance, peak instance count, effective throughput.

**S2 — 1,000 message backlog, batchSize=4, slow processing (1s)**: Compare with S1 — measure throughput reduction and instance scaling behavior.

**S3 — Failure scenario**: All messages fail (simulate by returning non-200 from a mock endpoint). Measure time for all messages to reach poison queue. Count invocations per message.

**S4 — 10,000 message backlog**: Test scale-out ceiling on Consumption plan.

## 9. Expected signal

- **S1**: ~625 messages/second with 5 instances × 16 batch × 10 invocations/second per instance.
- **S2**: ~20 messages/second with 4 instances × 4 batch × 1 invocation/second.
- **S3**: Each message retried `maxDequeueCount` (5) times before poison queue. Total invocations = 5,000 for 1,000 messages.
- **S4**: Scale-out plateaus; Consumption plan typically limits to 200 instances.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Consumption plan cold start adds latency at the beginning of backlog clearance.
- Storage Queue has per-operation throttling; very high throughput may hit storage-side limits.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| batchSize is per-instance (not total) | **Strongly Suggested** (documented behavior) |
| All failed messages land in poison queue | **Strongly Suggested** |
| Scale-out plateaus at plan max | **Strongly Suggested** |

## 14. Related experiments

- [Timer Trigger Overlap](../timer-trigger-overlap/overview.md) — timer trigger singleton behavior
- [HTTP Concurrency Cliffs](../http-concurrency-cliffs/overview.md) — per-instance throughput limits

## 15. References

- [Azure Functions queue trigger configuration](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger)
- [host.json queues configuration](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue#host-json)

## 16. Support takeaway

For queue trigger throughput and backlog issues:

1. `batchSize` is per-instance. Effective parallelism = `batchSize × instanceCount`. A customer seeing lower-than-expected throughput should check instance count, not just batchSize.
2. During dependency outages, messages are retried `maxDequeueCount` times before the poison queue. This multiplies the invocation count and can cause 5× the expected downstream load when the dependency recovers and all queued retries fire simultaneously.
3. For large backlogs, recommend checking the downstream service rate limits before clearance begins — the Functions scale-out can easily exceed database connection limits.
4. After a poison queue accumulation, reprocessing requires: (a) diagnose root cause, (b) fix the dependency, (c) move messages from poison queue back to main queue, (d) adjust `batchSize` to pace recovery.
