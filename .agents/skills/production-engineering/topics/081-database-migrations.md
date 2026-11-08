---
topic: 81
title: Database Migrations
category: E
skill: production-engineering
status: stable
---

# 081 — Database Migrations

## 1. Topic name and metadata

- **Number:** 81 of 111
- **Title:** Database Migrations
- **Category:** E — Database Lifecycle
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/081-database-migrations.md`

## 2. What it is

Version-controlled, sequential, reversible scripts that evolve the schema in lockstep with the code — the database's own change history.

## 3. Why it exists

Schema changes are code; they need version control and review.

## 4. The engineering problem it solves

Ad hoc `ALTER TABLE` in production causes drift, failed deploys, and unrecoverable split states between code and schema.

## 5. How it works internally

A ledger table (`alembic_version` / `schema_migrations`) records applied revisions. Each migration has upgrade + downgrade (or is marked irreversible). Dependency chain enforced by revision ids. Safe migrations: **expand → migrate data → contract** (add nullable column → backfill → add constraint in a later deploy). Locking: `CONCURRENTLY` for indexes, batch tools (gh-ost, pg_repack) for big tables, avoiding long-held exclusive locks.

## 6. Architecture and design principles

Alembic migrations run as part of CI/CD (or a pre-deploy Job), not by hand; app code expects schema at revision N.

**Design principles for this category:** Schema changes are code — reviewed, reversible, ordered; never mutate what you cannot roll back.

## 7. When to use it

Always.

## 8. When NOT to use it

Never applicable — every schema change needs one.

**Alternatives:** none; manual DDL is the anti-pattern this replaces.

## 9. Implementation strategies

```bash
alembic revision -m "add orders.status" --autogenerate
alembic upgrade head
alembic downgrade -1
# big table:
CREATE INDEX CONCURRENTLY ix_big ON big_table (col);   -- manual, non-transactional
```

```python
def upgrade():
    op.add_column("orders", sa.Column("status", sa.String(20), nullable=True))
    op.create_index("ix_orders_status", "orders", ["status"], postgresql_concurrently=True)
```

## 10. Production-grade implementation

**Scenario:** 90-day fleet migration: expand (add nullable), backfill 120M rows in batches of 5k with pg_sleep throttle, switch reads behind `status IS NOT NULL` flag, deploy contract (NOT NULL after 2 weeks). Zero downtime.

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

Not applicable — this concept is infrastructure/protocol level; there is no FastAPI-specific surface. Apply it underneath FastAPI through configuration, middleware, or dependencies (section 9). Do not force a fake integration.

## 13. Distributed-system considerations

Fleet-wide schema change is a distributed deployment problem: expand/contract serves two code versions from one database with zero downtime.

## 14. AI/ML/LLM application examples where relevant

Prompt template and eval datasets are schema — version them like migrations; breaking 'schema' = prompt rewrite.

## 15. Security considerations

Migration role separate; reviews; no secrets in migrations; backup first.

## 16. Performance considerations

Migration speed vs safety: batched backfills are slower but safe; big-bang DDL is fast and outages everything.

## 17. Common mistakes

One giant migration per release; NOT NULL without default on huge table (full rewrite + lock); editing merged migration files; dropping column before code stops reading it; migrations as deploy side effect without readiness gates.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `migration_failures_total`, `alembic_version` drift alerts

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Migrate up/down on empty DB in CI; up/down on a production-like data copy; concurrency test (migration while traffic runs); rollback drill; schema-drift check (`alembic check`).

## 21. Deployment considerations

Migrations run through the pipeline as pre-deploy jobs with readiness gates — never by hand in production; rollback plan required for any destructive DDL.

## 22. Production-readiness checklist

- [ ] Small, frequent, reversible migrations
- [ ] Expand/contract for breaking changes
- [ ] Backup before contract
- [ ] CONCURRENTLY indexes
- [ ] Backfill in bounded batches with throttling
- [ ] CI runs migrations against disposable DB
- [ ] Never edit applied migrations — write a new one
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Migration holds AccessExclusiveLock on big table → all queries queue → timeout storm → deploy rollback (fix: batched/concurrent); irreversible data-loss migration deployed without backup; migration graph diverges between environments; partial failure leaves half-backfilled data with ambiguous state; autogenerate producing wrong ops (manual review required).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://alembic.sqlalchemy.org/en/latest/
- https://github.com/ankane/strong_migrations

**Related topics in this library:** `#82 Schema Versioning`, `#25 Database Indexing`, `#55 Rollbacks`, `#6 CI/CD`, `#52 Blue-Green Deployment`, `#81 Database Migrations`.
