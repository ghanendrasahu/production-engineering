---
topic: 62
title: Alerts
category: C
skill: production-engineering
status: stable
---

# 062 — Alerts

## 1. Topic name and metadata

- **Number:** 62 of 111
- **Title:** Alerts
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/observability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/062-alerts.md`

## 2. What it is

Automated notifications to humans when metrics/logs indicate actionable conditions — the bridge from observability to human response.

## 3. Why it exists

Page humans for actionable symptoms, never for noise.

## 4. The engineering problem it solves

An unpaged dashboard is decoration; but alert fatigue (crying wolf) makes responders ignore pages — worse than no alerting.

## 5. How it works internally

Prometheus Alertmanager: rules → alerts fire with labels → grouping (by cluster/service), inhibition (suppress low-sev if high-sev for same target), silencing (maintenance), routing by severity (P1 → PagerDuty phone; P3 → Slack ticket). Multi-window burn-rate alerts for SLOs (page: 14.4x over 1h long / 5m short; page: 6x over 6h long / 30m short; ticket: 1x over 3d long / 6h short). Every alert links a runbook containing diagnosis and immediate mitigation commands.

## 6. Architecture and design principles

Prometheus rules → Alertmanager → route tree → PagerDuty/Opsgenie/Slack; runbook URL in payload; post-incident feedback updates thresholds.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Always for production.

## 8. When NOT to use it

Pre-prod/dev.

**Alternatives:** n/a — alerting is the paging contract; only severity and routing vary.

## 9. Implementation strategies

```yaml
groups:
- name: slo.rules
  rules:
  - alert: ErrorBudgetBurnFast
    expr: (rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])) > 14.4 * (1 - 0.995)
    for: 2m
    labels: { severity: page }
    annotations: { summary: "fast error budget burn", runbook: "https://wiki/runbooks/burn" }
```

## 10. Production-grade implementation

**Scenario:** Burn-rate P1 page at 03:12; on-call opens runbook → checks canary % → flips feature flag → 4 minutes; 5 occurrences pattern identified → permanent fix deployed; alert threshold unchanged (it was correct).

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

Page on provider error-rate spikes + cost-burn anomalies; ticket on eval-score drift.

## 15. Security considerations

Alert content must not carry secrets — sanitize annotations and runbooks.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Alerting on causes (CPU high but users fine); 100 thresholds from one brainstorm; no runbooks; ack-and-mute culture; severity inflation (everything P1); no postmortem linkage.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `alerts_firing_total{severity}`, MTTA/MTTR, alert noise rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Synthetic alert test monthly; runbook walk-through; route-tree test to on-call dummy service; flapping test (verify `for:` works); inhibition drill.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] Page only symptom+actionable
- [ ] Multi-window burn rate
- [ ] Inhibition rules for shared root cause
- [ ] `for:` to debounce
- [ ] Runbook required
- [ ] On-call review monthly (tune/delete noisy alerts)
- [ ] Alert on SLI not causes
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Alert on every 4xx (noise); page on batch-job warnings; no `for:` → flapping; route tree misconfigured → P1 to a dead Slack; silences creating week-long blind spots; alert without runbook (MTTA balloons); threshold set from wishful thinking; nobody owns on-call rotations; cascading duplicate pages from one root cause (inhibition missing).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://prometheus.io/docs/
- https://prometheus.io/docs/

**Related topics in this library:** `#58 Monitoring`, `#61 Metrics`, `#63 SLOs`, `#65 Error Budgets`, `#110 On-Call`, `#111 Postmortems`.
