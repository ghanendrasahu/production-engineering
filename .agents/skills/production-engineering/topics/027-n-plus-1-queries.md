---
topic: 27
title: N+1 Queries
category: B
skill: production-engineering
status: stable
---

# 027 — N+1 Queries

## 1. Topic name and metadata

- **Number:** 27 of 111
- **Title:** N+1 Queries
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/027-n-plus-1-queries.md`

## 2. What it is

Issuing one query for a parent list and then one additional query per row for the children — N+1 round trips instead of one.

## 3. Why it exists

The classic ORM trap: one list endpoint becomes 1000 queries.

## 4. The engineering problem it solves

Endpoints that feel fine locally at 20 rows issue 1001 queries for 1000 rows in production; latency scales linearly with page size and saturates the connection pool.

## 5. How it works internally

ORM lazy loading emits a query per attribute access. Fix strategies: eager loading (JOIN or batched `IN (...)` "selectin" style), joined load, or explicit two queries. Batching selects by key is usually optimum (no duplicate rows). In SQLAlchemy 2.0: `selectinload` for collections, `joinedload` for many-to-one.

## 6. Architecture and design principles

Between route handler and database; invisible until measured with query logging or counting.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Use eager loading when: serializing nested relations.

## 8. When NOT to use it

Children are never touched (don't load); payload too large (paginate children separately or use streaming).

**Alternatives:** explicit two-step queries, GraphQL dataloaders, views.

## 9. Implementation strategies

```python
from sqlalchemy.orm import selectinload
orders = session.scalars(
    select(Order).options(selectinload(Order.items)).limit(100)
).all()          # 2 queries total, regardless of len(orders)
```

Or raw: `SELECT * FROM items WHERE order_id IN (:ids)` after fetching orders.

## 10. Production-grade implementation

**Scenario:** `/api/orders` listing 200 orders → 201 queries → 900ms; with selectinload: 2 queries, 12ms. Found by `log_min_duration_statement=0` showing 200 identical `SELECT * FROM items WHERE order_id=?`.

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

Serialization helper taking `selectinload(Order.items)` option; test with `assert db.query_count == 2` using pytest + event listener on `before_cursor_execute` or `SQLALCHEMY_ECHO`.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

RAG is an N+1 trap: retrieve once (top-k), never per-chunk queries — batch embedding calls (32-128).

## 15. Security considerations

Page-size caps are anti-DoS — unbounded pages are unbounded memory.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Lazy loading "because it's convenient"; `len()` on a lazy collection triggering full load; 5 nested loops of lazy relations; hiding N+1 with a cache.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `queries_per_endpoint`, query-count assertion failures in tests

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest with `before_cursor_execute` listener counting statements per request — assert ≤ expected; CI at realistic page size; profile endpoint in staging with echo=True.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Default to selectinload for collections, joinedload for many-to-one
- [ ] Count queries in tests
- [ ] Log query counts per request in dev
- [ ] Cap page sizes
- [ ] Code review rule: no attribute access in loops without eager loading
- [ ] Use `contains_eager` for custom filters.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Lazy-load in async context (MissingGreenlet) causing exceptions; N+1 reappearing via a new nested serialization field; join-eager-load Cartesian explosion (parent rows duplicated ×children) — prefer selectin; pagination applied after join (limit applies to duplicated rows); default relationships silently lazy in new code.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.sqlalchemy.org/en/20/orm/loading_relationships.html

**Related topics in this library:** `#26 Query Optimization`, `#25 Database Indexing`, `#28 Connection Pooling`, `#27 N+1 Queries` pairs with `#66 Observability` query tracing.
