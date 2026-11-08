# Observability Reference (Monitoring, Logging, Tracing, Metrics, SLOs)

Covers topics 58-66: monitoring, logging, distributed tracing, metrics, alerts, SLOs, SLIs, error budgets, observability.

### 58. Monitoring

**Definition:** Continuous collection and visualization of system/app signals (from external probes to internal metrics) to know the current state and trend of the service.

**Problem:** You cannot fix what you cannot see; without dashboards and health signals, degradation is discovered by users — or never.

**Internal Working:** Two modes: **active** (external probes from synthetic monitors — status-page checks, blackbox_exporter) and **passive** (scraped metrics, pushed logs). Stack: Prometheus pulls `/metrics` every 15-30s; Alertmanager routes; Grafana visualizes; retention tiers (short high-res, long downsampled). Four golden signals. USE method (utilization/saturation/errors) for resources; RED (rate/errors/duration) for services. Monitoring ≠ observability (below).

**Architecture:** App exposes metrics/logs → Prometheus scrapes/Loki/Elastic collects → Grafana → Alertmanager → PagerDuty/Slack; on-call reads dashboards first.

**Implementation:**

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

**Production Example:** p95 latency dashboard (RED) per route; blackbox probe every 30s from 3 regions; on-call runs `rate(http_requests_total{status=~"5.."}[5m]) > 0.01` daily — caught a degraded replica 40 minutes before users complained.

**Failure Scenarios:** Alerting on everything (alert fatigue → ignored pages); dashboards nobody watches (monitoring as compliance theater); metrics without ownership (nobody knows what "queue_depth" means); scrape too infrequent → miss fast degradations; missing blackbox probe → LB alive but DNS broken undetected; retention so short incidents can't be investigated; metric name changes breaking dashboards silently.

**Best Practices:** RED for services, USE for resources; blackbox probes; golden dashboards per service with owner; alert only on actionable signals; retention ≥ 13 months for audit; monitor the monitoring (up metric for Prometheus itself); postmortem-linked dashboards; consistent metric naming.

**Anti-Patterns:** Metrics for everything, alerts for nothing; single giant dashboard; CPU-only scaling insight; no external probe; alerts with no runbook; silence as a resolution.

**Trade-offs:** Performance (scrape overhead negligible; metric cardinality is the real cost); complexity (moderate with managed stacks); cost (retention × cardinality — watch series count); consistency (n/a); maintainability (dashboards-as-code (Grafonnet/JSON in Git)).

**Testing:** Fire a synthetic error surge → dashboards show it within 30s; kill a replica → blackbox flips; verify alert routing to a test receiver; scrape-miss detection (`up == 0` alert); cardinality audit quarterly.

**Related Concepts:** `#61 Metrics`, `#62 Alerts`, `#66 Observability`, `#60 Distributed Tracing`, `#63 SLOs`, `#56 Health Checks`.

**Decision Criteria:** Use when: always. Do not use when: n/a. Alternatives: managed (Datadog, Grafana Cloud, CloudWatch) vs self-hosted Prometheus; hosted = less ops, better out of box.


### 59. Logging

**Definition:** Structured, searchable, retained records of discrete events (requests, errors, decisions) enabling post-hoc search, debugging, and audit.

**Problem:** "It failed yesterday at some point and we have nothing" — unstructured logs and local files make debugging production guesswork and audits impossible.

**Internal Working:** Structured JSON (key-value, not sentences): timestamp (RFC3339, UTC), level, trace_id/span_id, service, message, context fields. Collectors (Fluent Bit/Vector/Promtail) ship to Loki/Elasticsearch/CloudWatch; retention tiers (hot 7-30d, cold months). Log levels: ERROR (needs action), WARN (attention), INFO (lifecycle), DEBUG (off in prod). Correlation via `trace_id` ties logs to traces and requests. PII must be redacted — logs are a data lake of leaks by default.

