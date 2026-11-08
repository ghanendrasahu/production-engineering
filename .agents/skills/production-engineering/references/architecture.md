# Architecture Reference — Backend & API Engineering

Resilience and traffic-management patterns for services sitting between clients and data stores: rate limiting, caching, load balancing, proxies, gateways, timeouts, retries, idempotency, background jobs, and discovery.

| # | Concept | One-line use case |
|---|---|---|
| 1 | Rate Limiting | Protect services from overload and abuse |
| 2 | Caching | Serve hot reads without hitting the origin |
| 3 | Load Balancing | Spread traffic across replicas |
| 4 | Reverse Proxies | Terminate TLS, route, and shield origins |
| 5 | API Gateways | Single entry for routing, auth, and quotas |
| 9 | Service Discovery | Find healthy instances dynamically |
| 10 | Circuit Breakers | Stop cascading failures to a sick dependency |
| 11 | Timeouts | Bound every remote wait |
| 12 | Retries | Recover from transient failures |
| 13 | Exponential Backoff | Retry without synchronizing a thundering herd |
| 14 | Idempotency | Make repeats of an operation safe |
| 21 | Cron Jobs | Time-based batch and maintenance work |

### 1. Rate Limiting

**Definition:** A control that bounds how many requests a client or operation may make per time window, rejecting or delaying excess traffic.

**Problem:** One buggy client, noisy tenant, or bot can exhaust database connections and CPU, degrading the service for everyone and inflating cost. LLM endpoints make this worse: each abandoned request may still bill tokens.

**Internal Working:** Token bucket (refill at a steady rate, burst up to bucket size) and sliding-window log/counter (count requests in the trailing window) are the two dominant designs. Leaky bucket smooths output to a constant rate. Implementations store counters in Redis with atomic `INCR`+`EXPIRE` or a Lua script that performs check-and-decrement atomically; local-memory buckets work per-instance but under-count globally and drift on scale-out.

**Architecture:** Enforced at three layers — edge (CDN/WAF), gateway (per-tenant quotas, API keys), and service middleware (per-user/per-route limits). Position matters: edge rejects cheaply before consuming origin capacity.

**Implementation:** Redis Lua token bucket; response headers `X-RateLimit-Limit/Remaining/Reset` and `Retry-After: 37`; return HTTP 429 with a problem+json body. For FastAPI, slowapi (limits) or a custom dependency works; for Nginx, `limit_req_zone`.

```
redis-cli SCRIPT LOAD ... ; EVALSHA <sha> 1 ratelimit:user:42 100 1
```

```python
import time, redis
r = redis.Redis(decode_responses=True)
LUA = """local t=redis.call('HMGET',KEYS[1],'ts','tokens'); local now=tonumber(ARGV[3]); local win=tonumber(ARGV[1]); local rate=tonumber(ARGV[2]); local ts=tonumber(t[1]) or now; local tok=tonumber(t[2]) or rate; local refill=(now-ts)*rate/win; tok=math.min(rate,tok+refill); if tok>=1 then tok=tok-1; redis.call('HMSET',KEYS[1],'ts',now,'tokens',tok); redis.call('EXPIRE',KEYS[1],win*2); return {1,math.floor(tok)} else return {0,math.floor((1-tok)*win/rate)} end"""
allowed, info = r.eval(LUA, 1, "rl:u:42", 60, 60, int(time.time()))
```

**FastAPI Example:**

```python
from fastapi import FastAPI, Depends, HTTPException, Request

async def rate_limit(request: Request):
    ok, retry_after = check_bucket(request.client.host)
    if not ok:
        raise HTTPException(429, detail="rate limit exceeded", headers={"Retry-After": str(retry_after)})

@app.get("/api/search", dependencies=[Depends(rate_limit)])
async def search(q: str): ...
```

**Production Example:** 30k QPS API with a public search endpoint: edge WAF caps 500 req/s per IP, gateway caps 10k/day per API key tier, Redis-backed per-user limit 60 req/min on `/v1/generate`. Zombies retrying do not pass the gateway because 429s are not retried blindly by well-behaved clients.

**Failure Scenarios:** Counter drift under clock skew across Redis multi-instance → users bypass limits; shared global key without TTL leaks memory; limiting only per-IP → NAT'd corporate networks blocked; limiting writes but not reads → database still dies on read storms; returning 200 with empty body instead of 429 confuses clients.

**Best Practices:** Return `Retry-After` and clear 429s; separate limits per route class (read vs write); rate-limit at the earliest layer; use Redis Lua for atomicity; make limits configurable via env; expose limit state in headers; exempt health checks; alert on sustained 429 rates.

**Anti-Patterns:** Fixed-window counters (boundary bursts at window edges); in-process counters in a multi-replica deployment; rate-limiting after the expensive work ran; a single global limit for everything; no 429 body; silently queueing instead of rejecting.

**Trade-offs:** Performance (Redis round trip per request, mitigated by in-memory short windows) vs correctness; complexity (Lua script + fallback if Redis is down — always fail-open with local bucket or fail-closed for abuse-sensitive endpoints); cost (Redis ops); consistency (near-exact globally vs approximate locally); maintainability (one config per route class).

**Testing:** pytest with fakeredis asserting the Nth+1 request is rejected; concurrent test with 50 threads hammering one key; verify `Retry-After` header value; load test to confirm gateway sheds rather than origin falling over.

**Related Concepts:** `#3 Load Balancing`, `#4 Reverse Proxies`, `#5 API Gateways`, `#11 Timeouts`, `#44 Backpressure`, `#75 DDoS Protection`, `#90 Serverless Limits` (LLM quotas).

**Decision Criteria:** Use when: public API, expensive endpoints, multi-tenant SaaS, LLM/token cost control, abuse response. Do not use when: internal single-process jobs with bounded concurrency (use backpressure instead); as the only protection against a DDoS (use edge/CDN). Alternatives: queue-based smoothing, autoscaling headroom, `#44 Backpressure` inside the service.

### 2. Caching

**Definition:** Storing the result of expensive work close to consumers so repeat requests are served cheaply and quickly, with a defined freshness and eviction policy.

**Problem:** Every read hitting the database or an LLM re-pays full cost and latency; hot data causes lock and CPU contention; origin outages become user-facing outages if there is no cached fallback.

**Internal Working:** Cache-aside (check cache → miss → fetch origin → set with TTL), read-through (cache fetches on miss), write-through (write cache and origin synchronously), write-back (write cache now, origin async — fastest, least durable). Eviction: LRU/LFU, TTL expiry, explicit invalidation. `stale-while-revalidate` serves the stale value while refreshing asynchronously; single-flight locks prevent cache stampedes (thundering herd) when a hot key expires.

