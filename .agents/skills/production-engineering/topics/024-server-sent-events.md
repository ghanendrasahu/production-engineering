---
topic: 24
title: Server-Sent Events
category: A
skill: production-engineering
status: stable
---

# 024 — Server-Sent Events

## 1. Topic name and metadata

- **Number:** 24 of 111
- **Title:** Server-Sent Events
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [networking-apis.md](../references/networking.md)
- **Topic file:** `.agents/skills/production-engineering/topics/024-server-sent-events.md`

## 2. What it is

A one-way HTTP stream (`text/event-stream`) from server to client — the standard answer for server→client push when the client doesn't need to send anything back.

## 3. Why it exists

One-way push is common; sockets are the wrong tool for it.

## 4. The engineering problem it solves

Streaming LLM tokens, progress bars, live logs, and notifications need push; WebSockets are bidirectional overhead for one-way data; SSE is a plain HTTP response that auto-reconnects natively.

## 5. How it works internally

`Content-Type: text/event-stream`; events framed as `id:`/`event:`/`data:` lines, blank-line separated; ends only when connection closes; browser `EventSource` auto-reconnects with `Last-Event-ID` on drop (server can replay from that id). Flow: long-lived HTTP/1.1 response (or HTTP/2 stream), chunk-flushed per event; heartbeats (`: ping`) every 15-30s to survive proxies. HTTP/2 multiplexes many SSE streams on one connection (100-stream limit, fine for most clients).

## 6. Architecture and design principles

Browser EventSource -> HTTP/2 response stream (`text/event-stream`) -> async generator flushed per token; Nginx/proxy must disable buffering; resume via `Last-Event-ID`.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Server→client push (LLM tokens, notifications, progress).

## 8. When NOT to use it

Bidirectional messaging (WS); tiny occasional updates (polling); IE/ancient clients (polyfill or fallback).

**Alternatives:** `#22 WebSockets`, Web Push, managed streaming services.

## 9. Implementation strategies

```python
from fastapi.responses import StreamingResponse
import json, asyncio

@app.get("/stream")
async def stream():
    async def gen():
        yield ":ok\n\n"                                  # comment heartbeat
        async for chunk in llm.astream(prompt):
            yield f"id: {chunk.id}\ndata: {json.dumps({'token': chunk.text})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

Nginx: `proxy_buffering off`. Client: `const es = new EventSource("/stream")`.

## 10. Production-grade implementation

**Scenario:** LLM `/v1/chat` on SSE: first token p50 350ms, heartbeat every 10s, `id:` = chunk sequence so reconnect resumes mid-stream; disconnects auto-resume; CDN unable to cache (no-cache) with buffering disabled; 12k concurrent streams across 8 pods — HTTP/2 and async handlers essential.

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

Canonical transport for LLM token streaming: text/event-stream, heartbeat comments, `id:` per chunk + Last-Event-ID resume; cancels upstream on disconnect.

## 15. Security considerations

Tenant-scope SSE channels — shared channels leak other users' progress/data.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Bidirectional use; no heartbeats; buffering proxies; forgetting Last-Event-ID; SSE for rare notifications (polling simpler); per-chunk flush through sync frameworks.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `sse_streams_active`, bytes_streamed, reconnect rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

curl -N asserting chunk delivery; kill client mid-stream → resume from Last-Event-ID; heartbeat absence test; proxy chain test (Nginx in between); load with 5k streams; backpressure test on slow client.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Heartbeat comments every 10-30s
- [ ] `id:` on every event
- [ ] Honor `Last-Event-ID` for resume
- [ ] No buffering headers
- [ ] Clients limit reconnect rate
- [ ] Async generator flush per chunk
- [ ] Cap stream duration (server closes at N minutes with retry-after hint)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Proxy buffering → client sees nothing until completion (set X-Accel-Buffering: no / proxy_buffering off); idle timeout kills silent streams > LB idle (heartbeats mandatory); EventSource auto-reconnect without Last-Event-ID → duplicate prefix replayed (dedupe by id); clients reconnecting in a storm (server-side shedding: 503 before accepting); text/event-stream through a JSON API gateway that expects `application/json` → 415; SSE on HTTP/1.1 with >6 connections per domain (browser cap — h2 needed).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://developer.mozilla.org/en-US/docs/Web/API/EventSource
- https://www.rfc-editor.org/rfc/rfc6202

**Related topics in this library:** `#22 WebSockets`, `#23 Long Polling`, `#99 HTTP/2 & HTTP/3`, `#91 Latency`, `#11 Timeouts`.
