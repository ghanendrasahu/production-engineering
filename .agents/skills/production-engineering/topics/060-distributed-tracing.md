---
topic: 60
title: Distributed Tracing
category: C
skill: production-engineering
status: stable
---

# 060 — Distributed Tracing

## 1. Topic name and metadata

- **Number:** 60 of 111
- **Title:** Distributed Tracing
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/observability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/060-distributed-tracing.md`

## 2. What it is

End-to-end recording of one request's journey across services — a tree of spans (name, start/end, attributes) sharing a trace_id — reconstructing causality and latency attribution across boundaries.

## 3. Why it exists

Follow one request across services to find the slow hop.

## 4. The engineering problem it solves

Logs tell you service A failed; tracing tells you it failed *waiting on inventory*, which was a `SKIP LOCKED` wait on a pool of 10; without tracing, multi-service latency is un-attributable.

## 5. How it works internally

OpenTelemetry SDK creates spans; context propagated via W3C `traceparent` header (and `baggage`); exporters send to Jaeger/Tempo/OTLP collectors; sampling: head-based (decision at root — misses rare-but-important errors), tail-based (collector buffers whole traces, decides after — catches errors but needs memory), probabilistic rate limiting. Span attributes: db.statement (careful — no raw PII), http.status, gen_ai.* for LLM calls (token counts!). Critical: trace context must flow through async boundaries too (queue messages carry traceparent).

## 6. Architecture and design principles

Services (OTel SDK auto-instrumentation) → OTel Collector (batch, tail-sampling, filter PII) → Tempo/Jaeger → Grafana. Correlation: trace_id in every log line.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

≥2 services or any async hop — essentially always.

## 8. When NOT to use it

Pure monolith, simple CRUD (metrics+logs suffice).

**Alternatives:** correlation IDs + structured logs (cheaper, coarser), APM SaaS (Datadog/New Relic).

## 9. Implementation strategies

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
provider = TracerProvider(); provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="http://otel-collector:4317")))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("app")
with tracer.start_as_current_span("checkout"):
    with tracer.start_as_current_span("charge_payment") as span:
        span.set_attribute("payment.amount", 129.0)
```

FastAPI: `opentelemetry-instrumentation-fastapi` auto-instruments routes.

## 10. Production-grade implementation

**Scenario:** Checkout p95 900ms; trace shows 700ms inside `inventory.lock` → pool 10 → waiters 40; pool raised to 40 → p95 250ms. Without tracing, they would have raised payment-replica counts.

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

One trace per agent run: spans for every LLM call + tool call; `gen_ai.usage.input_tokens` etc. semconv.

## 15. Security considerations

Trace capture: headers and IDs only — never bodies; scrub query params.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Head-based 1% random only (misses error traces); manual context propagation everywhere; traces stored forever (retention 7-30d); span names with IDs interpolated (high cardinality — `GET /orders/{id}` not `/orders/12345`); tracing without logs correlation.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `traces_sampled_total`, span error rate, `trace_id` log correlation rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Synthetic trace through staging path → assert span tree complete; kill collector → request path unaffected (circuit in exporter); sampling-rate test; PII scan of span attributes; queue propagation test.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] OTel everywhere (one standard)
- [ ] Propagate traceparent through HTTP/gRPC/queues
- [ ] Tail sampling for errors + 1-5% baseline
- [ ] Attributes: low cardinality, no PII
- [ ] Log_trace_id in every log
- [ ] Dashboards link from alert → trace
- [ ] Instrument LLM calls with gen_ai spans (tokens, latency)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Context lost at a boundary (manual thread, non-instrumented client) → fragmented traces; sampling drops the slow request exactly when you need it (tail sampling solves); PII dumped into span attributes (query text with user emails); collector down → SDK buffers/drops spans (must not block request path); 100% sampling in prod → doubles egress and costs; clock skew between spans corrupts waterfall (usually tolerable); missing queue traceparent breaks async chains.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://opentelemetry.io/docs/
- https://grafana.com/docs/tempo/

**Related topics in this library:** `#61 Metrics`, `#59 Logging`, `#66 Observability`, `#60 Distributed Tracing` + `#15 Message Queues` (traceparent in messages), `#63 SLOs` (span-derived latency SLIs).
