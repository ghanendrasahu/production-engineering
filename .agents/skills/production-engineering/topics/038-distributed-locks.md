---
topic: 38
title: Distributed Locks
category: B
skill: production-engineering
status: stable
---

# 038 — Distributed Locks

## 1. Topic name and metadata

- **Number:** 38 of 111
- **Title:** Distributed Locks
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [distributed-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/038-distributed-locks.md`

## 2. What it is

A mutual-exclusion mechanism spanning multiple processes/nodes — exactly one holder across the fleet — typically implemented on Redis, etcd, or a database.

## 3. Why it exists

Multiple machines must agree who edits the shared resource.

## 4. The engineering problem it solves

When correctness requires one-and-only-one actor across machines (billing job, inventory leader, outbound webhook sender), in-process locks do nothing.

## 5. How it works internally

Redis `SET key uuid NX PX ttl` acquire; heartbeat renewal via Lua compare-and-PEXPIRE; release via Lua compare-and-del (only delete if we hold the token). Redlock (multiple Redis nodes) is controversial — Martin Kleppmann showed timing assumptions break it; the robust answer is a consensus-backed lease (etcd) with a **fencing token**. Database advisory locks (`pg_advisory_lock`) work within Postgres. Critical requirements: (1) TTL — holder may die silently; (2) unique token per acquisition; (3) TTL > worst-case critical section; (4) fencing at the protected resource.

## 6. Architecture and design principles

App nodes → shared lock store (Redis/etcd/Postgres advisory) → protected resource (DB, external API). The lock only coordinates; correctness still requires the resource to validate the fencing token.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Cross-node single-writer for a short critical section (job dedup, migration gate).

## 8. When NOT to use it

Hot path with high contention (queue/serialize instead); you need strict correctness — then use consensus + fencing (etcd) not Redis Redlock; single process (asyncio.Lock is enough).

**Alternatives:** DB row locks (`#37 Pessimistic Locking`), unique constraints, `SKIP LOCKED` queue, single-leader scheduling.

## 9. Implementation strategies

```python
import time, uuid, redis
r = redis.Redis()

def with_lock(key, ttl_ms=10000, tries=3):
    token = uuid.uuid4().hex
    for _ in range(tries):
        if r.set(f"lock:{key}", token, nx=True, px=ttl_ms):
            try:
                yield token                      # critical section
            finally:
                r.eval("if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
                       1, f"lock:{key}", token)
            return
        time.sleep(0.1 * (tries + 1))
```

Celery: `lock = redis.lock("nightly-close", timeout=3600, blocking_timeout=0)`; DB: `SELECT pg_try_advisory_lock(42)`.

## 10. Production-grade implementation

**Scenario:** 3 replicas of the invoice-email sender before a Black Friday deploy; Redis lock with 30s TTL + fencing column `sent_by_token` in the `invoices` table guarantees exactly one email even if a GC pause runs the holder past TTL; the surviving lock holder's fencing token is honored only if higher.

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

Dependency that acquires `lock:endpoint-name` for a guarded admin operation; returns 409 if not acquired; the guarded action then carries a fencing token to the DB.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

GPU fleet leader election for batch jobs; fencing tokens into the job table — zombie schedulers double GPU spend.

## 15. Security considerations

Locks are a DoS lever — narrow scope; timeouts; no cross-service critical sections.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

`SETNX` without TTL (deadlock forever); unlocking without compare-and-delete; locks without fencing as a correctness guarantee; TTL == critical section duration exactly; using a lock for rate limiting; lock contention on the hot path (queue instead).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `lock_hold_seconds`, `lock_contention_total`, fencing rejections

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Pause-holder test (monkeypatch sleep > TTL) asserting fencing rejects stale writes; concurrent acquirer test; lock-store-down drill (fail-open vs fail-closed documented); verify unlock releases only own lock.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] TTL > critical section with margin
- [ ] Renew at TTL/2 via dedicated heartbeat
- [ ] Fencing tokens on the protected write
- [ ] Unique tokens
- [ ] Narrow-scope keys per resource
- [ ] Handle acquisition failure explicitly (409/skip)
- [ ] Monitor lock hold time and contention
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Lock holder GC-pauses past TTL; new holder starts; both "hold" — without fencing, both act on shared state; lock acquired but renewal thread starved (same loop as work) → lease expires mid-task; unlock by simple DEL without compare → unlocks someone else's lock; Redis down → lock service down → decide fail-open (split-brain) or fail-closed (unavailability) deliberately; lock scope too broad (whole job vs the single record) → unnecessary serialization.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://redis.io/docs/manual/patterns/distributed-locks/
- https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html

**Related topics in this library:** `#33 Leader Election`, `#21 Cron Jobs`, `#12 Retries`, `#14 Idempotency`, `#39 Race Conditions`, `#96 Clock Skew` (TTLs assume bounded error).
