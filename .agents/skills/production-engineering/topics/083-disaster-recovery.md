---
topic: 83
title: Disaster Recovery
category: F
skill: production-engineering
status: stable
---

# 083 — Disaster Recovery

## 1. Topic name and metadata

- **Number:** 83 of 111
- **Title:** Disaster Recovery
- **Category:** F — Disaster Recovery and Reliability
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [reliability-recovery.md](../references/reliability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/083-disaster-recovery.md`

## 2. What it is

The set of policies, runbooks, and infrastructure that restore service after catastrophic events (region loss, data corruption, ransomware, mass accidental deletion); measured by **RPO** (acceptable data loss) and **RTO** (acceptable downtime).

## 3. Why it exists

Improvised recovery is how outages become catastrophes.

## 4. The engineering problem it solves

Without a plan, recovery is improvised under maximum stress — the exact conditions guaranteeing mistakes; audits, contracts, and reality all demand tested recovery.

## 5. How it works internally

Tiers: backup-only (RPO hours/RTO hours), pilot light (core infra always on elsewhere, scale up on disaster), warm standby (scaled-down full system, minutes RPO), multi-site active-active (near-zero). The plan: inventory critical systems, define RPO/RTO per system, codify recovery as runbooks, automate via Terraform/Ansible, **test quarterly** by failing over for real. DR covers both infrastructure and data; data recovery alone is meaningless if you can't redeploy apps.

## 6. Architecture and design principles

Standby region/account; replicated data; IaC for full redeploy; DNS/traffic manager for cutover; comms plan; decision tree (declare disaster vs wait).

**Design principles for this category:** Assume failure; test recovery, not just uptime; the cheapest reliability is the one rehearsed before it is needed.

## 7. When to use it

Any production system with business continuity requirements.

## 8. When NOT to use it

Dev/sandbox.

**Alternatives:** none — but depth scales with RPO/RTO: pilot light for most, active-active only for strict RTO≈0 business cases.

## 9. Implementation strategies

```
RPO ≤ 5 min  → synchronous replication (#32) or async with lag alert < 5min
RTO ≤ 1 h    → warm standby + IaC deploy + automated smoke tests
DR drill: quarterly: destroy staging region → redeploy → verify RTO/RPO measured
```

## 10. Production-grade implementation

**Scenario:** Fintech: primary us-east-1, warm standby eu-west-1 (10% capacity, async replica 30s lag); quarterly drill: full cutover in 47 minutes, measured RPO 25s, RTO 47min — plan validated, audit passed; real event in 2025 (regional S3 outage) was cutover in 32 minutes with zero customer data loss.

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

DR is inherently distributed: replication links, region failover, and cross-region consistency decide whether your 'HA' survives the disaster or just survives the drill.

## 14. AI/ML/LLM application examples where relevant

Back up the vector DB and eval datasets; DR plans must include re-indexing runbooks (hours, not minutes).

## 15. Security considerations

Backups/DR copies need the same KMS/IAM hygiene as prod.

## 16. Performance considerations

Failover/DR add replication RTT (sync) or a lag window (async) — choose per data class, not globally.

## 17. Common mistakes

Backups-only plan sold as DR; DR region never started up; RPO/RTO fiction; manual steps in runbooks; drills skipped ("too costly" — cost of disaster is unbounded); DR plan covers infra not data validation.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `drill_rto_seconds`, `drill_rpo_seconds`, restore success rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Quarterly destroy-region drill with measured RTO/RPO; restore-backup drill; comms drill; data-integrity verification post-restore; runbook review by fresh engineer; audit score.

## 21. Deployment considerations

DR/failover changes must be rehearsed: quarterly game days with measured RTO/RPO; record results; update the runbook after every rehearsal.

## 22. Production-readiness checklist

- [ ] RPO/RTO per system, agreed with business
- [ ] IaC reproduces everything
- [ ] Quarterly measured drills
- [ ] Automated smoke verification
- [ ] Data replication lag alerting
- [ ] Cross-region secrets + registry replication
- [ ] Runbook tested by people who weren't in the room
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Backups exist but restoring took 6 hours (never rehearsed); RPO assumed 0 but replication async; DNS TTL 300s delaying cutover (use health-checked global accelerator instead); standby region drifted (config ≠ prod, different instance types); secrets not available in DR region; single person knows the runbook; "DR region" behind same control plane (us-east-1 etcd failure takes both).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://sre.google/sre-book/data-integrity/
- https://www.aws.amazon.com/disaster-recovery/

**Related topics in this library:** `#84 Backups`, `#85 Failover`, `#86 Multi-Region Deployment`, `#32 Replication`, `#87 Chaos Engineering`, `#111 Postmortems`.
