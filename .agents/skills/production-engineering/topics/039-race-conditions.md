---
topic: 39
title: Race Conditions
category: B
skill: production-engineering
status: stable
---

# 039 — Race Conditions

## 1. Topic name and metadata

- **Number:** 39 of 111
- **Title:** Race Conditions
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/039-race-conditions.md`

## 2. What it is

A bug class in which the correctness of an operation depends on the interleaving of concurrent execution — outcome varies nondeterministically with scheduling.

## 3. Why it exists

Interleavings decide correctness; ignoring them is corruption by omission.

## 4. The engineering problem it solves

Classic lost-update: two requests read balance 100, both add 50, both write 150 — one 50 vanishes. In production: money, inventory, counters, and file replacements silently corrupt.

## 5. How it works internally

Interleavings: read-modify-write without atomicity; check-then-act across async boundaries; time-of-check vs time-of-use (TOCTOU). Fixes: atomic operations (single SQL statement with math `SET x = x + 1`), transactions with locking, optimistic version checks, compare-and-swap (Redis `WATCH`/Lua, DB serializable), or single-writer serialization.

## 6. Architecture and design principles

Anywhere two execution contexts touch shared mutable state — threads, coroutines, replicas, cron + API.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Always — ask "what if two run at once?" for every write path.

## 8. When NOT to use it

Operation is provably single-threaded and single-process (rare).

**Alternatives:** event-sourced single writer, `#38 Distributed Locks`, serializable isolation (Postgres SSI — heavy).

## 9. Implementation strategies

```sql
UPDATE accounts SET balance = balance + 50 WHERE id = 1;   -- atomic
```

```python
# Redis compare-and-set via Lua (atomic)
lua = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('set',KEYS[1],ARGV[2]) else return 0 end"
```

```python
import asyncio
async with lock:  # asyncio.Lock for single-process; Redis lock across processes
    balance = get(); set(balance + 50)
```

## 10. Production-grade implementation

**Scenario:** Coupon redemption counter: 200 parallel "first 100 users" requests, all read redeemed=99 → all pass → 180 redemptions. Fixed with `UPDATE coupons SET redeemed = redeemed + 1 WHERE code='X' AND redeemed < 100` — affected-rows check enforces the cap.

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

Use `asyncio.Lock` only within one process; for multi-replica use Postgres atomic statement or Redis lock — never `asyncio.Lock` alone as correctness for money.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Agent tool calls run concurrently — check-then-act on budgets races; atomic decrement or serialized wallet row.

## 15. Security considerations

TOCTOU on authz checks — atomic check-and-act or FK constraints; no app-side pre-checks.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

`if not exists: create`; in-memory counters in multi-worker apps; `asyncio.Lock` as distributed correctness; fixing by adding sleep(); relying on single-threaded dev environment.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `integrity_errors_total`, constraint violations, anomaly counters

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest with `threading`/`asyncio.gather` hammering the operation 50x asserting invariant; force interleavings with barriers/monkeypatched sleeps; property test (hypothesis) generating concurrent op sequences; integration test at real concurrency.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Prefer atomic SQL over read-then-write
- [ ] Unique constraints + INSERT ... ON CONFLICT over pre-checks
- [ ] Idempotency keys for client retries
- [ ] Avoid check-then-act between separate round trips
- [ ] Serialize money operations
- [ ] Code review for shared mutable state.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** GET-then-POST double submit (no idempotency); check-then-create violating unique constraint (add unique index and catch IntegrityError instead of pre-check); counters drifting; file "replace" half-written (write temp + atomic rename); test suite passes, production interleaves differently.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://en.wikipedia.org/wiki/Race_condition

**Related topics in this library:** `#36 Optimistic Locking`, `#37 Pessimistic Locking`, `#40 Deadlocks`, `#43 Thread Safety`, `#14 Idempotency`, `#38 Distributed Locks`.
