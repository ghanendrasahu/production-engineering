---
topic: 20
title: Dead Letter Queues
category: A
skill: production-engineering
status: stable
---

# 020 — Dead Letter Queues

## 1. Topic name and metadata

- **Number:** 20 of 111
- **Title:** Dead Letter Queues
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [messaging-event-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/020-dead-letter-queues.md`

## 2. What it is

A holding queue (or parking lot) where messages that repeatedly fail processing are diverted after a retry limit, so one poison message cannot stall the pipeline and failures stay visible for inspection and replay.

## 3. Why it exists

One poison message must not stall the entire pipeline.

## 4. The engineering problem it solves

Without a DLQ, a single malformed message is nacked and requeued forever — hot-looping the consumer, consuming the broker, blocking every message behind it, and being retried until it corrupts throughput for healthy traffic.

## 5. How it works internally

Broker-enforced: RabbitMQ dead-letter-exchange (`x-dead-letter-exchange` on the queue; rejection/TTL/max-length expiry routes the message with original metadata + `x-death` header). SQS: `RedrivePolicy` (`maxReceiveCount`) → DLQ. Kafka: no native DLQ — implement by reading to an error topic on processing failure, or framework (Spring Kafka, kafka-dlt). Retention limits (`x-message-ttl` on DLQ) must not silently drop evidence. Replay is manual/controlled: inspect → fix consumer or data → re-publish (preserve order if possible).

## 6. Architecture and design principles

Consumer NACK/reject after max attempts → DLX/DLQ → alert + dashboard → operator imports or re-drive tool → producer/topic again.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Always, with any retry-capable queue — it is not optional plumbing.

## 8. When NOT to use it

Message loss is acceptable and volume is trivial (in-memory job list) — but you still need failure visibility somehow.

**Alternatives:** broker-less retry with inline DLQ table + sweeper job, SQS redrive policy, Kafka error topics.

<!--END-->

## 9. Implementation strategies

```bash
rabbitmqadmin declare exchange name=dlx type=direct
rabbitmqadmin declare queue name=orders-dlq durable=true arguments='{"x-message-ttl":1209600000}'
rabbitmqadmin declare binding source=dlx destination=orders-dlq routing_key=orders
rabbitmqadmin declare queue name=orders durable=true arguments='{"x-dead-letter-exchange":"dlx","x-dead-letter-routing-key":"orders"}'
```

```python
# consumer: reject without requeue after final attempt → routed to DLX
def on_message(ch, method, props, body):
    try:
        handle(body)
        ch.basic_ack(method.delivery_tag)
    except Retryable:
        ch.basic_nack(method.delivery_tag, requeue=True)   # broker counts deliveries
    except Unrecoverable as e:
        record_failed(body, str(e))
        ch.basic_reject(method.delivery_tag, requeue=False)  # → DLQ
```

## 10. Production-grade implementation

**Scenario:** Order-fulfilment consumer crashing on a schema change (`weight_kg` renamed). 4,000 messages hit max-receive-5 overnight, all in `orders-dlq`; alert fired at 02:10; team fixed the parser (accepts both keys), redrove DLQ at 09:00 — zero lost orders, one uncomfortable morning.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (inline in section 9)

This concept has no standalone Python surface — its artifacts are configuration,
templates, or pipeline steps. All runnable material for it lives inline in **section 9 (Implementation strategies)** and **section 12 (FastAPI integration)** where applicable. Do not force a toy example here.

## 12. FastAPI integration where relevant

An admin endpoint `POST /admin/dlq/redrive` (internal-only, ops auth) that re-publishes DLQ messages after a fix, disabled by default and audit-logged.

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

DLQs for failed embed/index/eval jobs — poison documents are the norm; redrive after parser/schema fixes; alert on DLQ arrival.

## 15. Security considerations

DLQs accumulate PII — redact before requeue; TTL; alert on arrival.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

NACK requeue forever; swallowing exceptions (ack always); no DLQ alerts ("we'll check manually"); DLQ as a garbage bin nobody owns; redriving everything blindly; using DLQ to hide schema mismatch instead of versioning events.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `dlq_messages_total`, `dlq_age_seconds`, redrive success rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Unit test the unrecoverable path → assert DLQ routing (testcontainers); integration test redrive; verify `x-death` attempts increment; alert fire-drill; replay-safety test on staging.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Every consumer DLQ wired at queue creation
- [ ] Alert on any DLQ message (or depth > 0)
- [ ] Retain at least 14 days
- [ ] Store full error + original payload + attempt count
- [ ] Redrive tooling with dry-run
- [ ] DLQ dashboards per queue
- [ ] Poison-message quarantine should include expiry hygiene
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** DLQ with no alerting (messages rot for months); DLQ TTL too short — auto-purge before triage; DLQ unbounded growth fills disk; replay without fixing root cause (poison returns); DLQ missing `x-death` metadata → debugging blind; auto-requeue-on-deploy of "poison" messages that fail for code reasons; redrive out of order breaking dependency sequences.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://rabbitmq.com/docs/dlx
- https://aws.amazon.com/blogs/compute/using-amazon-sqs-dead-letter-queues-redrive/

**Related topics in this library:** `#15 Message Queues`, `#16 Pub/Sub`, `#12 Retries`, `#13 Exponential Backoff`, `#14 Idempotency`, `#62 Alerts`.
