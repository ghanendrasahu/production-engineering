---
topic: 23
title: Long Polling
category: A
skill: production-engineering
status: stable
---

# 023 — Long Polling

## 1. Topic name and metadata

- **Number:** 23 of 111
- **Title:** Long Polling
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [networking-apis.md](../references/networking.md)
- **Topic file:** `.agents/skills/production-engineering/topics/023-long-polling.md`

## 2. What it is

A client requests an update; the server holds the request open until data is available (or a timeout), responds, and the client immediately re-requests — emulating push with plain HTTP.

## 3. Why it exists

Some environments cannot hold a socket but still need near-realtime.

## 4. The engineering problem it solves

Environments where WebSockets/SSE are blocked or impractical (ancient proxies, restrictive corporate networks) still need near-realtime updates.

## 5. How it works internally

Client GET /events?since=seq → server awaits new event bounded by ~25-30s → 200 with payload or 204 no-change → client re-polls immediately. Latency ≈ polling interval only during idle; updates arrive in ≤1 RTT when active. Server side: `asyncio.Event` per connection or DB LISTEN/NOTIFY; bounded waits prevent pinned workers (always timeout).

## 6. Architecture and design principles

Same-origin SPA/page -> long-held HTTP GET (25s) -> app async waiters on an in-process Event bus or DB LISTEN/NOTIFY; reconnect with `since` cursor; sits behind the same proxy with no Upgrade handling required.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

WS/SSE blocked and near-realtime required, or fallback tier.

## 8. When NOT to use it

WS works (use it); high update frequency + many clients (SSE/WS scale better).

**Alternatives:** `#22 WebSockets`, `#24 Server-Sent Events`, page refresh.

## 9. Implementation strategies

```python
@app.get("/events")
async def events(since: int = 0):
    event = await asyncio.wait_for(event_bus.wait_for(since), timeout=25)
    return event
```

## 10. Production-grade implementation

**Scenario:** Legacy intranet dashboard: 2k viewers, push every ~10s; long polling via uvicorn workers (2s wait budget) behind same-origin — corporate proxy allowed only plain HTTP/1.1 GET; updates effectively <100ms when active; fallback tier for clients failing WS negotiation.

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

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Fallback transport when WS is blocked (rare on corp networks) — viable degraded mode for live dashboards; not for token streams at scale.

## 15. Security considerations

Sanitize error bodies — long-poll responses must not leak stack details.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Infinite wait; no sequence; hot-loop repoll on error; thousands of parked workers eating thread pool (async required); polling when SSE/WS viable.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `longpoll_wait_seconds`, held-connection count, timeout rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Hold-and-release test; timeout test (25s expiry → 204); reconnect storm test; `since` resume consistency test; LB idle interaction test.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Bounded wait ≤ 25s (<LB idle)
- [ ] Sequence/`since` tokens
- [ ] Backoff+jitter on errors
- [ ] Return empty 204 cleanly
- [ ] Cap concurrent long-poll connections per client
- [ ] Monitor hold time
- [ ] Use only as fallback tier.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Pinned workers (wait_for without timeout); stampede on reconnect (exponential backoff + jitter mandatory); 204 storms burning CPU; header payload limits; proxies buffering and reordering responses; client re-poll loop without jitter after outage; missed events between polls (sequence numbers/`since` mandatory).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/Using_XMLHttpRequest

**Related topics in this library:** `#22 WebSockets`, `#24 Server-Sent Events`, `#11 Timeouts`, `#44 Backpressure`, `#99 HTTP/2 & HTTP/3`.
