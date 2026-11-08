---
topic: 40
title: Deadlocks
category: B
skill: production-engineering
status: stable
---

# 040 — Deadlocks

## 1. Topic name and metadata

- **Number:** 40 of 111
- **Title:** Deadlocks
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/040-deadlocks.md`

## 2. What it is

A cycle of transactions each waiting for a lock held by another; none can proceed; the database detects the cycle and aborts one victim.

## 3. Why it exists

Lock cycles stall transactions; detect and design them away.

## 4. The engineering problem it solves

Under concurrency, deadlocks spike during contention-heavy flows and show up as intermittent 40P01 errors that look random and are maddening to reproduce.

## 5. How it works internally

Each transaction acquires row/page locks; lock manager detects wait cycles (waits-for graph) → aborts the cheapest victim → client sees `deadlock detected`. Prevention: consistent lock acquisition order (always lock rows in ascending ID), short transactions, fewer locks per transaction, `NOWAIT`, `SKIP LOCKED`, avoiding user think time inside transactions. Retry the victim transaction — deadlocks are expected under concurrency.

## 6. Architecture and design principles

Inside the transaction manager; invisible to the app except error code `40P01` (Postgres).

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Diagnosis + prevention — always watch for it.

## 8. When NOT to use it

You don't have consistent ordering anywhere (fix design first).

**Alternatives:** optimistic locking, single-statement atomic updates, `SKIP LOCKED`, queue-based single-writer serialization.

## 9. Implementation strategies

```python
from tenacity import retry, stop_after_attempt, wait_random
@retry(stop=stop_after_attempt(3), wait=wait_random(0.05, 0.3), retry=retry_if_exception(is_deadlock))
def transfer_funds(a, b, amount):
    with session.begin():
        x, y = sorted([a, b])          # consistent lock order — prevents most deadlocks
        lock_rows(x); lock_rows(y)
        debit(x); credit(y)
```

## 10. Production-grade implementation

**Scenario:** Nightly bulk reconcile deadlocking against day-time order writes every run; reordered to lock by `order_id` ascending; deadlocks 40/day → 0.

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

Retry-on-deadlock decorator in the service layer; return generic 503 after 3 victims with correlation id logged.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Agent swarms on shared tables deadlock — deterministic lock order or queue-based serialization.

## 15. Security considerations

Victim retry must re-run authorization, never inherit prior authorization.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Blanket retry without ordering fix; transactions spanning HTTP calls; `SELECT FOR UPDATE` then user input; table locks; ignoring `log_lock_waits`.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `deadlocks_total{query}`, avg wait time, `log_lock_waits` events

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest forcing opposite-order transactions with threads; assert one aborts and retry succeeds; load test the suspected query under contention; chaos test killing a victim mid-cycle.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Lock in one deterministic global order
- [ ] Keep transactions < 100ms
- [ ] Index predicates so locks are precise
- [ ] Log lock waits (`log_lock_waits=on`)
- [ ] Retry victim with jitter
- [ ] Monitor deadlock rate per query — top offender tells you the design flaw
- [ ] Prefer `SKIP LOCKED` in workers.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Two transactions locking accounts A,B vs B,A in opposite order (classic); `UPDATE ... WHERE status='x'` touching unindexed predicate → row lock escalation; long transaction holding locks blocks everyone; retrying victim without fixing order re-deadlocks; pool full of deadlock victims.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/explicit-locking.html
- https://dev.mysql.com/doc/refman/8.0/en/innodb-deadlocks.html

**Related topics in this library:** `#37 Pessimistic Locking`, `#39 Race Conditions`, `#36 Optimistic Locking`, `#28 Connection Pooling`, `#12 Retries` (victim retry).
