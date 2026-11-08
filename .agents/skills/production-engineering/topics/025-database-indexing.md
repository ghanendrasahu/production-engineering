---
topic: 25
title: Database Indexing
category: B
skill: production-engineering
status: stable
---

# 025 — Database Indexing

## 1. Topic name and metadata

- **Number:** 25 of 111
- **Title:** Database Indexing
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/025-database-indexing.md`

## 2. What it is

An ordered auxiliary structure (usually a B-tree) that lets the database locate rows without scanning the whole table, at the cost of extra storage and slower writes.

## 3. Why it exists

Full table scans are the universal database bottleneck.

## 4. The engineering problem it solves

Sequential scans collapse at ~1M+ rows: p95 goes seconds, connections exhaust, and the entire service stalls. Missing index is the single most common production database bug.

## 5. How it works internally

PostgreSQL B-tree stores keys sorted with pointers to tuples; lookups are O(log n). The planner uses statistics (`pg_stats`, `ANALYZE`) to estimate selectivity. Composite indexes are used left-to-right (leftmost prefix rule); partial indexes index only a subset (`WHERE active`); covering indexes (`INCLUDE`) serve index-only scans; expression indexes (`lower(email)`) match the query predicate exactly. `EXPLAIN (ANALYZE, BUFFERS)` shows the real plan.

## 6. Architecture and design principles

Between the ORM/query layer and the storage engine; invisible to the application code except through latency. Migrations must create indexes `CONCURRENTLY` in production.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Measured slow queries with full scans on hot paths; join-heavy needs.

## 8. When NOT to use it

Write-heavy tables where index maintenance dominates; tiny tables (<10k rows); columns rarely filtered.

**Alternatives:** materialized views, denormalization, read replicas, `#31 Partitioning`.

## 9. Implementation strategies

```sql
CREATE INDEX CONCURRENTLY ix_orders_user ON orders (user_id);
CREATE INDEX CONCURRENTLY ix_orders_status_created ON orders (status, created_at DESC);
CREATE INDEX CONCURRENTLY ix_users_email_lower ON users (lower(email));
CREATE INDEX CONCURRENTLY ix_active ON orders (user_id) WHERE status = 'active';
CREATE INDEX CONCURRENTLY ix_covering ON orders (user_id) INCLUDE (total, created_at);
```

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 20;
```

## 10. Production-grade implementation

**Scenario:** `orders` 120M rows, p95 1.8s → after composite index (user_id, created_at DESC): p95 4ms. Index build on live traffic used `CONCURRENTLY` — zero downtime.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

```python
class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    __table_args__ = (Index("ix_orders_status_created", "status", text("created_at DESC")),)
```

## 12. FastAPI integration where relevant

Add `index=True` on columns used in `WHERE`/`JOIN`/`ORDER BY`; paginate deep pages with keyset (`WHERE id > :last ORDER BY id LIMIT 50`) not `OFFSET`.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

pgvector: HNSW on (embedding vector(1536)) — recall vs build cost; version the index with the embedding model name.

## 15. Security considerations

Parameters always; app DB role without DDL; CONNECTION-level statement_timeout.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Index every column; index low-cardinality columns; forgetting leftmost prefix; `SELECT *` defeating covering index; creating without CONCURRENTLY; no maintenance plan (bloat).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `seq_scans_total`, index hit ratio, `pg_stat_user_indexes` usage

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

`EXPLAIN (ANALYZE, BUFFERS)` on query in CI against a seeded subset; pg_stat_statements before/after; integration test asserting plan does not seq-scan the hot table; load test p95 improvement.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Index predicates and join keys
- [ ] Composite in selectivity order (most selective first, or equality-then-range)
- [ ] `INCLUDE` to cover
- [ ] `CONCURRENTLY` always in production
- [ ] Drop unused indexes (quarterly `pg_stat_user_indexes` review)
- [ ] Monitor bloat
- [ ] Verify with `EXPLAIN` before and after.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Index never chosen (statistics stale → `ANALYZE`; or `OR` instead of `IN`); write amplification (every INSERT/UPDATE maintains all indexes — a table with 8 indexes updates 8x); unused indexes bloating storage; index on low-selectivity boolean; partial index condition not matching the query.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/indexes.html
- https://www.postgresql.org/docs/current/index-b-tree.html

**Related topics in this library:** `#26 Query Optimization`, `#28 Connection Pooling`, `#29 Read Replicas`, `#31 Partitioning`, `#26` tuning and `#81 Database Migrations` (CONCURRENT builds).
