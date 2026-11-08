---
topic: 22
title: WebSockets
category: A
skill: production-engineering
status: stable
---

# 022 — WebSockets

## 1. Topic name and metadata

- **Number:** 22 of 111
- **Title:** WebSockets
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [networking-apis.md](../references/networking.md)
- **Topic file:** `.agents/skills/production-engineering/topics/022-websockets.md`

## 2. What it is

A protocol (RFC 6455) that upgrades an HTTP connection to a persistent, bidirectional message channel; both sides can send frames anytime.

## 3. Why it exists

Request/response cannot push; some features need a live channel.

## 4. The engineering problem it solves

Polling for live updates wastes bandwidth and adds latency; pure HTTP request/response cannot push — chat, presence, dashboards, and live inference token streams need a persistent channel.

## 5. How it works internally

Handshake (HTTP Upgrade + `Sec-WebSocket-Key` → 101 Switching Protocols); persistent TCP with framed messages (masked client→server); ping/pong keepalive; permessage-deflate compression optional; connection state lives in memory — load balancing with sticky sessions (or a pub/sub fanout like Redis) for multi-replica. Scaling: 10k-100k connections per node possible (event loops), but cross-node messages need a shared bus (Redis, NATS, Kafka).

## 6. Architecture and design principles

Client ⇄ WS gateway/server (FastAPI WebSockets/uvicorn behind Nginx with `Upgrade`/`Connection` headers) ⇄ Redis/NATS pubsub ⇄ backends.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Bidirectional realtime (chat, collaboration, games, live status).

## 8. When NOT to use it

Server-only push (SSE simpler); request/response (HTTP); rare updates (polling).

**Alternatives:** `#24 Server-Sent Events`, `#23 Long Polling`, WebTransport, managed Ably/Pusher.

## 9. Implementation strategies

```nginx
location /ws/ { proxy_pass http://app; proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }
```

```python
from fastapi import WebSocket
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    pubsub = redis.pubsub(); await pubsub.subscribe("feed")
    async for msg in pubsub.listen():
        await websocket.send_text(msg["data"])
```

## 10. Production-grade implementation

**Scenario:** Live trading UI: 30k concurrent WS clients across 6 nodes; Redis fanout broadcasts ticks; presence via heartbeat map; reconnect with backoff + snapshot+deltas resume (client stores last seen sequence); deploy drains via close frame.

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

Voice agents and collaborative UIs need bidirectional channels; SSE is preferable for pure token streaming — WebSockets add stickiness and fanout burden.

## 15. Security considerations

Handshake-time auth only — re-validate on long-lived connections.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Unbounded send queues; no ping/pong; broadcast without fanout in multi-node; auth never expires mid-connection; reconnecting clients hammering (thundering herd after restart — jitter backoff); using WS for everything including CRUD.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `ws_connections_active`, send-queue depth, `ws_broadcasts_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest + httpx-ws/ASGI transport; connection-storm test (5k opens); kill-server resume test (client reconnects with last-seq, assert no gap); slow-client backpressure test; idle-timeout test.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] App-level ping/pong + idle timeouts
- [ ] Bounded buffers with drop-oldest/disconnect-on-overflow
- [ ] Auth at handshake + periodic revalidation
- [ ] Resume protocol (sequence + replay)
- [ ] Sticky or bus fanout
- [ ] Close codes + reasons
- [ ] WS-aware load balancing (least connections)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Idle connections killed by proxy/LB idle timeout (ping every 30s); no backpressure → fast producer melts slow client (bounded send buffer, drop policy); deploy drops all sockets (drain + client backoff + resume token); memory per connection ×100k; auth checked once at handshake, not re-checked; cross-node messages lost without shared bus; someone already implemented this with polling "temporarily".
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.rfc-editor.org/rfc/rfc6455
- https://developer.mozilla.org/en-US/docs/Web/API/WebSocket

**Related topics in this library:** `#24 Server-Sent Events` (simpler one-way alternative), `#3 Load Balancing` (stickiness), `#9 Service Discovery`, `#44 Backpressure`, `#96 Clock Skew` (heartbeat timeouts).