**Architecture:** App → stdout/stderr → container runtime → collector → store (Loki/ES) → Grafana/Kibana; alerting on error-rate log queries.

**Implementation:**

```python
import structlog, json, sys
structlog.configure(processors=[structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.add_log_level,
    structlog.processors.JSONRenderer()])
log = structlog.get_logger()
log.info("order_created", order_id="o_9", total=129.0, trace_id=trace_id)
```

Never: `print`, f-string logs with secrets (`log.info(f"cfg {settings}")` — scrubber denylist).

**FastAPI Example:** Middleware assigns/logs `X-Request-ID` and `trace_id`; exception handler logs structured error + stack; redact `authorization`, `cookie`, `password`, `ssn` keys via a filter.

**Production Example:** 2026-10 incident: `payment_failed` events with `provider=stripe error=card_declined trace_id=…`; 40k matching lines; traced spike to a new card BIN failing; 4 hours instead of "some users can't pay".

**Failure Scenarios:** Log volume explosion (INFO per request in hot path → $10k/day); PII (tokens, emails, card numbers) in logs → breach; unstructured grep-farms; logs not shipped (container restart loses them — stdout only); duplicate logs (app handler + collector both); log store retention 48h during a 2-week investigation; trace_id missing → logs useless for distributed debugging.

**Best Practices:** JSON only; stdout/stderr; redaction filter; trace_id correlation; ERROR gets pages, DEBUG off; sampling for noisy endpoints (log 1% of 200s at INFO); retention policy by class; PII inventory in logs; dashboards link logs↔traces; alert on log-derived error rate.

**Anti-Patterns:** `print()` debugging left in; logging secrets; local log files inside containers; unstructured multiline stack traces without JSON wrap; "log level INFO for everything"; ignoring 4xx logs as noise.

**Trade-offs:** Performance (JSON serialization ~µs; I/O is the cost — async batch shippers); complexity (collector + store ops); cost (volume × retention — biggest observability cost driver); consistency (time-synced UTC); maintainability (schema conventions documented).

**Testing:** Test redaction filter with fake secret → assert absent in output; log-injection test (newline in user input → JSON stays valid, no log forging); verify collector ships to store in staging; volume budget alert; test log query for a known event.

**Related Concepts:** `#60 Distributed Tracing`, `#61 Metrics`, `#66 Observability`, `#68 IAM` (log access control), `#67 Secrets Management`.

**Decision Criteria:** Use when: always. Do not use when: n/a. Alternatives: managed SaaS (Datadog/LogDNA) vs self-host Loki/ES; event-sourced audit logs where compliance demands immutable trails.

### 60. Distributed Tracing

**Definition:** End-to-end recording of one request's journey across services — a tree of spans (name, start/end, attributes) sharing a trace_id — reconstructing causality and latency attribution across boundaries.

**Problem:** Logs tell you service A failed; tracing tells you it failed *waiting on inventory*, which was a `SKIP LOCKED` wait on a pool of 10; without tracing, multi-service latency is un-attributable.

**Internal Working:** OpenTelemetry SDK creates spans; context propagated via W3C `traceparent` header (and `baggage`); exporters send to Jaeger/Tempo/OTLP collectors; sampling: head-based (decision at root — misses rare-but-important errors), tail-based (collector buffers whole traces, decides after — catches errors but needs memory), probabilistic rate limiting. Span attributes: db.statement (careful — no raw PII), http.status, gen_ai.* for LLM calls (token counts!). Critical: trace context must flow through async boundaries too (queue messages carry traceparent).

**Architecture:** Services (OTel SDK auto-instrumentation) → OTel Collector (batch, tail-sampling, filter PII) → Tempo/Jaeger → Grafana. Correlation: trace_id in every log line.

**Implementation:**

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

**Production Example:** Checkout p95 900ms; trace shows 700ms inside `inventory.lock` → pool 10 → waiters 40; pool raised to 40 → p95 250ms. Without tracing, they would have raised payment-replica counts.

