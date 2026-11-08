---
topic: 26
title: Query Optimization
category: B
skill: production-engineering
status: stable
---

# 026 — Query Optimization

## 1. Topic name and metadata

- **Number:** 26 of 111
- **Title:** Query Optimization
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/026-query-optimization.md`

## 2. What it is

The discipline of shaping queries, schemas, and plans to minimize database work per request — read plans, remove waste, and verify with measurements.

## 3. Why it exists

Query cost must be measured and managed, not guessed.

## 4. The engineering problem it solves

Slow queries don't just feel bad; they hold locks, exhaust pools, and multiply under load — one bad query can be a whole-incident root cause.

## 5. How it works internally

Planner costs plans (I/O + CPU) using statistics; chosen plan depends on row estimates (`rows=`, `cost=`). Analyzing `EXPLAIN`: seq scan vs index scan, nested loop vs hash join, sort spilling to disk, estimate vs actual mismatch → stale stats or correlated predicates. Fixes: better indexes, query rewrite, `ANALYZE`, join order, join_collapse_limit, work_mem tuning for sorts, `pg_stat_statements` to find top offenders.

## 6. Architecture and design principles

Database engine + your query layer; optimization feedback loop: observe (pg_stat_statements/APM) → hypothesize → rewrite → verify.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Slow queries identified by measurement.

## 8. When NOT to use it

You don't have pg_stat_statements or EXPLAIN — set them up first.

**Alternatives:** caching the expensive result, materialized views, denormalization, OLAP offload.

## 9. Implementation strategies

```sql
SELECT query, mean_exec_time, calls FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20;
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;   -- look at actual time vs cost, buffers hit/read
SET work_mem = '64MB';  -- for a sort/hash spill in that session
ANALYZE table_name;
```

SQLAlchemy: `.options(selectinload(...))`, explicit joins; never `SELECT *`.

## 10. Production-grade implementation

**Scenario:** Report query at 8s (nested loop over 3M rows); estimate off 100x due to stale stats → `ANALYZE` + composite index + replacing `NOT IN (subquery with NULLs)` with `NOT EXISTS` → 80ms.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

```python
orders = session.scalars(
    select(Order).where(Order.status == "paid").order_by(Order.created_at.desc()).limit(50)
).all()
```

## 12. FastAPI integration where relevant

Debug toolbar / `SQLALCHEMY_ECHO=1` locally; production uses pg_stat_statements + slow-query log (`log_min_duration_statement=200`); endpoint timeouts set per route.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Hybrid retrieval (dense + BM25) + reranker; measure recall@k against exact search — don't trust defaults.

## 15. Security considerations

Restrict EXPLAIN in prod to ops roles — it exposes schema and data shapes.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Premature micro-tuning without stats; "index everything"; fixing one literal query while the same N+1 exists elsewhere; OFFSET pagination over 100k pages; assuming the ORM generates good SQL.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `pg_stat_statements` mean/p95 per query, plan flips

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

EXPLAIN diff before/after in PR description; CI seed at 1M rows; regression test asserting no seq scan on `orders` for the endpoint query; load test.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Measure first (`pg_stat_statements`)
- [ ] Hypothesis → change → measure
- [ ] Keep statistics fresh (autovacuum)
- [ ] Index for the query, not in general
- [ ] Set slow-query logging
- [ ] Pagination by keyset
- [ ] Avoid correlated subqueries
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Optimizing by average hides p95 (one plan flip once in a while); index added but unused (planner still seq-scans due to stats); cache hiding query regressions until cache expires; `work_mem` raised globally → OOM under concurrency; the "fix" works at 10k rows, breaks at 10M.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/using-explain.html
- https://www.postgresql.org/docs/current/sql-explain.html

**Related topics in this library:** `#25 Database Indexing`, `#27 N+1 Queries`, `#28 Connection Pooling`, `#29 Read Replicas`, `#93 P99 Latency`.