**Architecture:** Browser cache → CDN → reverse proxy cache (Nginx `proxy_cache`) → application cache (in-process, e.g. lru_cache) → shared Redis/Memcached → database buffer pool → read replicas. Placement higher up serves more traffic with less origin cost.

**Implementation:** Redis for shared app cache; key design `service:entity:id:v3` with version in key for cheap "invalidation"; TTL jitter (base ± random) to avoid synchronized expiry; single-flight via `SET NX PX` or `cachelock`; negative caching for 404s with short TTL.

```python
import json, time, hashlib, redis
r = redis.Redis(decode_responses=True)

def get_user(uid: int):
    key = f"user:{uid}:v2"
    hit = r.get(key)
    if hit:
        return json.loads(hit)
    lock = r.set(f"lock:{key}", "1", nx=True, px=2000)
    row = db_fetch(uid)               # origin
    if row is None:
        r.setex(key, 30, "null")      # negative cache
        return None
    r.setex(key, 300 + int(time.time() * 1000) % 60, json.dumps(row))
    if lock:
        r.delete(f"lock:{key}")
    return row
```

**FastAPI Example:** Response-level caching middleware that hashes the path+query and sets `Cache-Control: public, max-age=60, stale-while-revalidate=300`, returning `304 Not Modified` on `If-None-Match` with a stored ETag.

**Production Example:** Product catalog: 40k QPS reads, 50 QPS writes. Redis cache-aside, TTL 5 min + jitter, 97% hit ratio; origin Postgres load drops from 40k to ~1.2k QPS. LLM response cache on SHA-256 of normalized prompt + model + temperature saved 34% of token spend on a support bot.

**Failure Scenarios:** Hot key expires and 5k concurrent requests hit the origin (stampede) — mitigate with single-flight lock or early revalidation; stale data served after a write — mitigate with write-through or tag-based invalidation; cache poisoning by unvalidated input keys; unbounded memory growth (no maxmemory policy) evicting useful keys LRU-wise; per-user data under a shared key leaking across users.

**Best Practices:** Cache-aside + explicit TTL as the default; version keys for deploy-time invalidation; tag-based invalidation for lists/aggregates; jitter TTLs; monitor hit ratio and eviction count; set `maxmemory` and `maxmemory-policy allkeys-lru`; cache negative results briefly; never cache personalized responses under a shared public key.

**Anti-Patterns:** Caching without an invalidation strategy; caching everything "just in case"; infinite TTLs with no eviction policy; caching error responses; using the cache as the source of truth; cache-aside on write-heavy paths where the miss cost exceeds the value.