**Failure Scenarios:** Context lost at a boundary (manual thread, non-instrumented client) → fragmented traces; sampling drops the slow request exactly when you need it (tail sampling solves); PII dumped into span attributes (query text with user emails); collector down → SDK buffers/drops spans (must not block request path); 100% sampling in prod → doubles egress and costs; clock skew between spans corrupts waterfall (usually tolerable); missing queue traceparent breaks async chains.

**Best Practices:** OTel everywhere (one standard); propagate traceparent through HTTP/gRPC/queues; tail sampling for errors + 1-5% baseline; attributes: low cardinality, no PII; log_trace_id in every log; dashboards link from alert → trace; instrument LLM calls with gen_ai spans (tokens, latency); collector with memory limiter; verify sampling config in staging.

**Anti-Patterns:** Head-based 1% random only (misses error traces); manual context propagation everywhere; traces stored forever (retention 7-30d); span names with IDs interpolated (high cardinality — `GET /orders/{id}` not `/orders/12345`); tracing without logs correlation.

**Trade-offs:** Performance (~1-3% overhead with batch export; async queues off critical path); complexity (collector + backend); cost (storage scales with spans — sample hard); consistency (UTC timestamps + skew); maintainability (auto-instrumentation >> manual).

**Testing:** Synthetic trace through staging path → assert span tree complete; kill collector → request path unaffected (circuit in exporter); sampling-rate test; PII scan of span attributes; queue propagation test.

**Related Concepts:** `#61 Metrics`, `#59 Logging`, `#66 Observability`, `#60 Distributed Tracing` + `#15 Message Queues` (traceparent in messages), `#63 SLOs` (span-derived latency SLIs).

**Decision Criteria:** Use when: ≥2 services or any async hop — essentially always. Do not use when: pure monolith, simple CRUD (metrics+logs suffice). Alternatives: correlation IDs + structured logs (cheaper, coarser), APM SaaS (Datadog/New Relic).


### 61. Metrics

**Definition:** Numeric time series measured at intervals (counters, gauges, histograms) enabling aggregation, alerting, and trend analysis; the cheapest observability signal per decision.

**Problem:** Without metrics you can't page, can't trend, can't do capacity planning; logs alone can't tell you aggregate error rate.

**Internal Working:** Types: counter (monotonic sum — `rate()`), gauge (current value), histogram/summary (distribution — `histogram_quantile(0.99, ...)`). Prometheus model: pull at interval 15-30s; labels create dimensions — **cardinality explodes**: avoid per-user/order-id labels. Sampling buckets pre-set for latency (.005,.01,.025,.05,.1,.25,.5,1,2.5,5,10). Recording rules pre-compute expensive PromQL. Pushgateway only for batch jobs. Exemplars link metric points to traces.

**Architecture:** App `/metrics` → Prometheus → recording rules → Grafana; alerts on ratios, not raw counts.

**Implementation:**

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

**Production Example:** `error_budget_burn = rate(5xx[5m]) / rate(total[5m])` burned 100x budget in 5min → page; team saw new deploy flagged; pushed kill switch in 90s; SLO saved.

**Failure Scenarios:** High-cardinality labels (user_id) → Prometheus OOM; raw counts paged (use ratios); histogram buckets default mismatched (P99 invisible — custom buckets mandatory); metrics missing on crash before flush (scrape still gets last values if process alive); `rate()` on a gauge (nonsense); recording rules not tested (silent broken dashboards); stale metric after old deploy still scraped (`up` handles).

**Best Practices:** RED+USE; judicious labels (route, status, version); custom histogram buckets; recording rules for dashboards; exemplars → trace links; alert on ratios; document metric meanings; purge high-cardinality offenders; test PromQL in CI (promtool).

**Anti-Patterns:** user_id/order_id in labels; alerting on CPU alone; counting without rate over windows; dashboards nobody checks; metrics with no owner; no retention plan.

**Trade-offs:** Performance (scrape + tiny CPU; push path); complexity (moderate); cost (series × retention); consistency (token-per-second ~no); maintainability (naming conventions).

