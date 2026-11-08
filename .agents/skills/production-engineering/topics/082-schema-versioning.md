---
topic: 82
title: Schema Versioning
category: E
skill: production-engineering
status: stable
---

# 082 — Schema Versioning

## 1. Topic name and metadata

- **Number:** 82 of 111
- **Title:** Schema Versioning
- **Category:** E — Database Lifecycle
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/082-schema-versioning.md`

## 2. What it is

Tracking which schema version each environment and application instance expects, and enforcing that code and schema evolve together safely.

## 3. Why it exists

Code and schema must evolve together or the deploy lies.

## 4. The engineering problem it solves

Code at rev N+1 against schema at N (missing column) crashes at runtime; rolling deploys need compatibility windows where two code versions coexist on one schema.

## 5. How it works internally

`alembic_version` table is the source of truth. Rolling deploy compatibility rule: for any deploy, N and N+1 code must both run against the current schema (expand-migrate-contract). Backward-compat window: keep old columns until all fleet is on new code (track rollout). Also version the *data contract* for events (schema registry) — same idea, for messages.

## 6. Architecture and design principles

Migration ledger + deployment pipeline ordering (migrate → deploy app) + compatibility checklist in PR template.

**Design principles for this category:** Schema changes are code — reviewed, reversible, ordered; never mutate what you cannot roll back.

## 7. When to use it

Always.

## 8. When NOT to use it

N/a.

**Alternatives:** schema registry for messages, contract tests against live schema.

<!--END-->

## 9. Implementation strategies

`alembic current`, `alembic upgrade head` in CI pre-deploy job; app startup assertion: compare `alembic_version` with code's expected revision; refuse to boot on mismatch (fail fast).

## 10. Production-grade implementation

**Scenario:** `orders.status` added nullable at rev 041; blue-green deploy; 100% fleet on 041 code for 48h; rev 042 adds NOT NULL; rollout; zero errors. `alembic check` in CI fails PRs that drifted models from migrations.

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

Prompt v3 vs model v4 combinations are undocumented migrations — track and CI-check.

## 15. Security considerations

CI drift check — envs must match code rev; no silent authz gaps.

## 16. Performance considerations

Migration speed vs safety: batched backfills are slower but safe; big-bang DDL is fast and outages everything.

## 17. Common mistakes

"Deploy and migrate together and hope"; deleting columns in same release as code change; one-way-only migrations with no tested downgrade; migration scripts not in the same PR as code.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `schema_drift_detected_total`, revision mismatch gauges

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

CI: migrate → boot app → smoke test; two-version coexistence test (old code against new schema); `alembic check`; drift audit across envs.

## 21. Deployment considerations

Migrations run through the pipeline as pre-deploy jobs with readiness gates — never by hand in production; rollback plan required for any destructive DDL.

## 22. Production-readiness checklist

- [ ] Fail-fast startup check
- [ ] Expand-migrate-contract always
- [ ] No editing applied revisions
- [ ] PR checklist "migrations backwards compatible"
- [ ] Registry for event schemas alongside DB
- [ ] Verify `alembic check` in CI
- [ ] Document compatibility windows.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Deploy new code before migration completes → 500s; downgrade path broken → can't roll back code without breaking schema; hotfix migration edited in place → environments diverge silently; multiple parallel branches create conflicting revisions; schema-aware feature flags forgotten after split-brain deploy.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://alembic.sqlalchemy.org/en/latest/cookbook.html

**Related topics in this library:** `#81 Database Migrations`, `#51 Feature Flags`, `#55 Rollbacks`, `#102 API Versioning` (same philosophy), `#6 CI/CD`.
