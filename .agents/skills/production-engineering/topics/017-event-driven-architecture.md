---
topic: 17
title: Event-Driven Architecture
category: A
skill: production-engineering
status: stable
---

# 017 — Event-Driven Architecture

## 1. Topic name and metadata

- **Number:** 17 of 111
- **Title:** Event-Driven Architecture
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [messaging-event-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/017-event-driven-architecture.md`

## 2. What it is

An architectural style in which services communicate by emitting and reacting to immutable facts (events) rather than by issuing remote procedure calls; the event is the integration contract.

## 3. Why it exists

Services that react to facts decouple; callers chain their fates.

## 4. The engineering problem it solves

Synchronous chains mean the slowest dependency sets every request's latency and the least reliable one sets every caller's availability; features change by editing every participant. Events invert this: producers don't know their consumers.

## 5. How it works internally

Domain events (`OrderPlaced`) vs notification events (thin "something changed") vs event-carried state transfer (fat events with full payload). Delivery at-least-once; consumers maintain own state projection. Choreography (no central coordinator — emergent flow, risk of implicit control flow) vs orchestration (a saga/orchestrator commands services — explicit flow, easier to reason). Event store or log (Kafka, EventStoreDB) provides replay and temporal audit; exactly-once is only achievable as effectively-once via idempotency + transactions at consumers.

## 6. Architecture and design principles

Services own their data, publish facts, other services project their read models. No "distributed monolith" via synchronous calls pretending to be events.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Multiple consumers need the same fact, decoupling deploy/scale boundaries, audit/replay needs, temporal decoupling acceptable.

## 8. When NOT to use it

Strictly sequential request/response with need for immediate confirmation; a monolith that can use in-process calls — events inside one process buy nothing; team immature in operations.

**Alternatives:** direct synchronous calls behind circuit breakers, outbox + webhooks, CDC.

## 9. Implementation strategies

Outbox pattern to avoid dual-write: write event to an `outbox` table in the same transaction as the state change; a relay (Debezium CDC or a poller) publishes to the broker; services consume idempotently.

```sql
CREATE TABLE outbox (id uuid PRIMARY KEY, topic text NOT NULL, key text, payload jsonb NOT NULL,
                     created_at timestamptz DEFAULT now(), published boolean DEFAULT false);
```

```python
# inside the same DB transaction as the business write
session.add(Outbox(topic="orders", key=str(user_id), payload={"type": "order.created", "id": order_id}))
session.commit()  # relay publishes afterwards — no dual-write inconsistency
```

## 10. Production-grade implementation

**Scenario:** E-commerce: `order.created` → billing creates invoice, inventory reserves, email sends receipt, search/reco project state. p95 checkout 180ms (no downstream calls); warehouse lag 2s; one new consumer (loyalty points) added with zero changes to the order service.

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

Order endpoint validates + commits + outbox row atomically; returns 202 or 201 with `order_id`; the consumer services update their own projections asynchronously.

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Agent architectures are event-driven: tool calls emit facts; human approvals are events; the orchestrator reacts — choreography fits fanout, orchestration (saga) fits multi-step with compensation.

## 15. Security considerations

Outbox relay runs with DB creds — least privilege; payloads signed if crossing trust zones.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Calling the broker inside the request path for mandatory synchronous outcomes; events with no schema; PII sprayed into all topics; no replay strategy; mixing query events and commands; "event-driven" as a label for async calls with no contract to fall back on.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `outbox_pending`, projection lag, event consumption rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Integration tests with the full pipeline (publish → consumers → projections); contract tests per event type; replay test (reset group, reprocess a day of events into a scratch DB); chaos test dropping the broker; verify outbox relay marks rows published exactly once.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Outbox or CDC — never dual-write
- [ ] Thin events + consumer-side fetch, or fat events by design choice
- [ ] Schema registry
- [ ] Explicit event ownership
- [ ] Versioned topics (`orders.v2`)
- [ ] Idempotent consumers
- [ ] DLQs
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Dual-write bug (DB commit succeeds, broker publish fails) → outbox required; event schema drift breaks consumers silently; "event as god-object" carrying PII into analytics topics (data governance); replay causes non-idempotent side effects (emails re-sent); implicit choreography becomes untraceable (who does what on `payment.failed`?); poison events stall a consumer group.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.martinfowler.com/eaaDev/EventCollaboration.html
- https://cloudevents.io/

**Related topics in this library:** `#16 Pub/Sub`, `#15 Message Queues`, `#19 Saga Pattern`, `#18 Distributed Transactions`, `#50 Cache Invalidation` (events invalidate caches), `#66 Observability` (trace across events).