**Testing:** promtool check-rules; integration test asserting `/metrics` emits expected counters; alert-fire drill; cardinality audit; dashboard render check.

**Related Concepts:** `#62 Alerts`, `#58 Monitoring`, `#63 SLOs`, `#60 Distributed Tracing`, `#64 SLIs`, `#66 Observability`.

**Decision Criteria:** Use when: always. Do not use when: n/a. Alternatives: StatsD push (UDP, lossy), OpenTelemetry metrics (equivalent), managed APM.


### 62. Alerts

**Definition:** Automated notifications to humans when metrics/logs indicate actionable conditions — the bridge from observability to human response.

**Problem:** An unpaged dashboard is decoration; but alert fatigue (crying wolf) makes responders ignore pages — worse than no alerting.

**Internal Working:** Prometheus Alertmanager: rules → alerts fire with labels → grouping (by cluster/service), inhibition (suppress low-sev if high-sev for same target), silencing (maintenance), routing by severity (P1 → PagerDuty phone; P3 → Slack ticket). Multi-window burn-rate alerts for SLOs (fast burn 14.4x 5min+long 14d for precision, slow burn 6x 6h+3d). Every alert links a runbook containing diagnosis and immediate mitigation commands.

**Architecture:** Prometheus rules → Alertmanager → route tree → PagerDuty/Opsgenie/Slack; runbook URL in payload; post-incident feedback updates thresholds.

**Implementation:**

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

**Production Example:** Burn-rate P1 page at 03:12; on-call opens runbook → checks canary % → flips feature flag → 4 minutes; 5 occurrences pattern identified → permanent fix deployed; alert threshold unchanged (it was correct).

**Failure Scenarios:** Alert on every 4xx (noise); page on batch-job warnings; no `for:` → flapping; route tree misconfigured → P1 to a dead Slack; silences creating week-long blind spots; alert without runbook (MTTA balloons); threshold set from wishful thinking; nobody owns on-call rotations; cascading duplicate pages from one root cause (inhibition missing).

**Best Practices:** Page only symptom+actionable; multi-window burn rate; inhibition rules for shared root cause; `for:` to debounce; runbook required; on-call review monthly (tune/delete noisy alerts); alert on SLI not causes; test alerts fire into a test channel; track MTTA/MTTR per alert; error budget integration.

**Anti-Patterns:** Alerting on causes (CPU high but users fine); 100 thresholds from one brainstorm; no runbooks; ack-and-mute culture; severity inflation (everything P1); no postmortem linkage.

**Trade-offs:** Performance (n/a); complexity (rule + route tuning); cost (modest); consistency (n/a); maintainability (the hardest operational discipline in SRE).

**Testing:** Synthetic alert test monthly; runbook walk-through; route-tree test to on-call dummy service; flapping test (verify `for:` works); inhibition drill.

**Related Concepts:** `#58 Monitoring`, `#61 Metrics`, `#63 SLOs`, `#65 Error Budgets`, `#110 On-Call`, `#111 Postmortems`.

**Decision Criteria:** Use when: always for production. Do not use when: pre-prod/dev. Alternatives: n/a — alerting is the paging contract; only severity and routing vary.


### 63. SLOs

**Definition:** Service Level Objective — the target value of an SLI over a rolling window (e.g., 99.9% of HTTP requests succeed with latency < 300ms, measured monthly); the explicit reliability contract.

**Problem:** Without a target, reliability debates are vibes; error budget gives a data-driven policy for balancing velocity vs stability.

**Internal Working:** SLO = objective; SLI = measurement; error budget = 1 − SLO over window (99.9% → 43.8 minutes per 30d). Availability SLI: `good events / valid events`. Latency SLI: % of events under threshold. Rolling 30d math. Policy: when budget burns too fast, freeze features and ship reliability work; when budget healthy, ship aggressively. Multi-burn-rate alerts (`#62`) detect fast/slow consumption. Review SLOs quarterly with business.

