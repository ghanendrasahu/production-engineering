# Networking & Communication Reference

Client↔server communication primitives — real-time push channels, transport protocols, DNS, API evolution, and release semantics.

| # | Concept | One-line use case |
|---|---|---|
| 22 | WebSockets | Persistent full-duplex connection |
| 23 | Long Polling | Fallback when WebSockets can't be used |
| 24 | Server-Sent Events | One-way server push over HTTP |
| 97 | DNS | Name→address resolution |
| 98 | TCP vs UDP | Reliable stream vs datagrams |
| 99 | HTTP/2 & HTTP/3 | Multiplexed modern HTTP transports |
| 100 | gRPC | Typed RPC over HTTP/2 + protobuf |
| 101 | Webhooks | Server-to-server event callbacks |
| 102 | API Versioning | Evolve APIs without breaking clients |
| 103 | Semantic Versioning | Meaningful version numbers |

### 22. WebSockets

**Definition:** A protocol (RFC 6455) that upgrades an HTTP connection to a persistent, bidirectional message channel; both sides can send frames anytime.

**Problem:** Polling for live updates wastes bandwidth and adds latency; pure HTTP request/response cannot push — chat, presence, dashboards, and live inference token streams need a persistent channel.

**Internal Working:** Handshake (HTTP Upgrade + `Sec-WebSocket-Key` → 101 Switching Protocols); persistent TCP with framed messages (masked client→server); ping/pong keepalive; permessage-deflate compression optional; connection state lives in memory — load balancing with sticky sessions (or a pub/sub fanout like Redis) for multi-replica. Scaling: 10k-100k connections per node possible (event loops), but cross-node messages need a shared bus (Redis, NATS, Kafka).

**Architecture:** Client ⇄ WS gateway/server (FastAPI WebSockets/uvicorn behind Nginx with `Upgrade`/`Connection` headers) ⇄ Redis/NATS pubsub ⇄ backends.

**Implementation:**

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

**Production Example:** Live trading UI: 30k concurrent WS clients across 6 nodes; Redis fanout broadcasts ticks; presence via heartbeat map; reconnect with backoff + snapshot+deltas resume (client stores last seen sequence); deploy drains via close frame.

**Failure Scenarios:** Idle connections killed by proxy/LB idle timeout (ping every 30s); no backpressure → fast producer melts slow client (bounded send buffer, drop policy); deploy drops all sockets (drain + client backoff + resume token); memory per connection ×100k; auth checked once at handshake, not re-checked; cross-node messages lost without shared bus; someone already implemented this with polling "temporarily".

**Best Practices:** App-level ping/pong + idle timeouts; bounded buffers with drop-oldest/disconnect-on-overflow; auth at handshake + periodic revalidation; resume protocol (sequence + replay); sticky or bus fanout; close codes + reasons; WS-aware load balancing (least connections); metrics: connections, send queue, broadcast rate.

**Anti-Patterns:** Unbounded send queues; no ping/pong; broadcast without fanout in multi-node; auth never expires mid-connection; reconnecting clients hammering (thundering herd after restart — jitter backoff); using WS for everything including CRUD.

**Trade-offs:** Performance (best latency, persistent overhead per connection); complexity (high — state, scale, drain, resume); cost (idle connections consume slots/memory); consistency (ordering per connection only); maintainability (dedicated channel discipline).

**Testing:** pytest + httpx-ws/ASGI transport; connection-storm test (5k opens); kill-server resume test (client reconnects with last-seq, assert no gap); slow-client backpressure test; idle-timeout test.

**Related Concepts:** `#24 Server-Sent Events` (simpler one-way alternative), `#3 Load Balancing` (stickiness), `#9 Service Discovery`, `#44 Backpressure`, `#96 Clock Skew` (heartbeat timeouts).

**Decision Criteria:** Use when: bidirectional realtime (chat, collaboration, games, live status). Do not use when: server-only push (SSE simpler); request/response (HTTP); rare updates (polling). Alternatives: `#24 Server-Sent Events`, `#23 Long Polling`, WebTransport, managed Ably/Pusher.

### 23. Long Polling

**Definition:** A client requests an update; the server holds the request open until data is available (or a timeout), responds, and the client immediately re-requests — emulating push with plain HTTP.

**Problem:** Environments where WebSockets/SSE are blocked or impractical (ancient proxies, restrictive corporate networks) still need near-realtime updates.

