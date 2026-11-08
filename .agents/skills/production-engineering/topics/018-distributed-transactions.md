---
topic: 18
title: Distributed Transactions
category: A
skill: production-engineering
status: stable
---

# 018 — Distributed Transactions

## 1. Topic name and metadata

- **Number:** 18 of 111
- **Title:** Distributed Transactions
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [messaging-event-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/018-distributed-transactions.md`

## 2. What it is

A transaction spanning multiple services or databases that must commit or roll back as a unit; in practice achieved via 2PC/XA protocols or via saga orchestration, since strict atomic durability across services is rarely available.

## 3. Why it exists

Multi-service writes must not half-complete and be forgotten.

## 4. The engineering problem it solves

A business operation ("reserve inventory + charge card + ship") cannot fail halfway: partial commits leave stock reserved without payment, or payment without stock.

## 5. How it works internally

Two-phase commit: coordinator asks all participants to prepare (hold locks, vote), then commit/abort on unanimous yes. Guarantees atomicity but blocks on coordinator crash and holds locks across the network — fragile, rarely used across microservices. XA exists in Java/some DBs (not native in Python/FastAPI). Practical alternative: sagas — a sequence of local transactions, each with a compensating action (refund, release reservation). Outbox per service guarantees event emission aligns with local commit. Exactly-once across systems does not exist; effectively-once = local transaction + idempotent consumers.

## 6. Architecture and design principles

Saga orchestrator (Temporal workflow, custom DB state machine, AWS Step Functions) drives service A→B→C with timeouts and compensations; each service keeps its own atomic local commit.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Multi-service writes that must not silently diverge — money, inventory, bookings.

## 8. When NOT to use it

Everything fits in one database (one transaction wins); data loss tolerable (queue + replay); operational maturity for sagas missing.

**Alternatives:** modular monolith (single DB transaction), saga orchestration, CDC-based synchronization, accept eventual consistency with reconciliation jobs.

## 9. Implementation strategies

Avoid 2PC across services. If atomicity truly required within one Postgres: single-phase, same instance, one transaction. Across two databases: XA not available cleanly in Python → prefer saga + outbox, or make one database the system of record and the other a derived projection.

```python
# outbox + idempotency gives effectively-once between your DB and downstream
with session.begin():
    order = create_order(session, ...)           # local commit
    session.add(Outbox(topic="orders", key=order.id, payload={...}))
```

## 10. Production-grade implementation

**Scenario:** Airline booking: reserve seat (inventory service) → charge card (payments) → issue ticket (fulfilment). Charge succeeds, ticket fails → saga compensates: refund payment, release seat; customer emailed "booking failed, refunded"; all steps logged with saga_id.

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

Checkout endpoint: validate → local transaction (order + outbox) → return 202. Saga worker calls billing → shipping → marks saga complete; on ship failure it publishes `refund.requested`.

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Agent actions spanning billing/inventory/email need saga semantics: charge → reserve → fulfill with refund/release compensations; local commits only; idempotent steps.

## 15. Security considerations

Compensations can move real money — audit saga outcomes; four-eyes for high-value steps.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

2PC across microservices; "best effort" multi-service writes with no compensation plan; distributed transactions across a third-party API with no refund endpoint; sagas with no monitoring (they rot silently); compensations not idempotent.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `saga_duration_seconds`, `compensations_total`, stuck-saga count

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest per saga step incl. compensation path (force ship failure → assert refund + release); crash-injection between steps; replay test with duplicated events; verify no orphan reservations after N failed sagas; load test for lock contention on reservations.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Local transactions only inside a service — never hold a lock across a network call
- [ ] Outbox for event emission
- [ ] Idempotent everything
- [ ] Saga timeouts with automatic compensation
- [ ] Explicit saga state table
- [ ] Alert on stuck sagas
- [ ] Human-in-the-loop for failed compensations
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Coordinator crash mid-2PC → participants locked until recovery (classic deadlock/blocker); compensation itself fails (refund error) → needs retry/DLQ ("compensate the compensation"); outbox relay down → state committed but events missing → projections drift; duplicate compensation (retry) triggers double refund unless keyed; long-running sagas hold semantic locks (reserved seat) blocking other customers — need timeouts and TTLs.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://learn.microsoft.com/azure/architecture/patterns/saga

**Related topics in this library:** `#19 Saga Pattern`, `#14 Idempotency`, `#15 Message Queues`, `#17 Event-Driven Architecture`, `#30 Sharding` (same-shard writes can be single-phase), `#109 Production Incidents` (stuck sagas are incidents).
