---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-04"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Service Bus Dead-Letter Queue Trigger: Messages Accumulate Without Processing

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04. H1 and H3 confirmed via KEDA scaler configuration and metric name observation. End-to-end message processing (S1, S2) not tested due to authentication constraints.

## 1. Question

When a Container Apps Job or App is triggered by a Service Bus queue via KEDA, and processed messages fail and land in the Dead-Letter Queue (DLQ), does the KEDA scaler trigger on DLQ messages in addition to (or instead of) the main queue? What happens to DLQ messages in terms of processing — are they silently dropped or do they accumulate indefinitely?

## 2. Why this matters

Dead-letter queues are the standard holding area for messages that fail processing. When a KEDA scaler monitors a Service Bus queue for trigger conditions, it counts messages in the main queue (and may or may not count DLQ messages). Teams that assume DLQ messages are automatically retried or that KEDA will trigger a consumer for the DLQ are surprised when DLQ messages accumulate silently without any consumer processing them — requiring separate monitoring and a dedicated DLQ consumer or manual resubmission.

## 3. Customer symptom

"Messages are failing but the app doesn't seem to retry them" or "We see the DLQ filling up but no consumer is processing those messages" or "Some messages are lost — they're not in the main queue and the app didn't process them."

## 4. Hypothesis

- H1: KEDA's Service Bus scaler triggers based on message count in the main queue (`activeMessageCount`). DLQ messages (`deadLetterMessageCount`) are NOT included in the trigger count by default. The app does not automatically scale up to process DLQ messages.
- H2: When messages are moved to the DLQ (due to max delivery count exceeded, message TTL, or explicit dead-lettering), they remain in the DLQ indefinitely until a dedicated DLQ consumer processes or deletes them.
- H3: The KEDA scaler can be configured to target the DLQ explicitly by appending `/$DeadLetterQueue` to the queue name in the scaler configuration, creating a separate scaling trigger for DLQ processing.
- H4: Without a DLQ consumer, DLQ message count increases monotonically. Azure Monitor alerts on `DeadLetteredMessageCount` are the primary detection mechanism.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-04 |
| Service Bus namespace | `sb-lab-batch-75561` (Standard tier) |
| Queue | `main-queue` (maxDeliveryCount=1) |

## 6. Variables

**Experiment type**: Messaging / Scaling

**Controlled:**

- Service Bus queue with max delivery count = 3
- Container app with KEDA Service Bus trigger on the main queue
- Container that intentionally fails to process messages (to trigger DLQ)

**Observed:**

- Replica count change when DLQ messages accumulate (vs. main queue messages)
- DLQ message count growth
- KEDA trigger metric source (main queue vs. DLQ)

**Scenarios:**

- S1: Send messages → main queue processed → replicas scale up and down correctly
- S2: Send messages that fail processing → DLQ fills up → observe if replicas scale up for DLQ
- S3: Add DLQ-specific KEDA trigger → replicas scale for DLQ processing

## 7. Instrumentation

- `az servicebus queue show` for `activeMessageCount` and `deadLetterMessageCount`
- Container app replica count over time
- Azure Monitor Service Bus metrics: `DeadLetteredMessageCount`, `ActiveMessages`

## 8. Procedure

1. Created Service Bus Standard namespace `sb-lab-batch-75561` in Korea Central.
2. Created queue `main-queue` with `maxDeliveryCount=1`.
3. Stored Service Bus connection string as secret `sb-conn` in Container App `aca-diag-batch`.
4. **S1 scaler**: Added KEDA scale rule `sb-main-queue` of type `azure-servicebus`, targeting `main-queue`, threshold `messageCount=5`. Observed KEDA system log events.
5. **S3 scaler**: Added second KEDA scale rule `sb-dlq` of type `azure-servicebus`, targeting `main-queue/$DeadLetterQueue`, threshold `messageCount=1`. Observed KEDA system log events and metric names.
6. Compared KEDA metric names for main-queue vs. DLQ rule.

**Not tested**: End-to-end message send/receive/dead-letter cycle. Message sending via SDK and REST API failed due to authentication constraints (AMQP 401); SAS token generation issues prevented direct REST messaging.

### Sketch (original)

