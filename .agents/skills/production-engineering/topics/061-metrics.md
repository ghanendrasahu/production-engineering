---
topic: 61
title: Metrics
category: C
skill: production-engineering
status: stable
---

# 061 — Metrics

## 1. Topic name and metadata

- **Number:** 61 of 111
- **Title:** Metrics
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/observability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/061-metrics.md`

## 2. What it is

Numeric time series measured at intervals (counters, gauges, histograms) enabling aggregation, alerting, and trend analysis; the cheapest observability signal per decision.

## 3. Why it exists

Numbers you do not collect cannot page you.

## 4. The engineering problem it solves

Without metrics you can't page, can't trend, can't do capacity planning; logs alone can't tell you aggregate error rate.

## 5. How it works internally

Types: counter (monotonic sum — `rate()`), gauge (current value), histogram/summary (distribution — `histogram_quantile(0.99, ...)`). Prometheus model: pull at interval 15-30s; labels create dimensions — **cardinality explodes**: avoid per-user/order-id labels. Sampling buckets pre-set for latency (.005,.01,.025,.05,.1,.25,.5,1,2.5,5,10). Recording rules pre-compute expensive PromQL. Pushgateway only for batch jobs. Exemplars link metric points to traces.

## 6. Architecture and design principles

App `/metrics` → Prometheus → recording rules → Grafana; alerts on ratios, not raw counts.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Always.

## 8. When NOT to use it

N/a.

**Alternatives:** StatsD push (UDP, lossy), OpenTelemetry metrics (equivalent), managed APM.

## 9. Implementation strategies

```python
from prometheus_client import Counter, Histogram, Gauge
HTTP = Counter("http_requests_total", "", ["route","status"])
LAT = Histogram("http_request_seconds", "", ["route"])
INFLIGHT = Gauge("http_inflight", "")
```

```promql
histogram_quantile(0.99, sum by (le, route) (rate(http_request_seconds_bucket[5m])))
sum by (status) (rate(http_requests_total{route="/checkout"}[5m]))
```

## 10. Production-grade implementation

**Scenario:** `error_budget_burn = rate(5xx[5m]) / rate(total[5m])` burned 100x budget in 5min → page; team saw new deploy flagged; pushed kill switch in 90s; SLO saved.

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

Tokens/s, TTFT, ITL, cost per 1M tokens, free-GPU ratio — meter per feature, not just per model.

## 15. Security considerations

High-cardinality labels = PII — route/status/version only.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

user_id/order_id in labels; alerting on CPU alone; counting without rate over windows; dashboards nobody checks; metrics with no owner; no retention plan.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `http_requests_total`, latency histogram buckets, error ratio

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

promtool check-rules; integration test asserting `/metrics` emits expected counters; alert-fire drill; cardinality audit; dashboard render check.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] RED+USE
- [ ] Judicious labels (route, status, version)
- [ ] Custom histogram buckets
- [ ] Recording rules for dashboards
- [ ] Exemplars → trace links
- [ ] Alert on ratios
- [ ] Document metric meanings
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** High-cardinality labels (user_id) → Prometheus OOM; raw counts paged (use ratios); histogram buckets default mismatched (P99 invisible — custom buckets mandatory); metrics missing on crash before flush (scrape still gets last values if process alive); `rate()` on a gauge (nonsense); recording rules not tested (silent broken dashboards); stale metric after old deploy still scraped (`up` handles).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://prometheus.io/docs/concepts/metric_types/

**Related topics in this library:** `#62 Alerts`, `#58 Monitoring`, `#63 SLOs`, `#60 Distributed Tracing`, `#64 SLIs`, `#66 Observability`.
