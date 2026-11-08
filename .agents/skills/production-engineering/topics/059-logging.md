---
topic: 59
title: Logging
category: C
skill: production-engineering
status: stable
---

# 059 — Logging

## 1. Topic name and metadata

- **Number:** 59 of 111
- **Title:** Logging
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/observability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/059-logging.md`

## 2. What it is

Structured, searchable, retained records of discrete events (requests, errors, decisions) enabling post-hoc search, debugging, and audit.

## 3. Why it exists

When it breaks at 03:00, only searchable history says why.

## 4. The engineering problem it solves

"It failed yesterday at some point and we have nothing" — unstructured logs and local files make debugging production guesswork and audits impossible.

## 5. How it works internally

Structured JSON (key-value, not sentences): timestamp (RFC3339, UTC), level, trace_id/span_id, service, message, context fields. Collectors (Fluent Bit/Vector/Promtail) ship to Loki/Elasticsearch/CloudWatch; retention tiers (hot 7-30d, cold months). Log levels: ERROR (needs action), WARN (attention), INFO (lifecycle), DEBUG (off in prod). Correlation via `trace_id` ties logs to traces and requests. PII must be redacted — logs are a data lake of leaks by default.

## 6. Architecture and design principles

App → stdout/stderr → container runtime → collector → store (Loki/ES) → Grafana/Kibana; alerting on error-rate log queries.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Always.

## 8. When NOT to use it

N/a.

**Alternatives:** managed SaaS (Datadog/LogDNA) vs self-host Loki/ES; event-sourced audit logs where compliance demands immutable trails.

## 9. Implementation strategies

```python
import structlog, json, sys
structlog.configure(processors=[structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.add_log_level,
    structlog.processors.JSONRenderer()])
log = structlog.get_logger()
log.info("order_created", order_id="o_9", total=129.0, trace_id=trace_id)
```

Never: `print`, f-string logs with secrets (`log.info(f"cfg {settings}")` — scrubber denylist).

## 10. Production-grade implementation

**Scenario:** 2026-10 incident: `payment_failed` events with `provider=stripe error=card_declined trace_id=…`; 40k matching lines; traced spike to a new card BIN failing; 4 hours instead of "some users can't pay".

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

Middleware assigns/logs `X-Request-ID` and `trace_id`; exception handler logs structured error + stack; redact `authorization`, `cookie`, `password`, `ssn` keys via a filter.

## 13. Distributed-system considerations

Rollout safety across a fleet: probes, budgets, and automatic rollback are the distributed-systems controls for deployments — a bad pod must be ejected, not tolerated.

## 14. AI/ML/LLM application examples where relevant

Redacted prompts/responses only — trace_id per request; never log raw user text without scrubbing.

## 15. Security considerations

Redact at the collector — tokens/passwords/PII never hit storage.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

`print()` debugging left in; logging secrets; local log files inside containers; unstructured multiline stack traces without JSON wrap; "log level INFO for everything"; ignoring 4xx logs as noise.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `log_events_total{level}`, `pii_redactions_total`, ingest volume

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Test redaction filter with fake secret → assert absent in output; log-injection test (newline in user input → JSON stays valid, no log forging); verify collector ships to store in staging; volume budget alert; test log query for a known event.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] JSON only
- [ ] Stdout/stderr
- [ ] Redaction filter
- [ ] Trace_id correlation
- [ ] ERROR gets pages, DEBUG off
- [ ] Sampling for noisy endpoints (log 1% of 200s at INFO)
- [ ] Retention policy by class
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Log volume explosion (INFO per request in hot path → $10k/day); PII (tokens, emails, card numbers) in logs → breach; unstructured grep-farms; logs not shipped (container restart loses them — stdout only); duplicate logs (app handler + collector both); log store retention 48h during a 2-week investigation; trace_id missing → logs useless for distributed debugging.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://grafana.com/docs/loki/
- https://opentelemetry.io/docs/

**Related topics in this library:** `#60 Distributed Tracing`, `#61 Metrics`, `#66 Observability`, `#68 IAM` (log access control), `#67 Secrets Management`.
