---
topic: 58
title: Monitoring
category: C
skill: production-engineering
status: stable
---

# 058 — Monitoring

## 1. Topic name and metadata

- **Number:** 58 of 111
- **Title:** Monitoring
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/observability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/058-monitoring.md`

## 2. What it is

Continuous collection and visualization of system/app signals (from external probes to internal metrics) to know the current state and trend of the service.

## 3. Why it exists

If nobody watches it, it is not monitored.

## 4. The engineering problem it solves

You cannot fix what you cannot see; without dashboards and health signals, degradation is discovered by users — or never.

## 5. How it works internally

Two modes: **active** (external probes from synthetic monitors — status-page checks, blackbox_exporter) and **passive** (scraped metrics, pushed logs). Stack: Prometheus pulls `/metrics` every 15-30s; Alertmanager routes; Grafana visualizes; retention tiers (short high-res, long downsampled). Four golden signals. USE method (utilization/saturation/errors) for resources; RED (rate/errors/duration) for services. Monitoring ≠ observability (below).

## 6. Architecture and design principles

App exposes metrics/logs → Prometheus scrapes/Loki/Elastic collects → Grafana → Alertmanager → PagerDuty/Slack; on-call reads dashboards first.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Always.

## 8. When NOT to use it

N/a.

**Alternatives:** managed (Datadog, Grafana Cloud, CloudWatch) vs self-hosted Prometheus; hosted = less ops, better out of box.

## 9. Implementation strategies

```python
from prometheus_client import Counter, Histogram, start_http_server
REQUESTS = Counter("http_requests_total", "requests", ["route", "status"])
LATENCY = Histogram("http_request_seconds", "latency", ["route"], buckets=[.05,.1,.25,.5,1,2.5])
start_http_server(9100)
```

```yaml
# prometheus.yml
scrape_configs: [{job_name: app, static_configs: [{targets: ["app:9100"]}], scrape_interval: 15s}]
```

## 10. Production-grade implementation

**Scenario:** p95 latency dashboard (RED) per route; blackbox probe every 30s from 3 regions; on-call runs `rate(http_requests_total{status=~"5.."}[5m]) > 0.01` daily — caught a degraded replica 40 minutes before users complained.

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

GPU util, queue depth, tokens/s per model, TTFT/ITL, fallback rate — the AI golden signals.

## 15. Security considerations

Monitoring is the org's memory — IAM on dashboards, retention, PII-free labels.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Metrics for everything, alerts for nothing; single giant dashboard; CPU-only scaling insight; no external probe; alerts with no runbook; silence as a resolution.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `up`, `target_scrape_errors`, coverage of service signals

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Fire a synthetic error surge → dashboards show it within 30s; kill a replica → blackbox flips; verify alert routing to a test receiver; scrape-miss detection (`up == 0` alert); cardinality audit quarterly.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] RED for services, USE for resources
- [ ] Blackbox probes
- [ ] Golden dashboards per service with owner
- [ ] Alert only on actionable signals
- [ ] Retention ≥ 13 months for audit
- [ ] Monitor the monitoring (up metric for Prometheus itself)
- [ ] Postmortem-linked dashboards
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Alerting on everything (alert fatigue → ignored pages); dashboards nobody watches (monitoring as compliance theater); metrics without ownership (nobody knows what "queue_depth" means); scrape too infrequent → miss fast degradations; missing blackbox probe → LB alive but DNS broken undetected; retention so short incidents can't be investigated; metric name changes breaking dashboards silently.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://prometheus.io/docs/
- https://grafana.com/docs/

**Related topics in this library:** `#61 Metrics`, `#62 Alerts`, `#66 Observability`, `#60 Distributed Tracing`, `#63 SLOs`, `#56 Health Checks`.
