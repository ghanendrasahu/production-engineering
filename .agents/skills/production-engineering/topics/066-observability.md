---
topic: 66
title: Observability
category: C
skill: production-engineering
status: stable
---

# 066 — Observability

## 1. Topic name and metadata

- **Number:** 66 of 111
- **Title:** Observability
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/observability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/066-observability.md`

## 2. What it is

The property of a system whose internal state can be understood from its outputs — logs, metrics, traces — enabling answers to questions you did **not** anticipate at design time.

## 3. Why it exists

Monitoring says it broke; observability says why.

## 4. The engineering problem it solves

Monitoring tells you a known failure happened; observability lets you ask "why did *this* request fail for *this* customer?" — without new instrumentation being deployed after the fact.

## 5. How it works internally

Three pillars (correlated via trace_id): metrics (aggregates), logs (events), traces (request trees) — plus **high-cardinality, high-dimensionality** querying (Honeycomb/ClickHouse) where you slice by any dimension (user_id, deploy_sha, region) for unknown-unknowns. Events with wide context beat rigid dashboards. Practical differentiators: trace every request, structured logs with rich context, RED metrics, exemplars jumping metric→trace, and **correlation first** — every signal carries the same trace_id/service/environment.

## 6. Architecture and design principles

OTel SDK everywhere → collector → metrics (Prom/Mimir) + logs (Loki) + traces (Tempo) → single Grafana; or Honeycomb/Datadog as integrated platforms.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Any real production system — always.

## 8. When NOT to use it

N/a.

**Alternatives:** simple correlation only (cheap but weak); managed unified platforms (Honeycomb, Datadog) vs best-of-breed open stack.

<!--END-->

## 9. Implementation strategies

```python
# minimum viable correlation: one trace_id across everything
id = request.headers.get("X-Trace-Id") or uuid4().hex
log = structlog.get_logger().bind(trace_id=id)
log.info("request_in", route=path, method=method)
with tracer.start_as_current_span("handler"):
    ...
```

## 10. Production-grade implementation

**Scenario:** "Checkout failed for user 8832 at 14:02" — one click: trace shows 240ms in `payment.authorize` 401 from provider X for that BIN → merchant-side expired card mapping; no new logging needed; 15 minutes to resolution.

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

Trace-linked prompts/outputs (redacted), exemplars on TTFT histogram — the debugging superpower for 'why was THIS answer bad'.

## 15. Security considerations

Observability stores are sensitive — same IAM class as production data.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Logging pyramids, uncorrelated pillars; high-cardinality panic banning user_id everywhere (instead: bounded via sampling/Honeycomb-style columns); alert-only mentality; observability as a one-time purchase; no redaction (PII in spans = breach).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** exemplars count; `trace_id` in logs; unknown-unknown MTTI

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

"Can we answer: why did request X fail?" drill on staging; correlation assertion in CI (log line ↔ span share trace_id); sampling verification; PII scan; unpredictable-question exercise in game days.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] Correlation via trace_id everywhere
- [ ] Wide structured events
- [ ] Tail sampling for errors
- [ ] Exemplars on latency/error metrics
- [ ] Dashboards for known-unknowns + query power for unknown-unknowns
- [ ] Observability requirements in PR review
- [ ] Incident follow-ups add missing telemetry (not just alerts)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Pillars deployed but not correlated (metrics/logs/traces in separate universes); sampling deletes the exact trace you need (head-based 1% random); dashboard-only culture (known-unknowns only); PII leakage in spans/logs (guard with redaction at collector); "observability" = one Grafana with 60 panels nobody opens; no ownership, no query training → Slack questions go unanswered; treating observability as a purchase instead of a practice (needs onboarding, runbooks, exemplars from day one).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://opentelemetry.io/docs/
- https://sre.google/sre-book/monitoring-distributed-systems/

**Related topics in this library:** `#58 Monitoring`, `#59 Logging`, `#60 Distributed Tracing`, `#61 Metrics`, `#63 SLOs`, `#109 Production Incidents`, `#111 Postmortems`.
