---
topic: 88
title: Cost Optimization
category: F
skill: production-engineering
status: stable
---

# 088 — Cost Optimization

## 1. Topic name and metadata

- **Number:** 88 of 111
- **Title:** Cost Optimization
- **Category:** F — Disaster Recovery and Reliability
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [reliability-recovery.md](../references/reliability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/088-cost-optimization.md`

## 2. What it is

Continuous engineering of spend against value — sizing, pricing models, architecture efficiency, idle waste elimination — while never compromising required reliability.

## 3. Why it exists

Cost is an engineering constraint — budget it explicitly.

## 4. The engineering problem it solves

Cloud bills drift up silently (over-provisioned instances, unmanaged storage, forgotten environments, inefficient queries) while nobody owns the number; cost is a reliability-adjacent discipline, not finance's problem.

## 5. How it works internally

Levers: right-sizing (CPU/memory utilization < 40% for 2 weeks → downsize), pricing models (on-demand → savings plans/RIs/spot for fault-tolerant workers), storage lifecycle (hot→warm→cold tiering, orphan volumes), architecture (cache hot reads, serverless off-peak, spot fleets), data transfer (biggest hidden cost — cross-region egress $0.02-0.09/GB), LLM cost control (token limits, caching, smaller models, prompt trimming). FinOps loop: measure (tag by team/service) → report (showback/chargeback) → optimize (top offenders) → budget alerts. Never cut below the reliability floor — cost decisions use the same decision framework (`#63 SLOs`): budget cuts only capacity that headroom wasn't using, or optimizations with no SLO impact.

## 6. Architecture and design principles

Tagging + cost allocation + FinOps tooling + PR-level cost review.

**Design principles for this category:** Assume failure; test recovery, not just uptime; the cheapest reliability is the one rehearsed before it is needed.

## 7. When to use it

Always — as a continuous review.

## 8. When NOT to use it

Never justifiable; always weigh against SLOs.

**Alternatives:** n/a — this is the process for spending wisely.

<!--END-->

## 9. Implementation strategies

```bash
aws ce get-cost-and-usage --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY --metrics BlendedCost --group-by Type=TAG,Key=service
kubectl top pods -A | sort -k2 -rn   # oversized requests
```

K8s: VPA recommendations; cluster autoscaler; spot node pools for queues; `kubectl idle` analysis.

## 10. Production-grade implementation

**Scenario:** 14 services tagged; $180k/month bill reviewed; findings: two m5.4xlarge at 8% CPU → m5.xlarge (saves $4k); unattached EBS 9TB ($800); NAT gateway cross-AZ chatter ($2k); LLM prompt regression burning $12k → prompt trim + cache (saves $9k); total −$15k/month with zero SLO change.

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

Token unit economics: cache, smaller models for routing, prompt trimming, batch APIs — often −30-70% spend with zero quality loss.

## 15. Security considerations

Security spend is not discretionary — but inflate cost, never cut controls.

## 16. Performance considerations

Failover/DR add replication RTT (sync) or a lag window (async) — choose per data class, not globally.

## 17. Common mistakes

Cutting redundancy first; spot for stateful primaries; no tagging (can't attribute); one-time optimization without recurring review; cost policing by finance alone with no engineering context; "just delete the DB" energy on usage-based features.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `cost_per_request`, `cost_per_1M_tokens`, budget burn % alerts

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Budget alert test; spot interruption drill; quarterly right-size review against p95 latency and SLO (never degrade below SLO); cost regression as PR gate for big changes.

## 21. Deployment considerations

DR/failover changes must be rehearsed: quarterly game days with measured RTO/RPO; record results; update the runbook after every rehearsal.

## 22. Production-readiness checklist

- [ ] Tag everything
- [ ] Monthly top-5 cost review
- [ ] Utilization < 40% → downsize
- [ ] RI/Savings Plans for baseline, spot for burst/batch
- [ ] Storage lifecycle rules
- [ ] Egress minimization
- [ ] Cost as a design review item
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Cost hunting that disables HA (cuts the standby — false economy); cutting cache layer → DB overload → outage (cost "saving" = incident); spot capacity revoked at peak → worker fleet vanishes (use spot only for retry-tolerant queues); ignoring data egress (biggest line item surprise); cutting observability to save 2%; no budget alert → $40k surprise month; optimizations applied once and forgotten (reservations expire).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://aws.amazon.com/economics/
- https://www.finops.org/framework/

**Related topics in this library:** `#63 SLOs`, `#88 Cost Optimization` pairs with `#45 Autoscaling`, `#47 Vertical Scaling`, `#50 Cache Invalidation`, `#90 Serverless Limits` (LLM spend), `#2 Caching`.