**Architecture:** SLO definitions (SLI + objective + window + owner) living in an SLO platform (Nobl9/Grafana SLO) or as Prometheus recording rules + dashboards; error budget feeds deploy gates.

**Implementation:**

```promql
# SLI: proportion of good requests (fast 5m and slow 6h windows)
1 - (sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])))
```

Weekly review: `error_budget_remaining = SLO - (1 - achieved_SLI)` over 30 days.

**FastAPI Example:** Middleware labels requests; `/slo.json` or Grafana panel shows rolling SLI vs SLO; budget exhausted → CI pipeline blocks feature deploys (gate on remaining budget < 10%).

**Production Example:** API SLO 99.95% over 30 days (≤ 21.9 min bad); November: one bad deploy consumed 60% of budget in 40 minutes; feature freeze invoked; team shipped retry/pool fixes; December budget healthy — velocity resumed. Auditors approved; customers noticed nothing.

**Failure Scenarios:** SLO set equal to current best ("99.99% because we once saw it") → impossible, permanent freeze; measuring success by uptime % rather than user-visible errors; SLI includes internal health checks (gaming own SLO); window too short/noisy; no owner; no burn-rate alerts → budget gone before anyone knows; SLO on everything (dilutes focus to 2-4 critical services).

**Best Practices:** 2-4 SLOs per user journey; user-perceived metrics; rolling 28-30d; multi-window burn alerts; error-budget freeze policy pre-agreed with product; quarterly review vs real incidents; include latency + availability; document exclusion rules (dependency outages count or don't — say which).

**Anti-Patterns:** Vanity SLOs (100%); uptime-based SLOs ignoring correctness; gaming via cheap checks; no consequence policy; SLOs nobody reviews; counting your own greps.

**Trade-offs:** Performance (n/a); complexity (SLO platform optional; can do on dashboards); cost (minimal); consistency (n/a); maintainability (process + cultural — needs leadership backing).

**Testing:** Alert drill: burn fast synthetic → page fires; SLI unit checks in CI (expected values from fixture data); budget-remaining dashboard verification; freeze-gate test in deploy pipeline.

**Related Concepts:** `#64 SLIs`, `#65 Error Budgets`, `#62 Alerts`, `#93 P99 Latency`, `#66 Observability`, `#110 On-Call`.

**Decision Criteria:** Use when: customer-facing production services. Do not use when: internal batch-only tooling (use job success metrics, not SLOs). Alternatives: SLAs (legal contract, superset of SLO) for external commitments.


### 64. SLIs

**Definition:** Service Level Indicator — the concrete measurement behind an SLO, e.g., proportion of requests completing <300ms without server error, computed over a window.

**Problem:** "We're 99.9% reliable" is meaningless without a defined measurement; ambiguous SLIs make SLOs untestable and debates endless.

**Internal Working:** Good events / valid events over the window. Valid events exclude planned maintenance, client 4xx, health-check probes. Latency SLI uses histogram buckets; availability uses status class; correctness SLI (returned right data) needs app-level verification; freshness (data age) for pipelines via last-ingest timestamp. Aggregation across endpoints: weight by traffic or define per-journey SLOs. Source: Prometheus recording rules or gateway telemetry.

**Architecture:** Telemetry source → recording rules/SLI platform → SLO dashboard → error budget math.

**Implementation:**

```promql
# availability SLI
sum(rate(http_requests_total{status!~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
# latency SLI: % under 300ms
sum(rate(http_request_seconds_bucket{le="0.3",route="/checkout"}[5m])) / sum(rate(http_request_seconds_count{route="/checkout"}[5m]))
```

**Production Example:** Checkout journey SLI: 99.9% of `POST /checkout` either <300ms with 2xx/3xx, or a documented 409 (sold out); measured via gateway logs; November p99 780ms from N+1 query consumed half budget — discovered by budget burndown chart, not complaints.

**Failure Scenarios:** SLI excludes the endpoints users actually use; valid-event definition quietly excludes real errors ("4xx excluded" hides auth breakage); latency measured at LB only (hides app work); high-cardinality SLI queries time out (record at source instead); SLI drift after API redesign without SLO update; different SLI per environment confuses comparisons.

**Best Practices:** Valid-events definition documented and reviewed; user-perceived measurement (not internal ticks); record SLIs at LB or app edge; histogram bucket aligned with SLO threshold; one SLI per critical journey; export to SLO platform; audit quarterly; never count your own health checks.

**Anti-Patterns:** Vanity SLIs (client-side noise); counting infrastructure errors as none-events; SLI on CPU; SLI computed from logs with 30% drop; per-instance SLIs instead of journey-level; change without communication.

**Trade-offs:** Performance (recording exact buckets ~free); complexity (definitions must be agreed across teams); cost (minimal); consistency (UTC windows); maintainability (documented definitions versioned in Git).

**Testing:** Unit test PromQL against fixture TSDB; verify SLI against synthetic known-bad traffic; drift check when histogram buckets change; cross-team audit of valid/good definitions.

**Related Concepts:** `#63 SLOs`, `#65 Error Budgets`, `#61 Metrics`, `#93 P99 Latency`, `#66 Observability`.

**Decision Criteria:** Use when: defining any SLO — mandatory. Do not use when: n/a. Alternatives: tracer-derived SLIs (span duration from OTel), gateway logs, cloud LB metrics.


### 65. Error Budgets

**Definition:** The allowed unreliability derived from an SLO (1 − SLO) over the window — e.g., 43.8 min/30d at 99.9% — managed as a resource to spend on risk, not a metric to mourn.

**Problem:** "How much change is safe?" has no objective answer without a budget; error budgets turn that argument into policy and end the velocitist-vs-stability stalemate.

**Internal Working:** Budget remaining = SLO% − actual bad% (over rolling window). Burn rate = consumption speed vs steady state (1x = exactly spends budget over window). Policies: burn > 2x → alert; > 14.4x fast burn → page + freeze; budget exhausted → feature deploys halt, reliability work mandated — a negotiated, pre-agreed policy, not a panic. Multi-window alerting avoids noise from single blips.

**Architecture:** SLO platform/recording rules → burn-rate alerts → deploy gate (check remaining budget) → release policy.

**Implementation:**

```promql
# burn rate: how fast the budget is consumed vs budget rate
( sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) ) / (1 - 0.999)
# remaining budget (30d): fraction of good events still allowed
```

Deploy pipeline: `curl slo-api/check-budget?service=api` → exit 1 if < 10% remaining.

**Production Example:** 99.9% SLO = 43min/30d; one bad Tuesday burned 38 minutes; Wednesday pipeline blocked all feature merges; team fixed the pool bug; budget recovered; postmortem fed into canary gates; velocity restored.

**Failure Scenarios:** Freeze policy invoked but leadership overrides ad hoc (credibility dies — or never adopt it); budget computed over too-long a window hides a slow bleed; budget resets monthly causing "spend it in week 1" behavior (rolling windows prevent); no gaming protection (deploying during budget flush then claiming credit); quoting budget but never enforcing → worse than none; measuring budget by LB 5xx only, missing app-level corruption.

**Best Practices:** Pre-negotiated policy with product/eng leadership; rolling 30d multi-window burn alerts (fast page, slow ticket); deploy gates consult budget; weekly review slackbot; incidents always charged against the budget (owner); categorize spend (deploy vs dependency vs bug); publish weekly.

**Anti-Patterns:** Budgets on paper only; "100% reliability" targets; manual override habit; hiding incidents; counting only hard downtime (ignore slow, wrong responses); per-team budgets with no shared accountability.

**Trade-offs:** Performance (n/a); complexity (policy + platform); cost (minimal); consistency (policy discipline); maintainability (culture > tooling).

**Testing:** Synthetic burn drill (inject 5xx → alert + deploy gate trip); monthly budget report verified against logs; freeze-gate integration test; audit of charges vs incidents.

**Related Concepts:** `#63 SLOs`, `#64 SLIs`, `#62 Alerts`, `#109 Production Incidents`, `#53 Canary Releases`, `#66 Observability`.

**Decision Criteria:** Use when: you have SLOs. Do not use when: no SLO maturity (don't start with budgets before SLIs exist). Alternatives: simple freeze rules tied to change failure rate; CAB boards (weaker, human-gated).


### 66. Observability

**Definition:** The property of a system whose internal state can be understood from its outputs — logs, metrics, traces — enabling answers to questions you did **not** anticipate at design time.

**Problem:** Monitoring tells you a known failure happened; observability lets you ask "why did *this* request fail for *this* customer?" — without new instrumentation being deployed after the fact.

**Internal Working:** Three pillars (correlated via trace_id): metrics (aggregates), logs (events), traces (request trees) — plus **high-cardinality, high-dimensionality** querying (Honeycomb/ClickHouse) where you slice by any dimension (user_id, deploy_sha, region) for unknown-unknowns. Events with wide context beat rigid dashboards. Practical differentiators: trace every request, structured logs with rich context, RED metrics, exemplars jumping metric→trace, and **correlation first** — every signal carries the same trace_id/service/environment.

**Architecture:** OTel SDK everywhere → collector → metrics (Prom/Mimir) + logs (Loki) + traces (Tempo) → single Grafana; or Honeycomb/Datadog as integrated platforms.

**Implementation:**

```python
# minimum viable correlation: one trace_id across everything
id = request.headers.get("X-Trace-Id") or uuid4().hex
log = structlog.get_logger().bind(trace_id=id)
log.info("request_in", route=path, method=method)
with tracer.start_as_current_span("handler"):
    ...
```

**Production Example:** "Checkout failed for user 8832 at 14:02" — one click: trace shows 240ms in `payment.authorize` 401 from provider X for that BIN → merchant-side expired card mapping; no new logging needed; 15 minutes to resolution.

**Failure Scenarios:** Pillars deployed but not correlated (metrics/logs/traces in separate universes); sampling deletes the exact trace you need (head-based 1% random); dashboard-only culture (known-unknowns only); PII leakage in spans/logs (guard with redaction at collector); "observability" = one Grafana with 60 panels nobody opens; no ownership, no query training → Slack questions go unanswered; treating observability as a purchase instead of a practice (needs onboarding, runbooks, exemplars from day one).

**Best Practices:** Correlation via trace_id everywhere; wide structured events; tail sampling for errors; exemplars on latency/error metrics; dashboards for known-unknowns + query power for unknown-unknowns; observability requirements in PR review; incident follow-ups add missing telemetry (not just alerts); train every engineer to query; postmortem tag "observability gap".

**Anti-Patterns:** Logging pyramids, uncorrelated pillars; high-cardinality panic banning user_id everywhere (instead: bounded via sampling/Honeycomb-style columns); alert-only mentality; observability as a one-time purchase; no redaction (PII in spans = breach).

**Trade-offs:** Performance (1-3% overhead); complexity (collector + stores + training); cost (storage is real — sample judiciously); consistency (UTC + trace_id); maintainability (needs ownership and process, but pays back in every incident).

**Testing:** "Can we answer: why did request X fail?" drill on staging; correlation assertion in CI (log line ↔ span share trace_id); sampling verification; PII scan; unpredictable-question exercise in game days.

**Related Concepts:** `#58 Monitoring`, `#59 Logging`, `#60 Distributed Tracing`, `#61 Metrics`, `#63 SLOs`, `#109 Production Incidents`, `#111 Postmortems`.

**Decision Criteria:** Use when: any real production system — always. Do not use when: n/a. Alternatives: simple correlation only (cheap but weak); managed unified platforms (Honeycomb, Datadog) vs best-of-breed open stack.

<!--END-->

