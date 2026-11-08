---
topic: 65
title: Error Budgets
category: C
skill: production-engineering
status: stable
---

# 065 — Error Budgets

## 1. Topic name and metadata

- **Number:** 65 of 111
- **Title:** Error Budgets
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/observability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/065-error-budgets.md`

## 2. What it is

The allowed unreliability derived from an SLO (1 − SLO) over the window — e.g., 43.2 min/30d at 99.9% — managed as a resource to spend on risk, not a metric to mourn.

## 3. Why it exists

An error budget converts speed vs stability into policy.

## 4. The engineering problem it solves

"How much change is safe?" has no objective answer without a budget; error budgets turn that argument into policy and end the velocitist-vs-stability stalemate.

## 5. How it works internally

Budget remaining = SLO% − actual bad% (over rolling window). Burn rate = consumption speed vs steady state (1x = exactly spends budget over window). Policies: burn > 2x → alert; > 14.4x fast burn → page + freeze; budget exhausted → feature deploys halt, reliability work mandated — a negotiated, pre-agreed policy, not a panic. Multi-window alerting avoids noise from single blips.

## 6. Architecture and design principles

SLO platform/recording rules → burn-rate alerts → deploy gate (check remaining budget) → release policy.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

You have SLOs.

## 8. When NOT to use it

No SLO maturity (don't start with budgets before SLIs exist).

**Alternatives:** simple freeze rules tied to change failure rate; CAB boards (weaker, human-gated).

## 9. Implementation strategies

```promql
# burn rate: how fast the budget is consumed vs budget rate
( sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) ) / (1 - 0.999)
# remaining budget (30d): fraction of good events still allowed
```

Deploy pipeline: `curl slo-api/check-budget?service=api` → exit 1 if < 10% remaining.

## 10. Production-grade implementation

**Scenario:** 99.9% SLO = 43min/30d; one bad Tuesday burned 38 minutes; Wednesday pipeline blocked all feature merges; team fixed the pool bug; budget recovered; postmortem fed into canary gates; velocity restored.

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

Rollout safety across a fleet: probes, budgets, and automatic rollback are the distributed-systems controls for deployments — a bad pod must be ejected, not tolerated.

## 14. AI/ML/LLM application examples where relevant

Burn budget on quality (faithfulness) not just availability — bad answers consume budget faster than downtime.

## 15. Security considerations

Security hotfixes must bypass error-budget freezes — documented exception path.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Budgets on paper only; "100% reliability" targets; manual override habit; hiding incidents; counting only hard downtime (ignore slow, wrong responses); per-team budgets with no shared accountability.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `budget_consumed_percent`, freeze gates triggered

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Synthetic burn drill (inject 5xx → alert + deploy gate trip); monthly budget report verified against logs; freeze-gate integration test; audit of charges vs incidents.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] Pre-negotiated policy with product/eng leadership
- [ ] Rolling 30d multi-window burn alerts (fast page, slow ticket)
- [ ] Deploy gates consult budget
- [ ] Weekly review slackbot
- [ ] Incidents always charged against the budget (owner)
- [ ] Categorize spend (deploy vs dependency vs bug)
- [ ] Publish weekly.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Freeze policy invoked but leadership overrides ad hoc (credibility dies — or never adopt it); budget computed over too-long a window hides a slow bleed; budget resets monthly causing "spend it in week 1" behavior (rolling windows prevent); no gaming protection (deploying during budget flush then claiming credit); quoting budget but never enforcing → worse than none; measuring budget by LB 5xx only, missing app-level corruption.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://sre.google/sre-book/embracing-risk/
- https://sre.google/workbook/implementing-slos/

**Related topics in this library:** `#63 SLOs`, `#64 SLIs`, `#62 Alerts`, `#109 Production Incidents`, `#53 Canary Releases`, `#66 Observability`.
