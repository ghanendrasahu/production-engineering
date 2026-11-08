---
topic: 63
title: SLOs
category: C
skill: production-engineering
status: stable
---

# 063 — SLOs

## 1. Topic name and metadata

- **Number:** 63 of 111
- **Title:** SLOs
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/observability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/063-slos.md`

## 2. What it is

Service Level Objective — the target value of an SLI over a rolling window (e.g., 99.9% of HTTP requests succeed with latency < 300ms, measured monthly); the explicit reliability contract.

## 3. Why it exists

Reliability without a target is a vibe, not an SLO.

## 4. The engineering problem it solves

Without a target, reliability debates are vibes; error budget gives a data-driven policy for balancing velocity vs stability.

## 5. How it works internally

SLO = objective; SLI = measurement; error budget = 1 − SLO over window (99.9% → 43.2 minutes per 30d). Availability SLI: `good events / valid events`. Latency SLI: % of events under threshold. Rolling 30d math. Policy: when budget burns too fast, freeze features and ship reliability work; when budget healthy, ship aggressively. Multi-burn-rate alerts (`#62`) detect fast/slow consumption. Review SLOs quarterly with business.

## 6. Architecture and design principles

SLO definitions (SLI + objective + window + owner) living in an SLO platform (Nobl9/Grafana SLO) or as Prometheus recording rules + dashboards; error budget feeds deploy gates.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Customer-facing production services.

## 8. When NOT to use it

Internal batch-only tooling (use job success metrics, not SLOs).

**Alternatives:** SLAs (legal contract, superset of SLO) for external commitments.

## 9. Implementation strategies

```promql
# SLI: proportion of good requests (fast 5m and slow 6h windows)
1 - (sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])))
```

Weekly review: `error_budget_remaining = SLO - (1 - achieved_SLI)` over 30 days.

## 10. Production-grade implementation

**Scenario:** API SLO 99.95% over 30 days (≤ 21.6 min bad); November: one bad deploy consumed 60% of budget in 40 minutes; feature freeze invoked; team shipped retry/pool fixes; December budget healthy — velocity resumed. Auditors approved; customers noticed nothing.

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

Middleware labels requests; `/slo.json` or Grafana panel shows rolling SLI vs SLO; budget exhausted → CI pipeline blocks feature deploys (gate on remaining budget < 10%).

## 13. Distributed-system considerations

Rollout safety across a fleet: probes, budgets, and automatic rollback are the distributed-systems controls for deployments — a bad pod must be ejected, not tolerated.

## 14. AI/ML/LLM application examples where relevant

SLO on TTFT and task success rate (not uptime) — e.g., 95% of chats start streaming <800ms; 90% tool-call success.

## 15. Security considerations

Count correctness failures in SLOs, not just uptime — silent wrong data is worse than downtime.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Vanity SLOs (100%); uptime-based SLOs ignoring correctness; gaming via cheap checks; no consequence policy; SLOs nobody reviews; counting your own greps.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** error budget remaining; burn rate; SLO compliance %

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Alert drill: burn fast synthetic → page fires; SLI unit checks in CI (expected values from fixture data); budget-remaining dashboard verification; freeze-gate test in deploy pipeline.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] 2-4 SLOs per user journey
- [ ] User-perceived metrics
- [ ] Rolling 28-30d
- [ ] Multi-window burn alerts
- [ ] Error-budget freeze policy pre-agreed with product
- [ ] Quarterly review vs real incidents
- [ ] Include latency + availability
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** SLO set equal to current best ("99.99% because we once saw it") → impossible, permanent freeze; measuring success by uptime % rather than user-visible errors; SLI includes internal health checks (gaming own SLO); window too short/noisy; no owner; no burn-rate alerts → budget gone before anyone knows; SLO on everything (dilutes focus to 2-4 critical services).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://sre.google/sre-book/service-level-objectives/
- https://www.nobl9.com/

**Related topics in this library:** `#64 SLIs`, `#65 Error Budgets`, `#62 Alerts`, `#93 P99 Latency`, `#66 Observability`, `#110 On-Call`.