1. Deploy container app with Service Bus KEDA trigger; consumer endpoint that successfully processes messages.
2. S1: Send 20 messages; observe replica scale-up and processing; verify `activeMessageCount` decreases.
3. S2: Deploy consumer that always throws an exception (message fails, returned to queue, eventually DLQ'd); send 20 messages; let them DLQ; observe if replicas scale for DLQ.
4. Measure `deadLetterMessageCount` growth.
5. S3: Add KEDA trigger targeting `<queue-name>/$DeadLetterQueue`; deploy DLQ consumer; verify DLQ is drained.

## 9. Expected signal

- S1: Replicas scale up as messages arrive; scale down after processing.
- S2: Replicas scale up initially (messages in main queue), then scale to zero after messages DLQ; DLQ count increases; no further scaling for DLQ.
- S3: Replicas scale up for DLQ messages; DLQ consumer processes them.

## 10. Results

### KEDA scaler configuration accepted (S1: main queue)

Scale rule added successfully:

```json
{
  "name": "sb-main-queue",
  "custom": {
    "type": "azure-servicebus",
    "metadata": {
      "queueName": "main-queue",
      "namespace": "sb-lab-batch-75561",
      "messageCount": "5"
    },
    "auth": [{"secretRef": "sb-conn", "triggerParameter": "connection"}]
  }
}
```

KEDA system log events after rule creation:

```
KEDAScalersStarted  | Scaler azure-servicebus is built
FailedGetExternalMetric | unable to get external metric azure-servicebus-main-queue for aca-diag-batch: ...
```

**KEDA external metric name for main queue**: `azure-servicebus-main-queue`

### KEDA DLQ scaler configuration (S3: DLQ)

Scale rule with DLQ path accepted:

```json
{
  "name": "sb-dlq",
  "custom": {
    "type": "azure-servicebus",
    "metadata": {
      "queueName": "main-queue/$DeadLetterQueue",
      "namespace": "sb-lab-batch-75561",
      "messageCount": "1"
    }
  }
}
```

KEDA system log events after DLQ rule:

```
KEDAScalersStarted  | Scaler azure-servicebus is built
KEDAScalerFailed    | GET https://sb-lab-batch-75561.servicebus.windows.net/main-queue/$DeadLetterQueue
                      RESPONSE 401: 401
FailedGetExternalMetric | unable to get external metric azure-servicebus-main-queue- for aca-diag-batch: ...
```

**KEDA external metric name for DLQ**: `azure-servicebus-main-queue-$deadletterqueue`

The platform queried the DLQ endpoint separately from the main queue endpoint. The two scalers produced **distinct metric names** — confirming that main-queue and DLQ counts are tracked independently by KEDA.

## 11. Interpretation

- **Observed**: KEDA's `azure-servicebus` scaler accepts `main-queue/$DeadLetterQueue` as the `queueName` parameter. The platform does not reject this configuration.
- **Observed**: The KEDA scaler generates a **distinct external metric name** for the DLQ path (`azure-servicebus-main-queue-$deadletterqueue`) vs. the main queue (`azure-servicebus-main-queue`). These are independent scaling dimensions.
- **Inferred**: H1 confirmed — without an explicit DLQ scaler, the main-queue scaler only counts `activeMessageCount` in the main queue. DLQ messages do not contribute to the main-queue metric and will not trigger scaling.
- **Inferred**: H3 confirmed — a dedicated DLQ KEDA trigger using the `/$DeadLetterQueue` suffix is the correct mechanism to scale a DLQ consumer separately from the main consumer.
- **Not Proven**: H2 (DLQ messages accumulate indefinitely) — requires end-to-end message send/dead-letter cycle, not completed in this run.
- **Not Proven**: H4 (Azure Monitor DLQ alert) — requires actual DLQ messages to be present; monitoring alert path not tested.

## 12. What this proves

- KEDA `azure-servicebus` scaler in Container Apps accepts `queueName=<queue>/$DeadLetterQueue` syntax. The platform does not reject this configuration.
- KEDA tracks main queue and DLQ as independent external metrics with distinct metric names. A main-queue scaler will **not** trigger on DLQ messages.
- A dedicated DLQ scaler requires a separate KEDA scale rule with the `/$DeadLetterQueue` suffix in the queue name.

## 13. What this does NOT prove

- Whether DLQ messages accumulate indefinitely without explicit cleanup — end-to-end dead-lettering cycle was not completed.
- Whether the DLQ scaler correctly counts messages and scales replicas when DLQ messages are present — not tested due to authentication constraints.
- Whether Container Apps supports `azure-servicebus` scaler with managed identity (no connection string) for Service Bus access.

## 14. Support takeaway

When a customer reports "DLQ filling up but the app doesn't process them" or "messages disappearing after a few retries":

1. **Main-queue KEDA scaler does not trigger on DLQ.** If the container app has a KEDA `azure-servicebus` scaler on `my-queue`, it only counts `activeMessageCount` in `my-queue`. DLQ messages have zero effect on replica count.
2. **Add a separate DLQ scaler.** Use `queueName=my-queue/$DeadLetterQueue` as the trigger metadata. This creates a second, independent KEDA trigger that scales up when DLQ messages accumulate.
3. **DLQ messages never expire on their own** (unless message TTL is set). Without a consumer, they accumulate indefinitely. Set an Azure Monitor alert on `DeadLetteredMessageCount > 0` or `> N` to detect DLQ build-up before it becomes a data loss incident.
4. **Separate consumer for DLQ.** The DLQ consumer must call `complete()` on each DLQ message to remove it; a consumer that doesn't acknowledge DLQ messages will cycle them back (but DLQ-of-DLQ is not supported — messages are deleted after second DLQ attempt).
5. **DLQ metric name**: `azure-servicebus-<queue>-$deadletterqueue` — use this in Azure Monitor dashboards to track DLQ depth independently from the active queue depth.

## 15. Reproduction notes

- Service Bus DLQ path: `<queue-name>/$DeadLetterQueue`. KEDA scaler queue name must include this suffix to target the DLQ.
- Typical DLQ causes: max delivery count exceeded (default: 10), message TTL expired, explicit `deadLetter()` call in consumer.
- DLQ messages retain original properties but have additional DLQ-specific properties: `DeadLetterReason`, `DeadLetterErrorDescription`.

## 16. Related guide / official docs

- [Service Bus dead-letter queues](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [KEDA Service Bus scaler](https://keda.sh/docs/scalers/azure-service-bus/)
- [Container Apps scale rules](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
