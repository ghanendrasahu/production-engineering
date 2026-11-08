---
topic: 64
title: SLIs
category: C
skill: production-engineering
status: stable
---

# 064 — SLIs

## 1. Topic name and metadata

- **Number:** 64 of 111
- **Title:** SLIs
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/observability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/064-slis.md`

## 2. What it is

Service Level Indicator — the concrete measurement behind an SLO, e.g., proportion of requests completing <300ms without server error, computed over a window.

## 3. Why it exists

Objectives are meaningless without defined measurements.

## 4. The engineering problem it solves

"We're 99.9% reliable" is meaningless without a defined measurement; ambiguous SLIs make SLOs untestable and debates endless.

## 5. How it works internally

Good events / valid events over the window. Valid events exclude planned maintenance, client 4xx, health-check probes. Latency SLI uses histogram buckets; availability uses status class; correctness SLI (returned right data) needs app-level verification; freshness (data age) for pipelines via last-ingest timestamp. Aggregation across endpoints: weight by traffic or define per-journey SLOs. Source: Prometheus recording rules or gateway telemetry.

## 6. Architecture and design principles

Telemetry source → recording rules/SLI platform → SLO dashboard → error budget math.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Defining any SLO — mandatory.

## 8. When NOT to use it

N/a.

**Alternatives:** tracer-derived SLIs (span duration from OTel), gateway logs, cloud LB metrics.

## 9. Implementation strategies

```promql
# availability SLI
sum(rate(http_requests_total{status!~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
# latency SLI: % under 300ms
sum(rate(http_request_seconds_bucket{le="0.3",route="/checkout"}[5m])) / sum(rate(http_request_seconds_count{route="/checkout"}[5m]))
```

## 10. Production-grade implementation

**Scenario:** Checkout journey SLI: 99.9% of `POST /checkout` either <300ms with 2xx/3xx, or a documented 409 (sold out); measured via gateway logs; November p99 780ms from N+1 query consumed half budget — discovered by budget burndown chart, not complaints.

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

SLI: % generations under TTFT threshold; % answers passing groundedness/eval threshold.

## 15. Security considerations

SLI misdefinitions mask breaches — review the good-event definition with security.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Vanity SLIs (client-side noise); counting infrastructure errors as none-events; SLI on CPU; SLI computed from logs with 30% drop; per-instance SLIs instead of journey-level; change without communication.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** SLI ratio per journey (availability/latency/correctness)

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Unit test PromQL against fixture TSDB; verify SLI against synthetic known-bad traffic; drift check when histogram buckets change; cross-team audit of valid/good definitions.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] Valid-events definition documented and reviewed
- [ ] User-perceived measurement (not internal ticks)
- [ ] Record SLIs at LB or app edge
- [ ] Histogram bucket aligned with SLO threshold
- [ ] One SLI per critical journey
- [ ] Export to SLO platform
- [ ] Audit quarterly
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** SLI excludes the endpoints users actually use; valid-event definition quietly excludes real errors ("4xx excluded" hides auth breakage); latency measured at LB only (hides app work); high-cardinality SLI queries time out (record at source instead); SLI drift after API redesign without SLO update; different SLI per environment confuses comparisons.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://sre.google/sre-book/service-level-objectives/

**Related topics in this library:** `#63 SLOs`, `#65 Error Budgets`, `#61 Metrics`, `#93 P99 Latency`, `#66 Observability`.
