---
topic: 36
title: Optimistic Locking
category: B
skill: production-engineering
status: stable
---

# 036 — Optimistic Locking

## 1. Topic name and metadata

- **Number:** 36 of 111
- **Title:** Optimistic Locking
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/036-optimistic-locking.md`

## 2. What it is

A concurrency control that assumes conflicts are rare: instead of taking a lock first, it reads a version (or timestamp) with the row and rejects the update if the version changed since the read.

## 3. Why it exists

Lost updates on concurrent edits are silent and common.

## 4. The engineering problem it solves

Read-modify-write across a request (fetch → user edits → save) can silently overwrite another user's concurrent edit (last-writer-wins), losing data.

## 5. How it works internally

Add a `version` integer column. Update: `UPDATE orders SET ..., version = version + 1 WHERE id = :id AND version = :seen_version`. Affected rows = 0 → conflict → reload and retry or surface 409. No DB locks held between read and write — great for web request flows. SQLAlchemy: `version_id_col` on the Mapped column; conflict raises `StaleDataError`.

## 6. Architecture and design principles

Between the service layer and Postgres; the check is part of the UPDATE's WHERE clause.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Low-contention writes, long user edits, API-driven updates.

## 8. When NOT to use it

Counters/balances under high contention (lock or atomic SQL); operations with external side effects where retry duplicates work.

**Alternatives:** `#37 Pessimistic Locking`, atomic `SET x = x + 1` expressions, `#38 Distributed Locks`.

## 9. Implementation strategies

```python
from sqlalchemy.orm import Mapped, mapped_column
class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    total: Mapped[int] = mapped_column(Numeric(10, 2))
    version_id: Mapped[int] = mapped_column(version_id_col=True)  # SQLAlchemy auto-increments + checks
```

orraw SQL as above with explicit retry loop (max 3).

## 10. Production-grade implementation

**Scenario:** Collaborative inventory edit: warehouse A and B open the same item; A saves (v3→v4); B's save (based on v3) rejected → 409, UI refreshes, B re-applies → no lost update. Zero locks held during the 4-minute edit session.

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

On `StaleDataError`/0-rows → `HTTP 409 Conflict` with `current_version` + current data so UI can merge; clients retry the mutation.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Not applicable — this concept operates below or beside the LLM layer; it applies to AI systems only indirectly (e.g., via the platform that runs them). Do not force AI-specific machinery here; apply the standard pattern unchanged.

## 15. Security considerations

Optimistic versions leak nothing — enforce on the server, never trust client versions.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Optimistic locking on hot rows (flash-sale counters); version check in app code instead of WHERE (TOCTOU race); swallowing 409s; identical "retry forever" loops.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `optimistic_conflicts_total`, `stale_write_rejections_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest: two concurrent sessions read v1; first writes (→v2); second write must raise/return 0 rows; API-level 409 test; conflict-rate metric assertion.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Use for low-contention, long-edit flows
- [ ] Cap client retry attempts
- [ ] Return the latest version on 409
- [ ] Expose `version` in API payloads
- [ ] Keep transactions short around the UPDATE
- [ ] Metric the conflict rate.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Hot contention → high 409 rate (that's the signal to switch to pessimistic locking or a queue); retry loop infinite without cap; version not incremented (manual SQL forgotten) → check is no-op; conflict resolution pushed to users with no merge help → support burden.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.sqlalchemy.org/en/20/orm/versioning.html

**Related topics in this library:** `#37 Pessimistic Locking`, `#39 Race Conditions`, `#35 Eventual Consistency`, `#14 Idempotency`, `#40 Deadlocks`.