**Internal Working:** Client GET /events?since=seq → server awaits new event bounded by ~25-30s → 200 with payload or 204 no-change → client re-polls immediately. Latency ≈ polling interval only during idle; updates arrive in ≤1 RTT when active. Server side: `asyncio.Event` per connection or DB LISTEN/NOTIFY; bounded waits prevent pinned workers (always timeout).

**Architecture:** Same-origin SPA/page -> long-held HTTP GET (25s) -> app async waiters on an in-process Event bus or DB LISTEN/NOTIFY; reconnect with `since` cursor; sits behind the same proxy with no Upgrade handling required.

**Implementation:**

```python
@app.get("/events")
async def events(since: int = 0):
    event = await asyncio.wait_for(event_bus.wait_for(since), timeout=25)
    return event
```

**Production Example:** Legacy intranet dashboard: 2k viewers, push every ~10s; long polling via uvicorn workers (2s wait budget) behind same-origin — corporate proxy allowed only plain HTTP/1.1 GET; updates effectively <100ms when active; fallback tier for clients failing WS negotiation.

**Failure Scenarios:** Pinned workers (wait_for without timeout); stampede on reconnect (exponential backoff + jitter mandatory); 204 storms burning CPU; header payload limits; proxies buffering and reordering responses; client re-poll loop without jitter after outage; missed events between polls (sequence numbers/`since` mandatory).

**Best Practices:** Bounded wait ≤ 25s (<LB idle); sequence/`since` tokens; backoff+jitter on errors; return empty 204 cleanly; cap concurrent long-poll connections per client; monitor hold time; use only as fallback tier.

**Anti-Patterns:** Infinite wait; no sequence; hot-loop repoll on error; thousands of parked workers eating thread pool (async required); polling when SSE/WS viable.

**Trade-offs:** Performance (near-realtime, more requests than WS); complexity (simple — works anywhere); cost (one connection per client for 25s — pool math matters); consistency (ordered per session); maintainability (easy to implement, annoying at huge scale).

**Testing:** Hold-and-release test; timeout test (25s expiry → 204); reconnect storm test; `since` resume consistency test; LB idle interaction test.

**Related Concepts:** `#22 WebSockets`, `#24 Server-Sent Events`, `#11 Timeouts`, `#44 Backpressure`, `#99 HTTP/2 & HTTP/3`.

**Decision Criteria:** Use when: WS/SSE blocked and near-realtime required, or fallback tier. Do not use when: WS works (use it); high update frequency + many clients (SSE/WS scale better). Alternatives: `#22 WebSockets`, `#24 Server-Sent Events`, page refresh.

### 24. Server-Sent Events

**Definition:** A one-way HTTP stream (`text/event-stream`) from server to client — the standard answer for server→client push when the client doesn't need to send anything back.

**Problem:** Streaming LLM tokens, progress bars, live logs, and notifications need push; WebSockets are bidirectional overhead for one-way data; SSE is a plain HTTP response that auto-reconnects natively.

**Internal Working:** `Content-Type: text/event-stream`; events framed as `id:`/`event:`/`data:` lines, blank-line separated; ends only when connection closes; browser `EventSource` auto-reconnects with `Last-Event-ID` on drop (server can replay from that id). Flow: long-lived HTTP/1.1 response (or HTTP/2 stream), chunk-flushed per event; heartbeats (`: ping`) every 15-30s to survive proxies. HTTP/2 multiplexes many SSE streams on one connection (100-stream limit, fine for most clients).

**Architecture:** Browser EventSource -> HTTP/2 response stream (`text/event-stream`) -> async generator flushed per token; Nginx/proxy must disable buffering; resume via `Last-Event-ID`.

**Implementation:**

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

**Production Example:** LLM `/v1/chat` on SSE: first token p50 350ms, heartbeat every 10s, `id:` = chunk sequence so reconnect resumes mid-stream; disconnects auto-resume; CDN unable to cache (no-cache) with buffering disabled; 12k concurrent streams across 8 pods — HTTP/2 and async handlers essential.

**Failure Scenarios:** Proxy buffering → client sees nothing until completion (set X-Accel-Buffering: no / proxy_buffering off); idle timeout kills silent streams > LB idle (heartbeats mandatory); EventSource auto-reconnect without Last-Event-ID → duplicate prefix replayed (dedupe by id); clients reconnecting in a storm (server-side shedding: 503 before accepting); text/event-stream through a JSON API gateway that expects `application/json` → 415; SSE on HTTP/1.1 with >6 connections per domain (browser cap — h2 needed).