**Trade-offs:** Performance (10-100x read speedup) vs consistency (stale reads); complexity (invalidation is the hard part — Phil Karlton's "two hard things"); cost (Redis memory + extra hop); maintainability (key versioning and observability of hit rates mandatory).

**Testing:** pytest with fakeredis: miss path calls origin once, second call is a hit; TTL jitter verified; invalidation after write test; stampede test with one key expiring under 20 concurrent asyncio requests and assert origin called once.

**Related Concepts:** `#2 Caching` pairs with `#50 Cache Invalidation`, `#49 Edge Caching`, `#48 CDN`, `#38 Distributed Locks` (single-flight), `#28 Connection Pooling`, `#44 Backpressure`.

**Decision Criteria:** Use when: read-heavy workload on stable data, expensive computation (LLM calls, reports, joins), per-key hotness known. Do not use when: data must be strongly consistent (balances, inventory counts) without invalidation; write frequency exceeds read frequency; dataset is tiny. Alternatives: read replicas (`#29 Read Replicas`), denormalization, view materialization.

### 3. Load Balancing

**Definition:** Distributing incoming connections or requests across multiple backend instances so no single instance is overwhelmed and failed instances stop receiving traffic.

**Problem:** A single instance caps throughput and is a single point of failure; uneven load wastes capacity and causes tail-latency spikes even when averages look fine.

**Internal Working:** Algorithms — round robin (equal), weighted round robin (heterogeneous capacity), least-connections (sends to the least busy), IP hash/consistent hashing (session stickiness), random (surprisingly competitive at scale). L4 balancers forward TCP/UDP flows (fast, no content awareness); L7 balancers terminate HTTP/gRPC (route on path/headers, health-check semantically, inject headers). Health checks mark backends up/down; outlier detection ejects flapping instances.

**Architecture:** Edge LB (cloud ELB/NLB) → app replicas behind an L7 proxy (Nginx/Envoy/Traefik) → service instances → database with its own pool. Health check path (`/healthz`) informs the LB.

**Implementation:** Nginx `upstream { least_conn; server a:8000 max_fails=3 fail_timeout=30s; keepalive 64; }`; Kubernetes `Service` (kube-proxy iptables/IPVS, round-robin per connection); cloud ALB for gRPC/HTTP with target groups and 30s health checks.

```nginx
upstream api { least_conn;
  server 10.0.1.11:8000 max_fails=3 fail_timeout=30s;
  server 10.0.1.12:8000 max_fails=3 fail_timeout=30s;
  keepalive 64; }
server { location / { proxy_pass http://api; } }
```

**Python Example:** None — load balancing is infrastructure; verify from the app with `httpx.AsyncClient` against the VIP and observe connection reuse.

**FastAPI Example:** Run behind `uvicorn --workers N` (per-machine, not a substitute for LB) or gunicorn `-k uvicorn.workers.UvicornWorker`; rely on the LB for cross-instance balancing; keep `/healthz` cheap (no DB hit) and `/readyz` for dependency checks.

**Production Example:** 4 FastAPI replicas behind an ALB, least-connections, target-tracking health checks every 10s, 2 consecutive failures → deregister. p99 dropped from 800ms to 180ms after switching from round robin to least-connections because two replicas were slower (GC pauses) and kept accumulating connections.

**Failure Scenarios:** Sticky sessions via IP hash pinning users to a dying replica; health check endpoint that touches the DB → every replica goes "down" together during a DB blip and traffic collapses to zero; `keepalive` too low causing TIME_WAIT exhaustion; uneven weight config after a canary deploy; LB itself a SPOF (use multi-AZ LB).

**Best Practices:** Least-connections for long-lived or variable-cost requests; dumb fast L4 for gRPC streams when L7 not needed; health checks must test real readiness (but not hard dependencies); set `max_fails`/`fail_timeout`; enable connection keepalive to backends; multi-AZ; monitor per-backend request rate and error rate.

**Anti-Patterns:** Single LB instance without redundancy; no health checks (routing to dead nodes); least-connections on L4 TCP with cookie-based stickiness semantics confused; health check = full DB query; weights set once and forgotten.

**Trade-offs:** Performance (negligible overhead at L4, ~0.3-1ms at L7); complexity (minimal, built into cloud); cost (LCU/hour charges); consistency (none — stateless required); maintainability (infra-as-code, health check contracts documented).

**Testing:** Kill a replica and confirm no 5xx (health check removal time); load test verifying even p95 across backends; verify keepalive reuse with `tcpdump` or access logs; failure injection via toxiproxy for flaky-backend behavior.

**Related Concepts:** `#4 Reverse Proxies`, `#45 Autoscaling`, `#46 Horizontal Scaling`, `#56 Health Checks`, `#85 Failover`, `#9 Service Discovery`.

**Decision Criteria:** Use when: more than one replica (always in production), blue-green/canary traffic splitting, heterogeneous backends. Do not use when: single local dev instance; sessions in-process without externalization (fix the app, not the LB). Alternatives: client-side load balancing (gRPC), DNS round-robin, service mesh (Envoy/Istio).

### 4. Reverse Proxies

**Definition:** A server positioned in front of application origins that accepts client requests, performs cross-cutting duties (TLS termination, routing, caching, compression, security headers), and forwards to the origin.

**Problem:** Applications shouldn't implement TLS termination, WAF rules, compression, and routing themselves; origins need protection from direct exposure and a stable public identity.

**Internal Working:** Terminates TLS (handshake, cert chain, SNI-based virtual hosting, HTTP/2 h2 or HTTP/3 QUIC), rewrites/headers (Host, X-Forwarded-For), routes by path/host/header to upstreams, optionally caches responses (shared cache key), enforces limits (client body size, rate limit), buffers (for slow clients, proxy buffering saves origin from holding connections).

**Architecture:** Client → CDN/edge → reverse proxy (Nginx/Traefik/Envoy/HAProxy) → upstream app → database. Often the same process is both LB and TLS terminator.

**Implementation:** Nginx: `proxy_pass`, `proxy_set_header X-Forwarded-Proto $scheme`, `proxy_cache_path`, `gzip on`, `server_tokens off`, TLS via certbot (Let's Encrypt) or cloud cert manager; TLS 1.2/1.3 only; HSTS; OCSP stapling.

```nginx
server { listen 443 ssl http2; server_name app.example.com;
  ssl_certificate /etc/letsencrypt/live/app/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/app/privkey.pem;
  add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
  location / { proxy_pass http://upstream; proxy_set_header Host $host;
               proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; } }
```

**Python Example:** N/A (infrastructure); verify app behavior behind a proxy by trusting `X-Forwarded-Proto/For` only from a known proxy — FastAPI/Starlette `TrustedHostMiddleware` + `forwarded_allow_ips` in uvicorn.

**FastAPI Example:**

```python
# uvicorn --proxy-headers --forwarded-allow-ips '*' app:app
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="10.0.0.0/8")
```

**Production Example:** Nginx terminates TLS, gzips, serves `/static` directly (expires 1 year), proxies `/api` to 4 FastAPI replicas with `proxy_cache` on `/api/products` (10s TTL, 94% hit), client max body 10MB. TLS handshake cost amortized by keepalive; p50 static asset latency falls from 40ms to 8ms.

**Failure Scenarios:** Proxy buffers a streaming response and breaks SSE/LLM token streaming (must set `proxy_buffering off` / `X-Accel-Buffering: no`); `X-Forwarded-For` trusted from anywhere → IP spoofing for rate limits/audit; TLS cert expiry not monitored → total outage; `client_max_body_size` rejecting legitimate uploads (413); upstream timeout lower than app's internal timeout → 504 while app completes work.

**Best Practices:** Terminate TLS at proxy with cert automation (certbot/ACME) or cloud LB; hide versions (`server_tokens off`); add security headers (CSP, HSTS, X-Content-Type-Options); HTTP/2 or HTTP/3; `proxy_read_timeout` ≥ app's longest internal deadline; `proxy_buffering off` for streaming; monitor cert expiry.

**Anti-Patterns:** Passing TLS straight through without inspection (sometimes correct, but you lose routing); proxying trust headers blindly; proxy as single point of failure without HA; serving dynamic apps with caching on by default; misconfigured buffering breaking streaming.

**Trade-offs:** Performance (fast native proxy vs app doing TLS); complexity (one extra layer, mature); cost (negligible; LB/proxy instance charges); security (attack surface reduced but a misconfig exposes everything); consistency (proxy-layer caching can serve stale).

**Testing:** `curl -I https://app` verify HSTS/headers; 413 test with oversized body; streaming test confirming tokens flush (SSE/LLM); cert expiry alert test; upstream kill test to confirm502/504 behavior and recovery.

**Related Concepts:** `#3 Load Balancing`, `#48 CDN`, `#49 Edge Caching`, `#71 TLS`, `#74 WAF`, `#22 WebSockets` (proxy upgrade headers), `#24 Server-Sent Events`.

**Decision Criteria:** Use when: any production deployment (basically always), TLS termination, static file offload, caching, WAF. Do not use when: pure L4 internal service-to-service (mTLS mesh may be better). Alternatives: cloud LB (ALB/NLB), Traefik (K8s-native), Envoy, CDN edge.
### 5. API Gateways

**Definition:** A single managed entry point for client APIs that centralizes cross-cutting concerns — routing, authentication, authorization, rate limiting, quotas, transformation, and observability — and routes requests to backend services.

**Problem:** Without a gateway, every service re-implements auth, rate limits, and logging; clients must know every service address; security policy drifts per-service; internal topology leaks to clients.

**Internal Working:** Accepts all external traffic on one hostname, resolves route rules (path/method/host) to an upstream, applies a filter/middleware chain (TLS termination → WAF → authN (JWT/API key/mTLS) → authZ (scopes/RBAC) → rate limit/quota → request transformation (header injection, path rewrite) → forward), applies response policies (CORS, caching, header stripping), and emits metrics/traces keyed by route. Modern gateways (Kong, Envoy, Tyk, AWS API Gateway, cloud LB) run as plugins over a shared dataplane.

**Architecture:** Client → DNS → CDN → gateway → services (or monolith) → databases/queues. Internal service-to-service calls usually bypass the gateway.

**Implementation:** Kong on Kubernetes (Ingress or Gateway API) with plugins: `rate-limiting`, `jwt`, `key-auth`, `cors`, `prometheus`, `request-transformer`. OpenAPI contract per route; CI validates spec and pushes config. AWS API Gateway for serverless: stage variables, usage plans, API keys, Lambda integrations, custom domain.

```yaml
# Kong declarative config (kong.yml) excerpt
services:
- name: users-api
  url: http://users-svc:8000
  routes: [{ name: users, paths: ["/v1/users"], methods: [GET, POST] }]
  plugins:
  - name: rate-limiting
    config: { minute: 100, policy: redis, redis_host: redis }
  - name: jwt
```

**Python Example:** Client-side route helper fetching config; more usefully, verifying the gateway injected identity: `request.headers["X-User-Id"]` signed by the gateway between gateway and services.

**FastAPI Example:**

```python
from fastapi import FastAPI, Header, HTTPException
import hmac, hashlib
async def verified_user(x_user_id: str = Header(...), x_signature: str = Header(...)):
    # trust only traffic from the gateway (signed, shared secret or mTLS)
    expected = hmac.new(SECRET, x_user_id.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_signature):
        raise HTTPException(401, "untrusted caller")
    return int(x_user_id)
```

**Production Example:** 12 backend services behind Kong: one `kong.yml` in Git, CI lints it, per-route quotas (free tier 100/day, pro 100k), JWT verification at gateway so backends receive only `X-User-Id`/`X-Scopes`, CORS centralized, `/healthz` bypassed. Partner onboarding = add an API key + usage plan, zero code changes.

**Failure Scenarios:** Gateway becomes a SPOF or bottleneck (payloads, no keepalive, insufficient replicas); gateway outage blocks everything (region failover needed); secret leak in gateway config; authZ rules in gateway disagree with service-level checks (defense-in-depth still required); gateway retries upstreams causing double charges; request transformation bug silently drops headers (e.g. idempotency key).

**Best Practices:** Centralize authN at gateway, keep authZ close to data too; validate and strip inbound headers; idempotency key pass-through; circuit breaker per upstream; budget and benchmark gateway CPU; dashboard per route (RPS, p95, 5xx); gateway config in Git with review; canary config changes; plan gateway capacity for 3x peak.

**Anti-Patterns:** Business logic in the gateway (transformations only); no fallback auth in services (gateway-only security); single global quota; gateway config hot-patched in production without PR; exposing internal service URLs to mobile apps.

**Trade-offs:** Performance (extra hop ~1-3ms, offloads backends); complexity (one more mature component, well-known ops); cost (managed gateway fees or K8s resources); consistency (single enforcement point vs drift); maintainability (config as code beats 12 duplicated middleware stacks).

**Testing:** Contract-test routes in CI; integration tests against a gateway test instance; chaos test: take one upstream down → expect 502 only on its route; load test validating quota counters; verify header stripping at the edge.

**Related Concepts:** `#1 Rate Limiting`, `#3 Load Balancing`, `#4 Reverse Proxies`, `#67 Secrets Management`, `#69 OAuth`, `#102 API Versioning`, `#76 CORS`.

**Decision Criteria:** Use when: multiple backends or clients, multi-tenant quotas, public API program, serverless. Do not use when: a single modular monolith with 2 routes and one consumer — Nginx is enough; internal East-West traffic better served by a mesh. Alternatives: service mesh (Envoy/Istio), cloud LB + app middleware, Nginx with Lua.

### 9. Service Discovery

**Definition:** The mechanism by which services locate the network addresses of their dependencies dynamically, so instances can come and go without static configuration.

**Problem:** Hardcoded IPs/hostnames break deployments, autoscaling, failover, and blue-green rollouts; manual address management causes 100% outages when an instance dies and traffic still routes to it.

**Internal Working:** Client-side discovery (client queries registry — Consul/Eureka/etcd — and load-balances itself) vs server-side discovery (LB/router queries the registry or K8s Services route via iptables/IPVS DNAT to pod IPs). Registrations happen on startup with TTL/heartbeat leases (Consul session TTL, K8s readiness gates); deregistration is automatic on health failure. DNS is the universal baseline (SRV/A records, e.g. `headless` Services in K8s); watches (etcd watch/Consul blocking queries) push updates instead of polling.

**Architecture:** Service A → resolver/registry (K8s API, Consul, etcd) → healthy instances of Service B. In K8s this is free: `ClusterIP` + `Service` + probe-driven endpoint removal from EndpointSlices.

**Implementation:** Kubernetes: create `Service` + Deployment; use `http://users-svc.payments.svc.cluster.local:8000`; headless service for direct pod discovery (gRPC client-side LB). Consul: `consul agent -dev`, services registered via annotations/config, `consul.watch` in clients. etcd: lease + keepalive, `Watch` on prefix for endpoints. Application must gracefully deregister on shutdown (drain + SIGTERM hook).

**Python Example:**

```python
import httpx
async def call_users_service(path: str):
    # K8s DNS round-robin; refresh connections so pod changes are picked up
    async with httpx.AsyncClient(timeout=2.0, limits=httpx.Limits(max_keepalive_connections=20)) as c:
        return await c.get(f"http://users-svc.prod.svc.cluster.local:8000{path}")
```

**FastAPI Example:** Read peer URLs from env (`USERS_SVC_URL=http://users-svc:8000`) injected by the platform — K8s DNS resolves at connect time; do not resolve once and cache forever; for gRPC use `dns:///` targets.

**Production Example:** Blue-green deploy of the `orders` service: new pods pass readiness → EndpointSlice adds IPs → all proxies receive endpoints within seconds; old pods deregister and connections drain via preStop hook + termination grace. Zero hardcoded addresses anywhere.

**Failure Scenarios:** Consul agent dies → stale views and split-brain membership; readiness probe too shallow (TCP-only) keeps routing to broken pods; DNS TTL too high caches dead endpoints; client caches registry snapshot without refresh; simultaneous all-replicas deregister during a full rollout → 503 storm; `headless` service used by a non-LB client → all traffic to one pod.

**Best Practices:** Let the platform do discovery (K8s Services) before building your own; deregister on SIGTERM (preStop sleep + grace period); keep TTLs small with lease renewal; health checks orthogonal to discovery; client-side: shuffle endpoints; export resolution latency/errors; document the registry as a critical dependency and test its failure mode.

**Anti-Patterns:** Static IPs in config; discovery without health filtering; heartbeat intervals >> MTTR requirements; custom registry built in-house before evaluating K8s/Consul; discovery lookups on the hot path without caching (N+1 network calls).

**Trade-offs:** Performance (registry lookup cost; mitigated by long-lived connections and client caches); complexity (platform-provided in K8s ≈ free; self-hosted registry is real ops burden); consistency (endpoints are eventually consistent — brief window of dead-endpoint traffic); maintainability (config-driven > code-driven).

**Testing:** `dig SRV users-svc...` lists only ready pods; kill a pod mid-traffic and confirm no client errors after deregistration; registry-failure test (stop Consul) verifying cached fallback and alert; rollout drill measuring time-to-100%-routing.

**Related Concepts:** `#3 Load Balancing`, `#45 Autoscaling`, `#56 Health Checks`, `#57 Liveness & Readiness Probes`, `#8 Kubernetes`, `#85 Failover`.

**Decision Criteria:** Use when: any environment with ephemeral instances (K8s, autoscaling, containers) — i.e., always outside static VMs. Do not use when: a single-host monolith; stable VM fleet without containers (static config acceptable). Alternatives: DNS (K8s headless), K8s Gateway API, cloud service maps, Consul Connect/mesh.

### 10. Circuit Breakers

**Definition:** A client-side pattern that tracks failures to a dependency and, after a threshold, short-circuits calls (fails fast without sending them) for a cooldown period, then half-opens to probe recovery.

**Problem:** When a dependency is sick, callers otherwise pile up: threads/connections blocked on timeouts, retries amplifying load, and the failure cascading into every upstream until the whole system is down.

**Internal Working:** Three states — CLOSED (normal, count failures), OPEN (fail fast immediately for a cooldown, no network call), HALF-OPEN (allow one/few trial calls; success → CLOSED, failure → OPEN again). Counter thresholds (e.g., 50% of 20 requests in 10s, or N consecutive failures), plus optional sliding-window metrics. Implementations: pybreaker, resilience4j (JVM), Envoy outlier detection, K8s → Istio `outlierDetection` or `DestinationRule`.

**Architecture:** Client library wraps the dependency client (database, HTTP, gRPC, Redis, LLM provider) between business logic and the network stack. Sits alongside timeouts and retry logic — retries without a breaker are an amplifier.

**Implementation:**

```python
import pybreaker, time
brk = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30, exclude=[ValueError])

@brk
def charge(card: str, amount: int) -> dict:
    return payment_client.post("/charge", json={"card": card, "amount": amount})
```

For async: wrap with a manual counter or use `aiobreaker`. Envoy: `outlier_detection: { consecutive_5xx: 5, interval: 10s, base_ejection_time: 30s }`.

**FastAPI Example:**

```python
from fastapi import HTTPException
@app.post("/orders")
async def create_order(order: Order):
    try:
        return await checkout(order)
    except pybreaker.CircuitBreakerError:
        raise HTTPException(503, "payment provider degraded - try again later")
```

**Production Example:** Payment provider starts returning 500s with 100% error rate. Breaker (fail_max=20 over 10s, reset 30s) opens after ~2s; upstream `POST /checkout` p95 falls from 30s to 2ms; alert fires; when provider recovers, half-open trial succeeds and breaker closes. Without it, uvicorn worker pool exhausted and the whole API went down.

**Failure Scenarios:** Breaker opens but alert is noisy and ignored; reset_timeout too long → half-open probe too rare; per-instance breakers in 30 replicas each needing 5 failures → provider melts before opening globally (use Envoy or shared Redis counter); breaker used for non-transient errors (bad input 500s) opens needlessly — exclude expected client errors; half-open allows full flood of traffic through one slow endpoint.

**Best Practices:** Always pair breaker + timeout + bounded retries; exclude 4xx from failure counting; metric per dependency (`breaker_state{dep="payments"}`); alert on OPEN; fallback path (serve cached/degraded response); open on slow calls too (latency breaker); test half-open behavior; tune reset_timeout ~ dependency MTTR.

**Anti-Patterns:** Retry storm without a breaker; breaker with threshold so high it never opens; treating deterministic 400s as failures; no fallback — just exceptions; reset_timeout = forever; breaker per app instance without aggregate protection for a shared dependency.

**Trade-offs:** Performance (fail-fast frees resources; breaker overhead negligible); complexity (modest; a library); cost (avoids overload cost of cascading calls); consistency (fail-fast serves errors/degraded responses — require fallback design); maintainability (one decorator/wrapper per dependency).

**Testing:** Unit test with a fake client failing N times → assert breaker opens, calls short-circuit, half-open probe after reset_timeout; integration test against toxiproxy-injected 500s; chaos test in staging verifying error rate drops and recovery closes the breaker.

**Related Concepts:** `#11 Timeouts`, `#12 Retries`, `#13 Exponential Backoff`, `#56 Health Checks`, `#10 Circuit Breakers` composes with `#55 Rollbacks` during deploys.

**Decision Criteria:** Use when: any remote dependency that can be slow/down (third-party API, shared DB under contention), high-QPS services. Do not use when: purely local calls; one-shot batch scripts; idempotent reads where simple retry suffices and timeout is tiny. Alternatives: load-shed via `#44 Backpressure`, mesh-level outlier detection, bulkheads (separate pools per dependency).

### 11. Timeouts

**Definition:** A bound on how long an operation may wait for a result before it is abandoned with an error; every blocking operation that crosses a process or network boundary must have one.

**Problem:** Without timeouts, a hung dependency holds threads, connections, and transactions indefinitely; resources exhaust, and the whole service becomes unresponsive rather than failing a single request.

**Internal Working:** Client-side deadline propagation (gRPC deadline, `context.Context.WithDeadline`, `asyncio.wait_for`, `httpx.AsyncClient(timeout=…)`); server-side: request budget enforced by the framework (uvicorn `--timeout-keep-alive`, K8s `terminationGracePeriodSeconds`). Timers must account for the **entire** path: connect, TLS handshake, wait-for-first-byte, response body. Set the caller's timeout ≥ the sum of internal timeouts along the path plus slack — never smaller than what downstream needs, or you get 504s on work that will still complete (wasted).

**Architecture:** Every hop sets and passes budgets: gateway 30s → service A (25s) → service B (10s) → DB statement timeout 5s. Enforce at each client wrapper (DB pool `statement_timeout`, HTTP client, queue consume deadline).

**Implementation:** PostgreSQL: `statement_timeout = '5s'` per role/session; SQLAlchemy: `connect_timeout=5` and engine `pool_timeout=30`; httpx: `timeout=httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=1.0)`; asyncpg/asyncio: `asyncio.wait_for(coro, 5)`; Redis client `socket_timeout=2`; Celery `task_time_limit=300`; Kafka consumer `max.poll.interval.ms`.

```python
import httpx
async with httpx.AsyncClient(timeout=httpx.Timeout(connect=2.0, read=8.0, write=5.0, pool=2.0)) as client:
    r = await client.post(url, json=payload)
```

**FastAPI Example:**

```python
import asyncio
from fastapi import HTTPException
@app.post("/summarize")
async def summarize(doc: str):
    try:
        return await asyncio.wait_for(llm.complete(doc), timeout=45.0)
    except asyncio.TimeoutError:
        raise HTTPException(504, "model timed out - retry shortly")
```

**Production Example:** Checkout chain: ALB idle 60s → service 20s end-to-end → inventory gRPC 2s, pricing 3s, payments 10s → Postgres `statement_timeout=8s`. Payments latency degraded to 12s; timeouts shed fail-fast instead of hanging the pool; p99 capped at ~20s; partial-failure path returns "payment pending, we will reconcile".

**Failure Scenarios:** Cascading timeout violation — upstream caller times out before downstream finishes → duplicate side effects (pair with `#14 Idempotency`); timeout == retry budget misconfiguration (timeout smaller than backoff gap) causing spurious errors; default timeouts that are infinite (requests library default: forever); `statement_timeout` in the DB higher than the app's, so the app gives up but the query keeps running and holds locks; timeouts only on connect, never on read → classic hung-socket outage.

**Best Practices:** Budget the whole path and write it down; align timeouts: gateway > service > DB; timeout on connect, read, write, AND pool; propagate remaining budget via `X-Request-Timeout`/gRPC metadata; log timeout as a metric labeled by dependency; pair every timeout with a retry budget and idempotency; graceful deadline errors with `Retry-After`.

**Anti-Patterns:** Infinite defaults (`requests.get(url)` without timeout); one global timeout for all endpoints; timeout smaller than DNS resolve + TLS + first byte combined; retrying inside the timeout window wastefully; converting timeouts into silent empty responses; setting DB `statement_timeout` longer than the app's.

**Trade-offs:** Performance (fail-fast frees resources vs risk of cutting slow-but-successful work); complexity (simple to add, harder to tune coherently); cost (fewer hung resources); consistency (timed-out-but-committed writes need idempotency/reconciliation); maintainability (documented budget table in ADR).

**Testing:** pytest with monkeypatched slow client + `asyncio.wait_for` asserting TimeoutError path; toxiproxy-injected delays; verify `statement_timeout` kills the query with `pg_stat_activity`; load test confirming pool does not exhaust under dependency latency injection.

**Related Concepts:** `#12 Retries`, `#13 Exponential Backoff`, `#10 Circuit Breakers`, `#94 Tail Latency`, `#11 Timeouts` budgets flow into `#93 P99 Latency`.

**Decision Criteria:** Use when: always, for every outbound call and every database statement. Do not use when: truly indefinite batch work (use explicit kill-switch/cancellation instead). Alternatives: deadlines/cancellation tokens, `context` propagation, request budgets in the mesh.

### 12. Retries

**Definition:** Re-executing a failed operation, bounded in attempts and budget, typically only for transient, retryable failures.

**Problem:** Transient blips (network hiccup, leader election, deploy drain, 503 from an overloaded node) are common; without retries a 1-in-1000 failure becomes a user-visible error 1000x more often than it should.

**Internal Working:** Retry classifier decides retryable (network reset, timeout, 429, 5xx, 503) vs non-retryable (4xx validation, 409 conflict). Delay policy: fixed, exponential with full jitter, or decorrelated jitter. Budget: max attempts (2-3), overall deadline, and a retry budget at scale (e.g., ≤20% of requests may be retries) to prevent retry storms. Combine with idempotency keys for safe repeat of side-effecting calls. Server hints: honor `Retry-After`.

**Architecture:** Client-side wrapper around HTTP/gRPC/DB/queue clients, or in the queue itself (broker redelivers on nack). Mesh can inject retries (Istio VirtualService `retries: { attempts: 3, perTryTimeout: 2s }`) — pick one layer to own retries, not both.

**Implementation:** httpx transport retries via `httpx-retries`; tenacity for arbitrary callables; `@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.5, max=8), retry=retry_if_exception(is_retryable))`. Celery: `autoretry_for=(ConnectionError,), retry_backoff=True, retry_jitter=True, max_retries=5`.

```python
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.5, max=10, jitter=2),
       retry=retry_if_exception_type((TimeoutError, ConnectionError)), reraise=True)
def fetch_profile(uid: int): ...
```

**FastAPI Example:**

```python
from fastapi import BackgroundTasks
@app.post("/notify")
async def notify(msg: Notification, background: BackgroundTasks):
    background.add_task(deliver_with_retry, msg)  # retry with cap + DLQ on exhaustion
    return {"status": "queued"}
```

**Production Example:** Order webhook to a flaky partner endpoint (0.5% failure rate). Tenacity: 3 attempts, exponential + jitter, honor `Retry-After`; failures after 3 attempts go to a DLQ table with `order_id`; reconciler job re-drives every 5 min; partner-facing duplicate rate controlled by idempotency-key header.

**Failure Scenarios:** Retry storm — 30s dependency blip, all 500 global users ×3 retries = 1500x amplification; retrying a non-idempotent charge endpoint → double billing (must have `#14 Idempotency`); retrying a 400 (validation) wastes budget forever; nested retries in gateway and service → multiplicative amplification; retrying beyond caller's timeout → work completes after caller already errored.

**Best Practices:** Retry only transient/5xx/timeout/connection errors; cap attempts (2-3) and total time; exponential backoff with full jitter; honor `Retry-After`; idempotent side effects or idempotency keys; one layer owns retry policy; metric per outcome (`retry_attempt{outcome=exhausted}`); budget retries; DLQ on exhaustion; alert on retry rate.

**Anti-Patterns:** Unbounded retries; immediate fixed-interval retry; retrying 4xx; retries on non-idempotent writes; nested retries across layers; ignoring `Retry-After`; retry as the fix for missing capacity; hiding failure rates from telemetry.

**Trade-offs:** Performance (hides transients, adds latency to failing paths); complexity (modest); cost (amplified load — budget required); consistency (duplicates — idempotency mandatory for writes); maintainability (centralize retry policy).

**Testing:** pytest with a fake failing N times then succeeding; assert attempts count and backoff sleep called with jitter bounds (mock `time.sleep`); integration test: toxiproxy-cut connection mid-request; verify DLQ after max attempts; load test retry amplification against a failing dependency.

**Related Concepts:** `#13 Exponential Backoff`, `#14 Idempotency`, `#20 Dead Letter Queues`, `#10 Circuit Breakers`, `#11 Timeouts`, `#12 Retries` ⇄ latency of `#93 P99 Latency`.

**Decision Criteria:** Use when: transient faults dominate and the operation is safe (read or idempotent-write). Do not use when: deterministic failures (validation, auth), non-idempotent side effects without keys, saturated dependencies (retry makes it worse). Alternatives: DLQ + reprocess, `#10 Circuit Breakers`, fail-fast with user retry, queue-based buffering (`#15 Message Queues`).

### 13. Exponential Backoff

**Definition:** A delay strategy for retries in which the wait grows multiplicatively (e.g., 100ms, 200, 400, 800…) and is capped, usually combined with random jitter.

**Problem:** Synchronized retries after a shared failure (deploy, dependency blip, 429 wave) return in lockstep and hammer the recovering service — a self-inflicted thundering herd that turns a 2-minute blip into a full outage.

**Internal Working:** delay_n = min(cap, base × 2^n); full jitter: sleep(random(0, delay_n)) spreads retries uniformly across the window; decorrelated jitter: delay = random(base, delay_prev × 3) — best under ongoing contention. Jitter is not optional: deterministic backoff preserves synchronization. Add a cap (≤30s typical) and an overall deadline. Clients often add `Retry-After` hints from the server that override the computed delay.

**Architecture:** Inside retry wrappers (tenacity/httpx/Celery), client SDK token-refresh loops, queue consumers re-delivering with broker `x-delay`, and LLM API clients honoring `Retry-After`.

**Implementation:**

```python
from tenacity import retry, stop_after_delay, wait_exponential_jitter, wait_random_exponential
@retry(stop=stop_after_delay(30), wait=wait_exponential_jitter(initial=0.1, max=10))
def call_llm(prompt: str): ...
# Celery: task = app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
```

Broker: RabbitMQ DLX + `x-message-ttl` per retry tier (10s/60s/5min); SQS `VisibilityTimeout` increase per attempt.

**FastAPI Example:** Token-refresh on 401: single-flight refresh with backoff so 500 concurrent 401s do not each hit the IdP (see `#14 Idempotency` for dedupe of refresh requests).

**Production Example:** 429 rollout from an LLM provider. Full-jitter backoff (base 200ms, cap 20s, max 5 attempts) spread 300 retrying workers across ~20s with peak 60 req/s instead of a 300-req/s burst; error rate recovered without operator intervention.

**Failure Scenarios:** No jitter → lockstep retry storm; cap too high → request outlives caller timeout and uselessly completes; cap too low → gives up before recovery; backoff without a deadline → worker pinned for minutes; everyone uses the same base → partial synchronization.

**Best Practices:** Always full jitter; cap delay and total deadline; honor `Retry-After`; stagger bases per client class; log attempt count and final failure; monitor retry distribution; combine with `#14 Idempotency`; use broker-side delay tiers for queue redelivery.

**Anti-Patterns:** Fixed 1s retries; backoff without jitter; unbounded growth; no cap; implicit synchronization via identical fleets; backoff misread as user-facing latency budget.

**Trade-offs:** Performance (delays add latency, dramatically raise recovery probability); complexity (trivial); cost (reduced amplification); consistency (pairs with idempotency); maintainability (standard library, no custom math).

**Testing:** pytest asserting computed delays within [0, min(cap, base×2^n)] over 10k samples; mocked clock advancing; verify `Retry-After` honored; chaos test failing a dependency and confirming no correlated retry spike in metrics.

**Related Concepts:** `#12 Retries`, `#10 Circuit Breakers`, `#14 Idempotency`, `#75 DDoS Protection` (defenders use the same math), `#90 Serverless Limits`.

**Decision Criteria:** Use when: any retry exists — backoff+jitter is the default delay policy. Do not use when: operation is latency-critical and user-facing with immediate failure preferred (e.g., interactive checkout — surface error instantly); when retries are forbidden entirely (non-idempotent). Alternatives: token bucket pacing, queue-based retry tiers, user-initiated retry.

### 14. Idempotency

**Definition:** A property of an operation such that performing it once or many times has the same observable effect; for APIs, the client supplies an idempotency key and the server dedupes by it.

**Problem:** Retries, double-clicks, webhook redeliveries, and client timeouts mean "did it happen?" is ambiguous; without idempotency, ambiguity charges cards twice, creates duplicate orders, and double-sends emails.

**Internal Working:** Client generates a unique key (UUID v4) per logical operation and sends it (e.g., `Idempotency-Key: 9b2f…`). Server runs a transaction: `INSERT INTO idempotency_keys(key, status, response) VALUES (...) ON CONFLICT DO NOTHING` (or Redis `SET key1 <hash> NX PX 86400000`); on conflict, returns the stored response instead of re-executing. Store request hash too — same key with different payload must be rejected (422). Keys expire with a TTL ≥ retry horizon (24h typical). The critical section must be atomic with the side effect (same DB transaction for DB writes; for external APIs, forward the same key to the downstream provider which supports idempotency — Stripe-style).

**Architecture:** API boundary + persistence layer (`idempotency_keys` table), plus downstream forwarding to providers that accept keys (Stripe, SendGrid). Middleware or dependency extracts the key; service layer performs check-and-execute in one transaction.

**Implementation:**

```python
# SQLAlchemy model sketch
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))  # in_flight | done
    response: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

Flow in one DB transaction: SELECT key FOR UPDATE → if none: INSERT status=in_flight; execute side effect; UPDATE status=done + response; COMMIT. Concurrent duplicates block on the row lock and re-read the outcome.

**FastAPI Example:**

```python
@app.post("/payments")
async def create_payment(req: PaymentRequest, idempotency_key: str = Header(...), db: Session = Depends(get_db)):
    outcome = await idempotency.execute(db, idempotency_key, req.model_dump_json(), lambda: gateway.charge(req))
    return outcome.response
```

**Production Example:** Stripe-integration style `POST /v1/charges` with `Idempotency-Key` per user checkout attempt; DB transaction stores key + charge result atomically; retried request within 24h returns the original `200 {charge_id}` without re-calling Stripe; mismatched key+payload → `422`. Double-charge reports dropped to zero.

**Failure Scenarios:** Key stored in Redis but side effect committed separately → key lost, duplicate executes (store key in same DB/transaction); same key + different payload silently accepted → data corruption; TTL shorter than the retry window → duplicates recur after expiry; storing the response but not status=in_flight → concurrent duplicates both execute; downstream provider without idempotency support and no dedup → duplicate charge anyway; user retrying with a *new* key believing it is the same operation.

**Best Practices:** One key per logical operation, from client; store request hash; atomic check-and-execute; 422 on key+payload mismatch; TTL ≥ 24h; return stored status+body; forward keys downstream; log key for audit; make all mutating endpoints idempotent or document why not; GET/PUT/DELETE are naturally idempotent — POST is not.

**Anti-Patterns:** Client generates a key per retry attempt (defeats the purpose); dedup by request body hash only (breaks legit repeat orders); key check outside the transaction; no TTL; swallowing duplicate errors and returning 200 with a fabricated response that hides failure.

**Trade-offs:** Performance (one extra row/lock per mutating request); complexity (moderate; transaction discipline required); consistency (exactly-once illusion achieved for effects inside the transaction boundary); storage (tiny, pruned by TTL); maintainability (cross-cutting — middleware + table + tests).

**Testing:** pytest: same key twice → origin called once, identical response both times; different payload same key → 422; concurrent requests with same key (asyncio.gather ×10) → single execution; key expiry behavior; Stripe-style integration test with provider test mode redelivering webhooks.

**Related Concepts:** `#12 Retries`, `#13 Exponential Backoff`, `#18 Distributed Transactions`, `#19 Saga Pattern`, `#36 Optimistic Locking`, `#101 Webhooks` (receivers must dedupe).

**Decision Criteria:** Use when: any client-retried mutating call, webhooks, payment flows, order creation, queue consumers (at-least-once delivery). Do not use when: pure reads; internal calls with exactly-once transport (rare/nonexistent); operations where duplication is harmless and provably so. Alternatives: natural unique constraints (email + order number), `#36 Optimistic Locking` for version-checked updates, "at-least-once + dedupe" instead of "exactly-once".

### 21. Cron Jobs

**Definition:** Time-scheduled execution of jobs (a crontab entry or platform scheduler) that run periodic tasks such as reports, cleanups, reconciliations, and cache warming.

**Problem:** Recurring maintenance is inevitable; done ad hoc by hand it is forgotten, duplicated across hosts, or run twice concurrently — corrupting data or double-charging.

**Internal Working:** Unix cron evaluates `minute hour day month weekday command` with local time and `PATH`; no leader election, no retries, no overlap protection. Platform schedulers (K8s CronJob with `concurrencyPolicy: Forbid|Replace` and `startingDeadlineSeconds`, AWS EventBridge, Celery beat, Airflow) add history, dedup, retries, and observability. Missed schedules depend on `startingDeadlineSeconds`; overlap is the most common production bug — two runs mutate the same state.

**Architecture:** Scheduler triggers a job container/worker that runs a short, idempotent unit; heavy work enqueued onto a queue; results/metrics reported; alerts on failures or missed runs (heartbeat).

**Implementation:**

```yaml
# Kubernetes CronJob
apiVersion: batch/v1
kind: CronJob
metadata: {name: nightly-close}
spec:
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid          # never overlap
  startingDeadlineSeconds: 600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      template: {spec: {restartPolicy: Never, containers: [{name: run, image: registry/app:1.2.3, command: ["python","-m","jobs.close"]}]}}
```

For app-embedded loops use Celery beat or APScheduler with a Redis lock (`SET lock:job:nightly-close NX`) to guarantee single execution.

**Python Example:**

```python
import redis
r = redis.Redis()
lock = r.set("lock:job:nightly-close", "1", nx=True, ex=3600)
if lock:
    try:
        reconcile_daily_billing()
    finally:
        r.delete("lock:job:nightly-close")
else:
    sys.exit(0)  # another instance is running; do not overlap
```

**FastAPI Example:** Rarely inside the API process — instead an endpoint `POST /jobs/nightly-close` that is not publicly routable (internal listener only) and that enqueues work; admins can trigger via authenticated call. Better: exit API entirely, use K8s CronJob.

**Production Example:** Nightly invoice reconciliation (02:00, ~8 min): K8s CronJob Forbid-concurrency, job acquires Redis leader lock, writes results to `recon_runs` table with status; heartbeat dead-man's switch pings healthchecks.io; failure → alert to on-call with the run ID; reruns are idempotent by `(date, run_id)` upsert keys.

**Failure Scenarios:** Job runs twice on two replicas (no lock/forbid) → double charges; job silently fails for 3 weeks (no monitoring) → stale data; job held by a hung process for hours while next schedule fires anyway (Forbid absent) → overlap deadlock; job duration > interval → perpetual lag; timezone confusion (server local vs UTC) → reports at wrong hour; missing deadline → missed run never executes (startingDeadlineSeconds too small).

**Best Practices:** Idempotent, re-runnable jobs keyed by logical date; single execution via Forbid or distributed lock; dead-man's-switch monitoring (alert on silence, not only errors); structured logs + duration metrics; jobs enqueue rather than compute inline; uniqueness keys derived from schedule date; document what a manual rerun means for data.

**Anti-Patterns:** `cron` on a single VM that gets decommissioned; job doing heavy work inline in a 30-second loop every minute; no monitoring ("it ran yesterday"); partial failures committed without a transaction; wall-clock-naive scripts; shared mutable state with no lock.

**Trade-offs:** Performance (off-peak batch is cheap; Bursts can collide); complexity (platform scheduler ≈ free vs custom beat); cost (idle capacity only during run); consistency (at-least-once → idempotency mandatory); maintainability (declare schedules in Git, review with the app).

**Testing:** pytest the job function directly with a fixed logical clock; dry-run flag against a staging DB; assert Forbid/lock behavior by triggering twice concurrently; dead-man's-switch test by disabling the job; verify `recon_runs` uniqueness after rerun.

**Related Concepts:** `#14 Idempotency`, `#38 Distributed Locks`, `#56 Health Checks`, `#62 Alerts`, `#21 Cron Jobs` pairs with `#15 Message Queues` for fan-out, and with `#84 Backups`.

**Decision Criteria:** Use when: periodic batch/maintenance/maintenance tasks, reconciliation, cleanup, report generation. Do not use when: work must react to events (use `#15 Message Queues`/`#16 Pub/Sub`); sub-minute precision needed (use a streaming loop); single user-triggered actions (use an endpoint). Alternatives: message triggers, workflow engines (Airflow/Temporal), event-driven handlers.

<!--END-->
