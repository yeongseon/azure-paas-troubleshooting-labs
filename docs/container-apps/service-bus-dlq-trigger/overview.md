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

# Service Bus Dead-Letter Queue Trigger: Messages Accumulate Without Processing

!!! info "Status: Planned"

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
| Date tested | — |

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

_To be defined during execution._

### Sketch

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

- Service Bus DLQ path: `<queue-name>/$DeadLetterQueue`. KEDA scaler queue name must include this suffix to target the DLQ.
- Typical DLQ causes: max delivery count exceeded (default: 10), message TTL expired, explicit `deadLetter()` call in consumer.
- DLQ messages retain original properties but have additional DLQ-specific properties: `DeadLetterReason`, `DeadLetterErrorDescription`.

## 16. Related guide / official docs

- [Service Bus dead-letter queues](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [KEDA Service Bus scaler](https://keda.sh/docs/scalers/azure-service-bus/)
- [Container Apps scale rules](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