**Best Practices:** Heartbeat comments every 10-30s; `id:` on every event; honor `Last-Event-ID` for resume; no buffering headers; clients limit reconnect rate; async generator flush per chunk; cap stream duration (server closes at N minutes with retry-after hint); metrics on active streams + bytes.

**Anti-Patterns:** Bidirectional use; no heartbeats; buffering proxies; forgetting Last-Event-ID; SSE for rare notifications (polling simpler); per-chunk flush through sync frameworks.

**Trade-offs:** Performance (excellent one-way stream; h2 multiplex); complexity (low — plain HTTP); cost (one long-lived response per client); consistency (ordered stream; resume semantics app-defined); maintainability (trivially debuggable with curl).

**Testing:** curl -N asserting chunk delivery; kill client mid-stream → resume from Last-Event-ID; heartbeat absence test; proxy chain test (Nginx in between); load with 5k streams; backpressure test on slow client.

**Related Concepts:** `#22 WebSockets`, `#23 Long Polling`, `#99 HTTP/2 & HTTP/3`, `#91 Latency`, `#11 Timeouts`.

**Decision Criteria:** Use when: server→client push (LLM tokens, notifications, progress). Do not use when: bidirectional messaging (WS); tiny occasional updates (polling); IE/ancient clients (polyfill or fallback). Alternatives: `#22 WebSockets`, Web Push, managed streaming services.

### 97. DNS

**Definition:** The hierarchical distributed database mapping human-readable names to IP addresses (and other records), with caching resolvers at every level.

**Problem:** Without DNS you hardcode IPs — every failover, migration, and CDN cutover breaks; DNS is also a frequent root cause of "everything is down but nothing changed (CDN TTL expired)".

**Internal Working:** Resolution chain (recursive resolver → root → TLD → authoritative); record types: A/AAAA (address), CNAME (alias), ALIAS/ANAME (apex alias), MX (mail), TXT (verification), SRV (service+port), NS. TTL governs cache lifetime (30s–24h); negative caching; round-robin and latency-based/failover routing policies (Route 53/Cloud DNS); DNSSEC signs records (integrity). Common failure: TTL set to 1h during an outage pointing at the dead IP (launch day TTL should be ≤60s until stable).

**Architecture:** Stub resolver (OS/app) -> recursive resolver (ISP/1.1.1.1/8.8.8.8) -> root -> TLD -> authoritative; TTL-bound caches at every level; failover/latency routing policies at the authoritative layer.

**Implementation:**

```
Route 53 failover policy: PRIMARY health-checked record → ALB; SECONDARY → static S3 status page
TTL: 60s for app endpoints; 300-3600s for stable infra; 5s for migration cutovers
_ dig +trace app.example.com      # see the actual delegation chain
```

**Production Example:** Primary region loss: health check marks record unhealthy in 30s; resolver caches refresh within TTL 60s; traffic shifts to us-east-1; TTL 300s would have meant 5 extra minutes of outage — TTL discipline paid off.

