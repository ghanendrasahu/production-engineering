---
topic: 37
title: Pessimistic Locking
category: B
skill: production-engineering
status: stable
---

# 037 — Pessimistic Locking

## 1. Topic name and metadata

- **Number:** 37 of 111
- **Title:** Pessimistic Locking
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/037-pessimistic-locking.md`

## 2. What it is

A concurrency control that takes a row-level lock before reading/writing so no other transaction can modify (or depending on level, read) the row until commit.

## 3. Why it exists

Hot rows need mutual exclusion, not optimism.

## 4. The engineering problem it solves

When conflicts are *likely* (inventory decrement on hot SKU), optimistic retry loops thrash; you need mutual exclusion to keep correctness simple.

## 5. How it works internally

`SELECT ... FOR UPDATE` takes an exclusive row lock; `FOR UPDATE SKIP LOCKED` skips locked rows (classic queue pattern); `NOWAIT` errors instead of waiting. Locks held until transaction commit/rollback. Postgres also has predicate locks for serializable isolation. Deadlocks possible — keep lock order and transaction length small.

## 6. Architecture and design principles

Within one DB transaction, wrapping the critical section; the transaction is the lock boundary.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

High-contention rows with critical invariants (stock, balances); queue consumers.

## 8. When NOT to use it

Long user edit flows (optimistic wins); cross-service consistency (use `#38 Distributed Locks` or saga).

**Alternatives:** atomic single-statement updates, `#36 Optimistic Locking`, application-level semaphore via Redis.

## 9. Implementation strategies

```sql
BEGIN;
SELECT id, stock FROM items WHERE id = 42 FOR UPDATE;   -- blocks concurrent decrementors
UPDATE items SET stock = stock - 1 WHERE id = 42 AND stock >= 1;
COMMIT;
```

Queue pattern: `SELECT * FROM jobs WHERE state='pending' ORDER BY id LIMIT 10 FOR UPDATE SKIP LOCKED;`

```python
job = session.scalar(select(Job).where(Job.state == "pending")
                     .order_by(Job.id).with_for_update(skip_locked=True).limit(1))
```

## 10. Production-grade implementation

**Scenario:** Flash sale: 5000 concurrent checkouts on SKU with 100 units; FOR UPDATE serializes decrements; last 4900 get 409/sold-out cleanly — zero negative stock, zero oversell. p95 checkout 240ms.

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

Checkout: `with session.begin(): item = locked_select(...); if item.stock < qty: raise 409` — entire read+write in one request transaction.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Saga-style reservation of GPU slots for premium tiers: row lock on slot table; auto-release on timeout.

## 15. Security considerations

Keep critical sections <100ms — long locks are privilege-escalation windows under contention.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

SELECT FOR UPDATE without WHERE; locks around user think-time; entire endpoint in one giant transaction; ignoring deadlock victims; locking whole table (LOCK TABLE) to fix a bug.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `lock_wait_seconds`, deadlock victim count, `FOR UPDATE` hold time

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest: spawn two transactions, assert second blocks until first commits; deadlock-injection test with reversed lock order; assert `SKIP LOCKED` consumer never double-processes; load test hot-row decrement for invariants (stock never < 0).

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Lock the narrowest row set
- [ ] Keep transactions < 100ms
- [ ] Consistent lock ordering (by ID)
- [ ] Handle deadlock victim (retry the transaction)
- [ ] SKIP LOCKED for job queues
- [ ] Never call external services inside a lock transaction
- [ ] Monitor lock wait time (`pg_stat_activity.wait_event`).
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Lock held over network/LLM call inside transaction → pool exhaustion and 30s queueing; lock order inversion across tables → deadlock; long transaction blocks all writers on hot rows; forgetting WHERE clause locks whole table via predicate range; NOWAIT errors treated as 500s instead of 409.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/sql-select.html#SQL-SELECT-FOR-UPDATE-OF

**Related topics in this library:** `#36 Optimistic Locking`, `#40 Deadlocks`, `#39 Race Conditions`, `#28 Connection Pooling`, `#38 Distributed Locks` (lock across services).
