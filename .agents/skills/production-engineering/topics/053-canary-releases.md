---
topic: 53
title: Canary Releases
category: C
skill: production-engineering
status: stable
---

# 053 — Canary Releases

## 1. Topic name and metadata

- **Number:** 53 of 111
- **Title:** Canary Releases
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/deployment.md)
- **Topic file:** `.agents/skills/production-engineering/topics/053-canary-releases.md`

## 2. What it is

Route a small percentage of real traffic to the new version; watch metrics; ramp gradually; auto-rollback if SLIs degrade.

## 3. Why it exists

Small blast radius, measured ramp, automatic stop on regression.

## 4. The engineering problem it solves

Blue-green shifts 100% at once — a subtle bug hits everyone; canary limits blast radius to 1-5% and catches what tests can't (load, data skew, provider behavior).

## 5. How it works internally

Traffic splitting at LB/service mesh (weighted targets: 95/5), progressive rollout (Flagger/Argo Rollouts: steps 10%→25%→50%→100% with analysis runs querying Prometheus for error rate/latency), analysis template with success criteria (e.g., `p99 < 300ms`, `5xx ratio < 0.1%`), automatic rollback on failure, automatic advance on success. Cohorts sticky by consistent hash on user-id/tenant.

## 6. Architecture and design principles

Deploy new ReplicaSet alongside old → mesh/LB splits by weight → analysis controller reads metrics → decides promote/abort.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Production services with metrics maturity — most stateless services.

## 8. When NOT to use it

No meaningful SLIs (build those first); single-instance systems; stateful migrations without expand/contract.

**Alternatives:** blue-green, flags + rolling, dark launch (mirror traffic, no user impact).

## 9. Implementation strategies

```yaml
# Argo Rollouts canary step (excerpt)
strategy:
  canary:
    steps:
      - setWeight: 5
      - pause: { duration: 10m }
      - setWeight: 25
      - analysis:
          templates: [{ templateName: error-rate }]
      - setWeight: 50
      - pause: { duration: 10m }
```

Success criteria: `sum(rate(http_requests_total{status=~"5..",version="canary"}[5m])) / sum(rate(http_requests_total{version="canary"}[5m])) < 0.01`.

## 10. Production-grade implementation

**Scenario:** Recommendation model v3: 2% traffic for 6h, p99 inference latency and click-through compared; canary error rate normal → ramped 10/25/50/100 over 2 days; bug in embed cache never reached >25% users; auto-analysis would have aborted otherwise.

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

Version header `X-Release: canary` via middleware; metrics labeled `version="canary"`; dashboards comparing cohorts instantly; rollback = scale canary to zero / weight 0.

## 13. Distributed-system considerations

Rollout safety across a fleet: probes, budgets, and automatic rollback are the distributed-systems controls for deployments — a bad pod must be ejected, not tolerated.

## 14. AI/ML/LLM application examples where relevant

Eval-gated canary: ramp only when faithfulness/cost metrics hold; auto-rollback on regression (like Argo Rollouts analysis).

## 15. Security considerations

Canary gets production traffic — same auth, same audit, same limits.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Manual-only ramp with no metrics gate; 1% for 1 minute "looks fine"; canary on non-representative path; no auto-rollback; cohorts unsticky; two canaries at once (attribution impossible).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `canary_error_rate`, `canary_latency_vs_stable`, rollback events

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Analysis-abort drill (inject 5xx in canary pod → auto-rollback fires); sticky-bucket distribution test; promote-on-healthy E2E in staging; comparison dashboard sanity; rollback timing measurement.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] Automated analysis + auto-rollback (never manual gates alone)
- [ ] Sticky cohorts
- [ ] 5-10min bake minimum
- [ ] Compare cohorts on latency/errors/business KPI
- [ ] Flags for behavior + canary for infra (belt and braces)
- [ ] Metric labels with version everywhere
- [ ] Alert only if canary aborts.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Metrics window too short to catch slow leaks (bake ≥ 10-15min per step); canary without representative users/traffic mix (only internal employees on canary → no signal); rollback not automated → human lag in incident; sticky sessions missing → user bounces between versions mid-flow (state mismatch); error budget burn by canary without auto-abort; flag/canary cache poisoning across cohorts; analysis query wrong (compares wrong denominators) → false abort or false promote.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://argoproj.github.io/rollouts/
- https://flagger.app/

**Related topics in this library:** `#52 Blue-Green Deployment`, `#55 Rollbacks`, `#63 SLOs`, `#64 SLIs`, `#61 Metrics`, `#53 Canary Releases` needs `#66 Observability`.