**Failure Scenarios:** TTL too long during cutover (stale IP); TTL too low (resolver load, slight latency); CNAME at apex (illegal — use ALIAS); forgetting to update DNS after LB IP change (control plane does it; manual doesn't); split-horizon misconfig (public resolver vs VPC resolver disagree); DNSSEC broken DS record → SERVFAIL everywhere; registrar lock/expiry (domain hijack risk); DNS as availability dependency (cache + secondary DNS provider).

**Best Practices:** Failover routing with independent health checks; low TTL for cutover windows; secondary DNS provider (different network); DNSSEC where supported; monitor with external probes (not just your authoritative); document delegation; avoid dangling CNAMEs to deprovisioned cloud resources (takeover risk!); health-check SB (state-based) not just TCP.

**Anti-Patterns:** Manual IP entries; TTL 86400 everywhere; single authoritative provider; dangling CNAMEs (self-serve subdomain takeover); no health checks on A records; expiry unmanaged (auto-renew domains).

**Trade-offs:** Performance (resolution cached; first-lookup RTT ~20-100ms); complexity (failover policy discipline); cost (tiny); consistency (TTL-bounded staleness); maintainability (IaC-managed DNS (Terraform) beats console).

**Testing:** External probes from 3 continents; failover drill (mark primary unhealthy, measure propagation); DNSSEC validation; dangling-record scanner; resolver-cache behavior test.

**Related Concepts:** `#85 Failover`, `#86 Multi-Region Deployment`, `#48 CDN`, `#4 Reverse Proxies`, `#97 DNS` + `#71 TLS` (cert SAN vs name), `#83 Disaster Recovery`.

**Decision Criteria:** Use when: n/a — DNS always exists; decisions are TTL/routing/DNSSEC. Do not use when: notice product-limitation: DNS not usable for sub-minute cutover — use accelerators/Anycast for that. Alternatives: global accelerator (health-checked, L4), service mesh, mDNS/internal discovery (K8s Services).

### 98. TCP vs UDP

**Definition:** TCP: connection-oriented, ordered, reliable, congestion-controlled byte stream. UDP: connectionless datagrams — no ordering, no delivery guarantee, no flow control, minimal overhead.

**Problem:** Picking the wrong transport loses latency/ordering needs or guarantees the wrong thing; both cross the same network, differently purposed.

**Internal Working:** TCP: 3-way handshake (1 RTT), sequence numbers + cumulative ACKs, retransmission (fast retransmit + RTO), congestion control (CUBIC/BBR), flow control window; head-of-line blocking across the single stream. UDP: send/receive, no state; app does its own reliability if needed. QUIC (HTTP/3) runs over UDP with its own reliability + multiplexed streams — no TCP HOL blocking, faster (0-RTT) handshake with TLS 1.3. Choose by: need ordered reliable bytes → TCP (HTTP, DB); need minimal latency and tolerate loss → UDP (voice, video, game state — WebRTC); need reliability without TCP's constraints → QUIC/HTTP3.

**Architecture:** Transport layer only: TCP(HTTP/DB/Redis clients) and UDP(DNS, WebRTC media, QUIC) share IP; choice happens per socket; middleboxes and firewalls filter differently per protocol — verify both traverse paths.

**Implementation:**

```python
import socket
# UDP: sendto, no connect; dedupe/reorder yourself
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# TCP: connect once (with timeout!), Nagle off for latency-critical
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
```

**Production Example:** Voice calls over UDP (WebRTC): a lost packet retransmitted is useless (late > lost) — jitter buffer absorbs; backend API remains TCP/TLS/HTTP2; DNS lookups over UDP with TCP fallback (truncation/TC bit); internal metrics over UDP push (loss acceptable, no backpressure) — with 1% loss fine.

**Failure Scenarios:** TCP HOL blocking under loss (one lost segment stalls all streams — HTTP/2 suffers; HTTP/3 fixes); UDP firewalled by corporate networks (fallback path needed); MTU blackholing; SYN backlog overflow (net.core.somaxconn); UDP sender flooding (no congestion control — small `send()` can saturate link); TCP retransmit ambiguity causing 200ms spikes; pooled TCP without keepalive → LB drops idle silently.

**Best Practices:** TCP for anything needing reliable ordered bytes (HTTP/DB/Redis clients); UDP only when loss-tolerant and latency-critical; enable TCP_NODELAY for request/response apps; keepalive < LB idle timeout; monitor retransmits; no-UDP-keep-it-except-QUIC discipline; firewall rule audits for UDP ports; for QUIC verify fallback to H2 (Alt-Svc).

**Anti-Patterns:** UDP without app-level sequence numbers for ordered needs; TCP for high-rate telemetry where loss is fine (bloated); QUIC everywhere without corp-network testing; ignoring TCP handshake latency for far replicas.

**Trade-offs:** Performance (UDP ~0 overhead vs TCP handshake+reliability); complexity (app-level reliability is hard); cost (n/a); consistency (TCP ordered; UDP none); maintainability (UDP debugging harder).

**Testing:** Packet loss injection test (toxiproxy); latency jitter measurements; firewall traversal test; QUIC vs H2 A/B; retransmit rate monitoring.

**Related Concepts:** `#99 HTTP/2 & HTTP/3`, `#97 DNS` (UDP+TCP), `#100 gRPC` (HTTP/2 over TCP), `#22 WebSockets` (TCP), `#75 DDoS Protection` (UDP floods).

**Decision Criteria:** Use when: transport design — TCP default; UDP for media/telemetry/QUIC. Do not use when: need reliable ordered delivery (don't force UDP). Alternatives: QUIC for new protocols, SCTP (rarely), HTTP/2 over TCP (the universal default).

### 99. HTTP/2 & HTTP/3

**Definition:** The modern binary HTTP transports. HTTP/2 (RFC 7540): multiplexed streams over one TCP connection with HPACK header compression. HTTP/3 (RFC 9114): same semantics over QUIC (UDP) — no TCP head-of-line blocking, faster handshakes, better mobility.

**Problem:** HTTP/1.1's one-request-per-connection serializes requests (6-connection cap), repeats headers, and wastes TLS re-handshakes; H2 multiplexes; H3 additionally fixes loss behavior and connection migration.

**Internal Working:** H2: single TCP + N concurrent streams, flow control per stream and connection, HPACK compresses headers, server push (deprecated-ish), ALPN negotiation (`h2`). H3: QUIC streams inside UDP datagrams; 0-RTT resume; connection IDs survive network changes (WiFi→4G); streams fully independent — one lost packet blocks only its stream; QPACK header compression. Encryption-in-QUIC is mandatory (always encrypted). Practice: enable H2 at the proxy (Nginx `listen ... http2`), H3 where clients support (CDN edge); origin hops can stay H1/H2.

**Architecture:** Negotiated via ALPN at TLS (`h2`/`h3`); terminated at CDN/edge LB, end-to-end or mesh internally; multiplexing happens inside one connection; origin hops usually stay h1/h2.

**Implementation:**

```nginx
listen 443 ssl http2;            # H2 terminated at edge
add_header Alt-Svc 'h3=":443"; ma=86400';   # advertise H3 upgrade
```

`curl --http3 -I https://app` to verify; keep origin H2 + keepalive.

**Production Example:** Asset-heavy page over H2: 40 requests over 1 connection, HPACK saves 70% header bytes; H3 on Cloudflare: p95 40→28ms on lossy mobile networks (1% loss kills H2, barely touches H3).

**Failure Scenarios:** H2 prioritizing browser bugs (nginx/nghttp2 old versions); HOL blocking under packet loss on H2 (H3 solves on lossy links); H2 behind LB with client resets (mitigate — use HTTP/2 end-to-end LB like AWS ALB); H3 fallback broken (Alt-Svc cached stale); buffering SSE/WS through H2 fine but not through broken middle-boxes; h2c vs tls confusion; HTTP/2 Rapid Reset DDoS (CVE-2023-44487 — patch and rate-limit resets).

**Best Practices:** H2 at proxy always; H3 at CDN; HPACK/keepalive everywhere; alert on 5xx + resets; keep-alive tuning; H3 verification in browser tests; don't force H3 on origin for micro-optimizations; patch for rapid-reset CVE.

**Anti-Patterns:** H1.1 end-to-end "because simple"; H2 via plaintext h2c without understanding; unpatched rapid-reset; assuming H3 everywhere works (corp proxies); enabling H2 + ignoring stream limits.

**Trade-offs:** Performance (large wins: multiplexing, compression, no HOL on H3); complexity (LB/CDN handles most); cost (free); consistency (same semantics); maintainability (enable and monitor).

**Testing:** curl --http2/--http3; browser waterfall comparison; loss injection (2% packet loss) comparing H2 vs H3; Rapid Reset regression (patched LB); keepalive reuse verification.

**Related Concepts:** `#98 TCP vs UDP`, `#4 Reverse Proxies`, `#48 CDN`, `#24 Server-Sent Events` (H2 multiplex), `#100 gRPC` (HTTP/2 foundation).

**Decision Criteria:** Use when: any internet-facing service — enable H2 (universal) and consider H3 at edge. Do not use when: internal single-connection simplicity is fine. Alternatives: H1 keep-alive (works, costs more), gRPC.

### 100. gRPC

**Definition:** A high-performance RPC framework: Protocol Buffers + HTTP/2 transport, generating typed clients/servers with unary, server-streaming, client-streaming, and bidirectional streaming methods.

**Problem:** REST's JSON + text HTTP is verbose and manual; internal services need typed contracts, streaming, and sub-millisecond overhead — hand-rolling that over JSON wastes engineering time and bandwidth.

**Internal Working:** `.proto` schema → generated stubs; binary protobuf (compact, fast encode/decode); HTTP/2 multiplex with deadlines/metadata; flow control; status codes (OK, INVALID_ARGUMENT, DEADLINE_EXCEEDED…); interceptors for auth/logging/metrics; load balancing: client-side via lookaside or L7 proxy (Envoy/Linkerd) since connections are long-lived; health checking protocol; reflection for debugging. Deadlines propagate through the chain (set once at ingress, all hops honor remaining budget).

**Architecture:** Schema (.proto) -> generated stubs -> HTTP/2 channels via LB/L7 proxy; deadlines and metadata propagate end-to-end; Envoy/mesh or client-side LB spread long-lived streams; gateway transcode (grpc-gateway) for public REST consumers.

**Implementation:**

```proto
service Orders { rpc GetOrder (GetOrderRequest) returns (Order); rpc Watch (OrderId) returns (stream OrderEvent); }
message GetOrderRequest { string id = 1; }
```

```python
# generated: OrderStub(channel).GetOrder(req, timeout=2.0)
channel = grpc.aio.insecure_channel("orders:50051")
resp = await stub.GetOrder(GetOrderRequest(id="o_9"), timeout=2.0)
```

**FastAPI Example:** FastAPI itself is HTTP — gRPC is a sibling server (serve both: `grpc.aio` on 50051 + FastAPI on 8000); or use `grpc-gateway` to expose REST transcoding for external clients.

**Production Example:** Internal `payment-authorize` p50 3ms (protobuf vs JSON); deadline propagation from gateway (2s budget) prevents orphaned work; streaming `Watch` replaced 2s polling for order status; Envoy LB spread long-lived connections across pods.

**Failure Scenarios:** Deadlines not propagated (whole chain hangs past caller's timeout); protobuf field number reuse breaking backcompat (never renumber; reserve removed tags); giant messages (4-8MB cap — chunk/stream); no server reflection in prod (debug pain); L4 LB with H2 long-lived connections → one pod saturated; error mapping to HTTP 5xx in gateway loses detail — map status codes deliberately; missing deadlines everywhere (default infinite hang).

**Best Practices:** Deadlines everywhere (start low, propagate); reserved field numbers; stream for large payloads; L7 LB (Envoy) or client-side LB; health checks via grpc.health.v1; protobuf lint (buf, breaking-change detection in CI); deadlines in SLOs; avoid message > 1MB; reflection in staging only.

**Anti-Patterns:** REST-over-grpc (GET-like RPC semantics ignored); unbounded streams without flow control; no deadlines; breaking protos without CI check; plaintext to internet; unversioned proto packages.

**Trade-offs:** Performance (fast, compact; browser clients need grpc-web/proxy); complexity (proto toolchain, codegen); cost (free); consistency (protobuf schema is the contract — evolve carefully); maintainability (excellent — one source of truth per contract).

**Testing:** buf breaking check in CI (buf breaking); integration against test server (grpcurl); deadline-cancellation test (client cancels mid-stream); load test with H2 multiplexing; contract suite per .proto; chaos: server killed mid-stream.

**Related Concepts:** `#99 HTTP/2 & HTTP/3`, `#11 Timeouts`, `#12 Retries`, `#101 Webhooks` (contrast sync vs async), `#100 gRPC` needs `#60 Distributed Tracing` for context, `#102 API Versioning` (proto evolution).

**Decision Criteria:** Use when: internal service-to-service RPC, streaming telemetry, strict contracts. Do not use when: browser-facing public APIs (REST/JSON fine; grpc-web awkward); simple CRUD teams unfamiliar with proto; human-debuggable APIs matter. Alternatives: REST+JSON, GraphQL, ConnectRPC, Twirp.

### 101. Webhooks

**Definition:** HTTP callbacks: a service POSTs a signed event payload to a URL you register — server-to-server push replacing polling of the provider's API.

**Problem:** Polling `GET /orders/:id` every 5s wastes both sides and adds lag; webhooks deliver the fact once, as it happens.

**Internal Working:** Provider → your HTTPS endpoint with JSON body + signature headers (Stripe: `Stripe-Signature: t=…,v1=…` HMAC-SHA256 of `t.body` with your signing secret; GitHub `X-Hub-Signature-256`). Security steps in order: raw body (before parsing!) → verify HMAC → constant-time compare → timestamp freshness (replay protection ±5min) → validate schema → **respond 2xx fast** → process async via queue. Delivery is at-least-once: expect duplicates — dedupe by event id. Failing endpoint → provider retries with backoff (Stripe: 3 days) then may disable it.

**Architecture:** Provider -> your public HTTPS endpoint -> signature verify + dedupe -> enqueue (202) -> async worker processes; egress-allowlisted sender; results recorded for audit and redrive.

**Implementation:**

```python
@app.post("/webhooks/stripe")
async def stripe_hook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    event = stripe.Webhook.construct_event(body, sig, WEBHOOK_SECRET)  # raises on bad sig
    dedupe_key = f"wh:{event.id}"
    if not redis.set(dedupe_key, "1", nx=True, ex=86400): return {"ok": True}  # dup
    celery.send_task("tasks.process_payment_event", args=[event.to_dict()])
    return {"ok": True}
```

**FastAPI Example:** Above; always: idempotent consumer + DLQ + redrive; respond before processing (avoid provider timeouts → redelivery storms).

**Production Example:** Payments via Stripe: 40% of order confirmations arrive via webhook vs redirect (user closed tab); HMAC verified, dedup by event.id (TTL 7d), processed via Celery; endpoint hinted at `orders-svc:443/webhooks/stripe` via egress allowlist; average delivery 300-900ms; redelivery storm during an outage handled by dedupe.

**Failure Scenarios:** Responding after processing (provider timeout → retries → duplicates; dedupe still catches it — but queue bloats); signature verified AFTER json parsing applied to raw body (must verify bytes); missing replay-timestamp check (old captured request replayed); endpoint returns 500 (provider disables after repeated failures — alert); schema drift (provider adds fields — additive only, tolerate); no dedupe (double charge!); webhook URL enumeration (use unguessable path or mTLS); secret committed in repo.

**Best Practices:** HMAC verify (raw body, constant-time, timestamp window); dedupe by event id with TTL; fast 2xx + async processing; DLQ + redrive tooling; alert on repeated 4xx/5xx from provider; signature secret rotation with overlap window; schema-tolerant parsing; test endpoint from provider CLI; monitor delivery lag.

**Anti-Patterns:** Parsing before verifying; 200-after-processing; processing inline of 30s webhook timeout; trusting payload fields without signature; no dedupe; exposing webhook path publicly with weak secret; 5xx on nonfatal event types.

**Trade-offs:** Performance (push = zero polling waste; async processing mandatory); complexity (moderate — crypto + queues); cost (tiny); consistency (at-least-once — embrace it with idempotency); maintainability (provider docs + tests per provider).

**Testing:** pytest with generated valid/invalid HMAC; replay old timestamp → reject; duplicate delivery → single processing; processing-failure → DLQ; provider test-mode deliveries; end-to-end with stripe-cli/github-cli.

**Related Concepts:** `#14 Idempotency`, `#20 Dead Letter Queues`, `#15 Message Queues`, `#73 Encryption in Transit`, `#80 SSRF` (keep webhook egress allowlisted).

**Decision Criteria:** Use when: provider supports webhooks — always enable alongside redirects. Do not use when: fully internal flows where you control both sides and durability needs exceed provider retry horizon. Alternatives: polling (last resort), provider-managed sync APIs, message buses for internal events.

### 102. API Versioning

**Definition:** The practice of evolving APIs while keeping existing clients working — by path (`/v1/`), header (`Accept: application/vnd.app.v2+json`), or date — with a documented deprecation lifecycle.

**Problem:** Breaking clients silently erodes trust; versioning gives everyone a migration runway and the provider a way to move forward.

**Internal Working:** Path versioning: `/v1/orders` and `/v2/orders` — visible, cacheable, simple, most common. Header/content negotiation: cleaner URLs, harder to test/debug. Date-based (Stripe: `2026-10-01`): strong immutability per release. Contract rules: additive changes free (new optional fields); breaking changes (renamed fields, removed endpoints, changed semantics, required new fields) require new version. Deprecation: `Sunset` + `Deprecation` headers (RFC 8594), 12-month window, docs + SDK bumps + migration guides, metrics per version to know who's left. Never: silent behavior change behind same version.

**Architecture:** Gateway/router maps version → handler; shared business logic underneath both versions; contract tests per version; error format stable across versions.

**Implementation:**

```python
router_v1 = APIRouter(prefix="/v1")
router_v2 = APIRouter(prefix="/v2")
app.include_router(router_v1); app.include_router(router_v2)
@app.middleware("http")
async def sunset_header(request, call_next):
    r = await call_next(request)
    if request.url.path.startswith("/v1/"): r.headers["Sunset"] = "Sat, 30 Oct 2027 00:00:00 GMT"; r.headers["Deprecation"] = "true"
    return r
```

**Production Example:** v2 introduces required `idempotency_key` on POST /charges; shipped alongside v1; 14 months migration; per-version metrics show v1 traffic 40%→3%; deprecation emails; Sunset header live; v1 removed after SLA window; mobile clients guided via SDK min-version.

**Failure Scenarios:** Breaking change under same version; versioning only some endpoints (half-versioned API); unbounded version count (v1..v9 all live forever); missing Sunset communication; v2 = rewrite with drift (logic diverges — share core code); deprecating without telemetry (who is left?); date versioning with undated clients (guess which behavior).

**Best Practices:** Path versioning for simplicity; additive-only within a version; deprecation policy with Sunset headers; shared core, thin adapters; per-version usage metrics; contract tests per version; 12-month minimum deprecation for public APIs; document every breaking change; SDK bumps follow API releases.

**Anti-Patterns:** Header-only versioning invisible in URLs; breaking change Friday; v1 never removed; implicit latest; inconsistent error shapes across versions.

**Trade-offs:** Performance (none meaningful); complexity (parallel maintenance of versions — minimize lifetime); cost (some CI time ×2); consistency (discipline); maintainability (good when practiced, rot without hygiene policy).

**Testing:** Contract tests per version (schema validation); Sunset headers asserted; migration soak (v1 clients against v2 via adapter); usage metric assertions; rollback test (v2 flag off).

**Related Concepts:** `#103 Semantic Versioning`, `#5 API Gateways`, `#51 Feature Flags`, `#81 Database Migrations` (expand/contract mirrors this), `#100 gRPC` (proto evolution rules).

**Decision Criteria:** Use when: any API consumed by others — always. Do not use when: pure internal prototyped API that will be rewritten (but you'll regret it). Alternatives: date versioning (Stripe), media-type negotiation (GitHub/v3+json), additive-only + flags for internal services.

### 103. Semantic Versioning

**Definition:** `MAJOR.MINOR.PATCH` (semver 2.0.0): MAJOR = incompatible API changes, MINOR = backwards-compatible features, PATCH = backwards-compatible fixes — a machine- and human-readable change contract.

**Problem:** Without meaning in version numbers, dependency resolution is guesswork; one bump can silently break a fleet — semver makes compatibility explicit and tooling trustworthy.

**Internal Working:** Rules: 0.x = initial dev (anything may change); 1.0.0 first stable; MAJOR bump for breaks; MINOR for additions; PATCH for fixes. Pre-release tags: `1.4.0-rc.1`. Build metadata after `+`. Ranges in manifests (`^1.4.0` = any ≥1.4 <2.0; `~` = patch-level) interact with lockfiles (poetry.lock/uv.lock/package-lock) — lockfiles pin exact, constraints allow compatible; libraries publish semver; apps lock. Deprecation inside semver: mark deprecated in docs, remove only on MAJOR.

**Architecture:** Convention inside every published artifact: version lives in packaging metadata (pyproject/package.json), git tags, registry artifacts and changelogs; consumers express intent as semver ranges; lockfiles pin exactness for apps.

**Implementation:**

```
pyproject.toml: version = "2.3.1"
^2.3.1  → allows 2.4.0, never 3.0.0
git tag v2.4.0 → CI builds & publishes; changelog from conventional commits
```

Conventional Commits (`feat:`/`fix:`/`feat!:`) automate bump selection.

**Production Example:** Internal SDK `orders-client`: semver enforced by `semantic-release` in CI; dependabot proposes only patch/minor automatically; MAJOR upgrades arrive as planned migrations with codemods; zero surprise breaks in 6 services across 4 months.

**Failure Scenarios:** Breaking change in MINOR ("it's only adding a header" — it wasn't); 0.x forever (users fear upgrades — fine, but be honest about stability); lockfile ignored (production ≠ tested version); releasing 1.0.0 prematurely (compat burden); version bumps by one dev without review; changelog inconsistent with tags; transitive deps floating (`latest`) — untraceable builds.

**Best Practices:** Conventional commits + automated release; lockfiles for apps, semver ranges for libraries; `feat!`/`BREAKING CHANGE:` signals MAJOR; deprecate before remove; pin CI tools; verify upgrade in staging before automerge (dependabot grouping); changelog per release; security patches as PATCH promptly.

**Anti-Patterns:** Manual version bumps; `^0.x` assumptions (0.y.z is all-breaking); `latest` in prod; breaking change snuck in MINOR; tags and pyproject drift; no lockfile in app repos.

**Trade-offs:** Performance (n/a); complexity (tooling + discipline); cost (free); consistency (contract across ecosystem); maintainability (massive — upgrades become predictable).

**Testing:** CI gates: lockfile freshness, changelog presence, semver lint (commit analyzer); staging ingest of new minor; consumer contract tests (Pact) across dependent services.

**Related Concepts:** `#102 API Versioning`, `#6 CI/CD`, `#106 Helm Charts`, `#107 Build Caching`, `#108 Dependency Hell`, `#81 Database Migrations`.

**Decision Criteria:** Use when: any published library or internal SDK/service artifact — always. Do not use when: n/a (it's a convention; use it). Alternatives: date versioning (CalVer — good for apps/distributions like Ubuntu), 0.x for honest instability.

<!--END-->
