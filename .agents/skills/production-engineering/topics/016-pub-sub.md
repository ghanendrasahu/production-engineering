---
topic: 16
title: Pub/Sub
category: A
skill: production-engineering
status: stable
---

# 016 — Pub/Sub

## 1. Topic name and metadata

- **Number:** 16 of 111
- **Title:** Pub/Sub
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [messaging-event-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/016-pub-sub.md`

## 2. What it is

A messaging pattern where producers publish to a topic and every subscribed consumer group receives its own copy — one-to-many fanout, no consumer competing for a single stream of messages.

## 3. Why it exists

One event should reach every interested consumer without coupling.

## 4. The engineering problem it solves

When many services need to react to the same business fact (order placed → email, inventory, analytics, fraud scoring), point-to-point calls multiply and couple producers to all consumers; adding a consumer means changing the producer.

## 5. How it works internally

Topic/exchange holds named subscriptions or consumer groups; each group keeps an independent cursor/offset. Kafka: one topic → N consumer groups, each group re-reads the log independently; ordering per key within a partition; retention time/size-based. RabbitMQ: exchange type `fanout` or `topic` (routing keys with `*`/`#`) → queue binding per subscriber — classic pub/sub. Redis `PUBLISH` is fire-and-forget, no persistence (Redis Streams are the durable option). Delivery still at-least-once; each group needs its own DLQ.

## 6. Architecture and design principles

Service emits domain events to a topic → independent consumers (billing, email, search indexer, warehouse) each subscribe with their own group.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Multiple independent consumers of the same fact, event sourcing-ish audit needs, replayability matters.

## 8. When NOT to use it

Only one consumer exists (a queue is simpler); you need request/response semantics; sub-millisecond latency required (use sync RPC).

**Alternatives:** `#15 Message Queues` (competing consumers), CDC (Debezium) from the DB, direct service calls with a circuit breaker.

## 9. Implementation strategies

```yaml
# RabbitMQ topic exchange
exchange: events (topic)
binding: orders.* → queue email-svc (routing key orders.created)
binding: orders.* → queue inventory-svc (same key)
```

```python
# Publisher (kafka-python style)
producer = KafkaProducer(bootstrap_servers=["kafka:9092"])
producer.send("orders", key=b"user:42", value=b'{"type":"order.created","id":"o_9","total":129.0}')
```

## 10. Production-grade implementation

**Scenario:** `order.created` topic with 8 partitions; consumers: search-indexer (lag p99 300ms), recommendation-trainer (batch micro-batch of 500, lag 30s), fraud-scorer (synchronous-ish, lag 50ms). One consumer crashes; its group falls behind — others unaffected; replay via resetting offsets.

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

Dependency that injects a cached `KafkaProducer` (singleton) into routes; publish after DB commit, key by user to preserve order per user.

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Embedding and eval fanout: one event → indexing, eval, cost-metering consumers — all independent groups on the same topic.

## 15. Security considerations

Topics leak — tenant-scope; encrypt payloads; audit publishers.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Pub/sub with no consumer ownership ("everyone may read"); giant events; no replay story; mixing command and event semantics in one topic; Redis PUBLISH for work that must not be lost; shared consumer groups meant to be separate.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `pubsub_lag_seconds{group}`, `events_published_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Publish synthetic event; assert each group received and applied it; simulate consumer down → replay after recovery; contract test event schema in CI; load test verifying lag within SLO at 3x; duplicate-delivery test.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Version events
- [ ] Schema registry (Avro/Protobuf) with compatibility rules
- [ ] Independent DLQs per group
- [ ] Lag alerting per group
- [ ] Small events (carry IDs, fetch details
- [ ] Not megabyte payloads)
- [ ] Idempotent consumers
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Consumer group lag explodes silently (no lag alerting); slow consumer blocks partition processing for its group (head-of-line blocking); event schema breaks consumers (no schema registry/versioning); duplicate events after rebalance (at-least-once) — consumers must dedupe; one poison event crash-loops a consumer for the whole group; topic retention too short → late consumer cannot replay.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kafka.apache.org/documentation/

**Related topics in this library:** `#15 Message Queues`, `#17 Event-Driven Architecture`, `#14 Idempotency`, `#20 Dead Letter Queues`, `#100 gRPC` (sync alternative), `#101 Webhooks`.
