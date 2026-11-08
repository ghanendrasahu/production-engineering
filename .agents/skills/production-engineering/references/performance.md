# Performance Reference (Scaling, Caching, Latency & Tail)

Covers topics 45-50 and 89-94: autoscaling, horizontal/vertical scaling, CDN, edge caching, cache invalidation, cold starts, serverless limits, latency, throughput, P99 and tail latency.

Scaling and caching decide whether a service absorbs demand or falls over. This reference covers capacity scaling (autoscaling, horizontal, vertical) and the caching tier (CDN, edge caching, invalidation), with concrete configs, runnable Python, and real failure modes.

| # | Concept | One-line use case |
|---|---|---|
| 45 | Autoscaling | Grow from 4 to 60 replicas during a flash crowd, shrink back at night. |
| 46 | Horizontal Scaling | Add identical stateless nodes behind a load balancer instead of a bigger box. |
| 47 | Vertical Scaling | Enlarge one node (bigger instance, bigger buffer pool) when state is local. |
| 48 | CDN | Serve assets from nearby PoPs and offload the origin. |
| 49 | Edge Caching | Cache repeat GETs at the edge with keys, TTLs, and ETag revalidation. |
| 50 | Cache Invalidation | Remove or version cached entries on write so clients never read stale data. |

### 45. Autoscaling

**Definition:** Autoscaling automatically adds or removes capacity in response to live metrics via target-tracking, step, or scheduled policies, replacing static capacity guesses with a feedback loop.

**Problem:** Provisioning for peak wastes budget at 3 AM; provisioning for average collapses in a flash crowd — idle spend or 5xx errors.

**Internal Working:** A controller samples CPU, rps, or queue depth and computes `desired = ceil(current × observed / target)` clamped to min/max. The HPA applies 0s scale-out and 300s scale-in stabilization windows plus policies like +100% replicas/15s out and −2 pods/60s in to prevent oscillation; AWS target-tracking alarms fire only after repeated breaching evaluations with a 300s cooldown. Scale-in is cordon → drain → SIGTERM; scale-out must finish scheduling, image pull, and readiness before the LB routes traffic — that pipeline is the lag.

**Architecture:** Above the Deployment/node group: reads Prometheus or CloudWatch, acts through the kube-scheduler or ASG API, and registers targets with the LoadBalancer.

**Implementation:** Kubernetes HPA:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: {name: api-hpa}
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: api}
  minReplicas: 4
  maxReplicas: 60
  metrics:
    - type: Resource
      resource: {name: cpu, target: {type: Utilization, averageUtilization: 65}}
  behavior:
    scaleDown: {stabilizationWindowSeconds: 300, policies: [{type: Pods, value: 2, periodSeconds: 60}]}
```

**Python Example:** target tracking with direction-aware cooldowns:

```python
import math, time
from dataclasses import dataclass

@dataclass
class Tracker:
    target: float
    lo: int = 4
    hi: int = 60
    out_cd: float = 15.0
    in_cd: float = 300.0
    changed: float = float("-inf")

    def desired(self, now: float, current: int, metric: float) -> int:
        cand = max(self.lo, min(self.hi, math.ceil(current * metric / self.target)))
        if cand == current:
            return current
        cd = self.out_cd if cand > current else self.in_cd
        if now - self.changed < cd:
            return current
        self.changed = now
        return cand

t = Tracker(target=450.0)
replicas = 4
for now, rps in [(0, 900), (60, 45), (660, 45)]:
    replicas = t.desired(now, replicas, rps)
print(replicas)
```

**FastAPI Example:** Prometheus metrics that KEDA or a custom-metrics HPA consumes:

```python
from fastapi import FastAPI
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

app = FastAPI()
REQS = Counter("http_requests_total", "requests", ["path", "status"])

@app.middleware("http")
async def observe(request, call_next):
    resp = await call_next(request)
    REQS.labels(request.url.path, str(resp.status_code)).inc()
    return resp

@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

**Production Example:** Flash crowd: 4 replicas at 450 rps each scale to 60 in 45s; p95 moves from 320ms with 6% 503s to 95ms. Scale-in then stabilizes to 6 replicas over 300s, cutting nightly spend ~55% versus a fixed 60-replica fleet.

**Failure Scenarios:**
- Scale-out lag: image pull plus warmup takes 40s while demand doubles every 20s — p95 hits 2s.
- Metric loss: a Prometheus scrape failure freezes the HPA.
- Scale-in kills in-flight work: a 90s batch dies at SIGTERM.
- Oscillation: a target near steady-state load causes endless up/down cycles.

**Best Practices:**
- Scale on request rate or in-flight concurrency; keep CPU secondary.
- Asymmetric behavior: fast scale-out, slow stabilized scale-in.
- Keep `minReplicas` ≥ what survives one node loss.
- Pre-pull images and fail readiness until caches are warm.

**Anti-Patterns:**
- Autoscaling on CPU only — misses request spikes and IO wait.
- No `maxReplicas` cap — a retry storm scales into a five-figure bill.
- Scaling stateful singletons as if they were stateless pods.
- Scale-in without drain, truncating in-flight requests.

**Trade-offs:**
- Performance tracks demand, but capacity arrives 15–60s late.
- Metrics, quota, and drain logic must all be correct — more moving parts.
- Pay-for-use lowers idle cost; slow scale-in inflates spend.
- Variable replica counts expose hidden session and state assumptions.

**Testing:** Load test 0.5×–5× baseline with k6 and assert replicas track the curve with p95 inside SLO; break the metrics endpoint and confirm alerts fire; scale in during an open batch and assert graceful drain.

**Related Concepts:** `#8 Kubernetes`, `#91 Latency`, `#92 Throughput`, `#44 Backpressure`, `#56 Health Checks`, `#88 Cost Optimization`

**Decision Criteria:** Use when: traffic is variable, the service is stateless or state is externalized, and metrics are trustworthy. Do not use when: startup takes minutes, capacity is bounded by one database, or metrics/alerting are unreliable. Alternatives: scheduled scaling for predictable curves, queue-driven scaling (`#15 Message Queues`), or a fixed over-provisioned fleet when traffic is flat.

### 46. Horizontal Scaling

**Definition:** Horizontal scaling adds more instances of the same service behind a load balancer instead of enlarging one. Capacity grows by adding nodes until a shared dependency becomes the bottleneck.

**Problem:** One large machine has a hard ceiling on CPU, RAM, and connections, and its failure takes the whole service down; the top of the instance ladder is also ruinously expensive per unit of capacity.

**Internal Working:** The LB keeps a membership set updated by health checks — three consecutive failures remove a target, a passing check re-adds it. Traffic spreads via round-robin, least-connections, or consistent hashing; scale-in drains (deregister, let connections finish) before termination. Since any node must serve any request, sessions and files move to shared stores, otherwise you need sticky sessions that break when nodes are replaced. Throughput scales near-linearly while nodes have headroom, then flattens as the database, pool, or lock service saturates.

**Architecture:** Behind a LoadBalancer/Ingress (`#3 Load Balancing`) in front of identical replicas, with state in Redis/Postgres and membership via service discovery (`#9 Service Discovery`).

**Implementation:** Deployment plus preStop drain:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: api}
spec:
  replicas: 12
  selector: {matchLabels: {app: api}}
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: api
          image: registry.example.com/api:1.42.0
          ports: [{containerPort: 8080}]
          lifecycle:
            preStop: {exec: {command: ["sleep", "10"]}}
          readinessProbe: {httpGet: {path: /ready, port: 8080}}
```

**Python Example:** state in Redis makes replicas interchangeable:

```python
import json, os, uuid
import redis

store = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

def load_cart(session_id: str) -> dict:
    raw = store.get(f"session:{session_id}")
    return json.loads(raw) if raw else {"id": session_id, "items": []}

def add_item(session_id: str, sku: str) -> dict:
    cart = load_cart(session_id)
    cart["items"].append(sku)
    store.setex(f"session:{session_id}", 3600, json.dumps(cart))
    return cart

sid = uuid.uuid4().hex
print(add_item(sid, "SKU-1"))
print(load_cart(sid))
```

**FastAPI Example:** a dependency that hides which replica answers:

```python
import json, os, redis
from fastapi import Depends, FastAPI, Header, HTTPException

app = FastAPI()
store = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

def get_session(x_session_id: str = Header(...)) -> dict:
    raw = store.get(f"session:{x_session_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="unknown session")
    return json.loads(raw)

@app.get("/cart")
def cart(session: dict = Depends(get_session)) -> dict:
    return session
```

**Production Example:** A catalog API runs 12 replicas behind an ALB; a launch pushes 8k → 34k rps. Scaling to 40 replicas takes 50s and holds p95 at 170–195ms (was 1.4s, 11% 5xx). Sessions already lived in Redis; killing one node mid-load caused 0.4% errors for 8s.

**Failure Scenarios:**
- Stateful service scaled out: two replicas overwrite each other's local file — silent data loss.
- Hot-key skew: one popular product drives 30% of traffic to a single replica at 8× median p99.
- Pool exhaustion: 40 pods × 10 connections exceed Postgres's 200-connection cap — errors become "too many connections."
- Sticky sessions break across deploys: carts vanish when a node is replaced.

**Best Practices:**
- Make every node disposable: no local disk state, config from env/secrets, honest readiness checks.
- Externalize sessions and uploads before scaling past one node.
- Size connection pools for fleet size, never per-pod defaults.
- Drain before SIGTERM with a preStop delay so the LB deregisters first.

**Anti-Patterns:**
- Scaling nodes that keep local state — replicas diverge and lose data.
- Sticky sessions used to dodge externalizing state.
- Scaling out against a single primary database.
- No replica cap, so a retry storm scales without limit.

**Trade-offs:**
- Near-linear throughput and no single point of failure, at the cost of network hops.
- State externalization and pool sizing add real complexity.
- Cheaper per unit capacity, but more nodes to patch and observe.
- Uneven cache warmth gives latency skew until replicas warm up.

**Testing:** Load test at 1, 4, and 12 replicas and plot throughput vs. replicas; delete a pod mid-test and assert errors stay <1%; audit that no session bytes live on local disk.

**Related Concepts:** `#3 Load Balancing`, `#47 Vertical Scaling`, `#32 Replication`, `#29 Read Replicas`, `#35 Eventual Consistency`, `#34 CAP Theorem`

**Decision Criteria:** Use when: traffic exceeds one node, state is externalized, and you want redundancy as fault tolerance. Do not use when: state cannot be externalized, coordination dominates (tight distributed locks), or load fits comfortably on one box. Alternatives: vertical scaling for simplicity, sharding (`#30 Sharding`) when one logical dataset is the limit.

### 47. Vertical Scaling

**Definition:** Vertical scaling (scale-up) enlarges a single node — more CPU, RAM, disk, or bandwidth — instead of adding nodes. It preserves locality and simplicity but has a hard ceiling and usually needs a restart.

**Problem:** Small teams drown in replication and pooling overhead for workloads one well-sized box serves; but hitting the ceiling mid-growth forces an emergency migration under load.

**Internal Working:** Resize means stop/start or live migration, so connections drain and clients reconnect — pools, keepalives, and retry budgets all see a blip. Memory growth changes runtime behavior: heap or `innodb_buffer_pool_size` sized to ~70% of RAM, leaving room for page cache; Python's GIL means extra cores help IO-bound concurrency, not CPU-bound throughput. The kernel must scale too (`somaxconn`, file descriptors) or the bigger box still refuses connections. Past the socket, NUMA and memory bandwidth make doubling cores yield less than double throughput.

**Architecture:** Below the service: instance type, VM size, database instance class, or a Kubernetes VPA. Only connection pools and the LB need reconnection tolerance.

**Implementation:** VPA with bounded requests:

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata: {name: api-vpa}
spec:
  targetRef: {apiVersion: apps/v1, kind: Deployment, name: api}
  updatePolicy: {updateMode: "Auto"}
  resourcePolicy:
    containerPolicies:
      - containerName: api
        minAllowed: {cpu: 250m, memory: 512Mi}
        maxAllowed: {cpu: "8", memory: 16Gi}
```

**Python Example:** find where more cores stop helping:

```python
import multiprocessing as mp
import time
from concurrent.futures import ThreadPoolExecutor

SECONDS = 2.0

def burn(_):
    end = time.perf_counter() + SECONDS
    while time.perf_counter() < end:
        pass                       # CPU-bound Python work

def run(factory, workers: int) -> float:
    start = time.perf_counter()
    with factory(workers) as pool:
        list(pool.map(burn, range(workers)))
    return time.perf_counter() - start

for n in (1, 2, 4, 8):
    print(n, run(mp.Pool, n), run(ThreadPoolExecutor, n))
```

**FastAPI Example:** size per-process queueing to the capacity bought:

```python
import os
from fastapi import FastAPI

cores = os.cpu_count() or 2
app = FastAPI(limit_concurrency=cores * int(os.environ.get("QUEUE_DEPTH", 64)))

@app.get("/ready")
def ready() -> dict:
    return {"cores": cores, "limit": app.router.concurrency_limit}
```

**Production Example:** A reporting service on 4 vCPU/16 GiB had p95 of 240ms as the cache and Postgres buffer pool fought for RAM. Moving to 16 vCPU/64 GiB with `shared_buffers=40GiB` dropped p95 to 90ms and major page faults from 900/s to <5/s, inside a 4-minute drain window with a 450s pool reconnect budget.

**Failure Scenarios:**
- Single point of failure: the enlarged node dies and there is no replica — full outage.
- Unexpected resize during business hours drops every open connection.
- GIL ceiling: more cores give ~0% gain on CPU-bound Python; cost per unit of work rises.
- Leaks scale with memory: a bigger heap only delays the OOM.

**Best Practices:**
- Measure saturation (steal, page faults, memory bandwidth) before buying bigger.
- Reserve vertical scaling for the stateful tier where locality matters.
- Run VPA in recommender mode first; enable `Auto` with disruption budgets.
- Drain connections and back off reconnects around every resize.

**Anti-Patterns:**
- Scale-up as the only strategy: every resize is an outage risk and the ceiling always arrives.
- Growing memory without fixing leaks.
- Choosing the largest instance "to be safe" with no utilization data.
- Vertical-only scaling of a stateless API that would scale linearly.

**Trade-offs:**
- Immediate single-node gains with zero network penalty, bounded by hardware.
- Lowest complexity of the three scaling modes — no coordination or state changes.
- Simple billing, but a steep premium per unit of capacity.
- Consistency untouched (one node, one truth); migration pain deferred, not removed.

**Testing:** Benchmark throughput at 1×, 2×, and 4× sizes to find the knee; fill 90% of RAM and assert graceful degradation without OOMKill; count failed requests during a resize; assert no swap (`vmstat 1` si/so ≈ 0) after the upgrade.

**Related Concepts:** `#46 Horizontal Scaling`, `#42 Garbage Collection`, `#41 Memory Leaks`, `#91 Latency`, `#88 Cost Optimization`, `#29 Read Replicas`

**Decision Criteria:** Use when: workload is small-to-moderate, state is local, or a single-writer database is the bottleneck. Do not use when: high availability matters (one node = one point of failure), CPU-bound Python hits the GIL, or the largest instance is already in use. Alternatives: horizontal scaling for stateless services, read replicas/sharding for databases, serverless (`#89 Cold Starts`) for spiky low volume.

### 48. CDN

**Definition:** A Content Delivery Network is a geographically distributed set of edge servers that cache and serve content close to users, offloading the origin. It combines anycast/BGP routing, a caching tier, TLS termination, and often WAF/DDoS protection.

**Problem:** Users far from the origin pay full round-trip latency and the origin pays full bandwidth; a viral asset or flash crowd saturates origin capacity and egress costs.

**Internal Working:** DNS resolves the CDN hostname and anycast/BGP steers the client to the nearest PoP. The edge hashes a cache key from the URL, query, selected headers, and `Vary` fields: a HIT serves locally and increments `Age`; a MISS fetches the origin, honors `Cache-Control`/`s-maxage`, then stores the object. Revalidation uses `If-None-Match`/`If-Modified-Since`, returning 304 with no body. An edge → regional → origin-shield hierarchy collapses fan-out, `stale-while-revalidate` refreshes in the background, and purges run by URL, prefix, or surrogate tag.

**Architecture:** `client → DNS/anycast → edge PoP → (miss) origin shield → origin`, with TLS terminated at the edge and the origin reachable only from CDN ranges.

**Implementation:** CloudFront essentials (Terraform):

```hcl
resource "aws_cloudfront_distribution" "assets" {
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    viewer_protocol_policy = "redirect-to-https"
    target_origin_id       = "origin"
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }
  origin {
    domain_name = "origin.example.com"
    origin_id   = "origin"
    origin_shield { enabled = true, origin_shield_region = "us-east-1" }
  }
}
```

**Python Example:** CloudFront signed URL for private media (canned policy):

```python
import base64, datetime as dt, json, urllib.parse, os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def signed_url(url: str, expires_in: int = 300) -> str:
    exp = int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=expires_in)).timestamp())
    policy = json.dumps({"Statement": [
        {"Resource": url, "Condition": {"DateLessThan": {"AWS:EpochTime": exp}}}]})
    key = serialization.load_pem_private_key(os.environ["CF_KEY_PEM"].encode(), password=None)
    sig = base64.b64encode(key.sign(policy.encode(), padding.PKCS1v15(), hashes.SHA1()))
    sep = "&" if "?" in url else "?"
    return (f"{url}{sep}Policy={urllib.parse.quote(policy)}"
            f"&Signature={urllib.parse.quote_from_bytes(sig, safe='-_~')}"
            f"&Key-Pair-Id={os.environ['CF_KEY_ID']}")

print(signed_url("https://d111.cloudfront.net/invoice.pdf"))
```

**FastAPI Example:** hand clients CDN URLs with explicit cache headers:

```python
import os
from fastapi import FastAPI, HTTPException, Response

app = FastAPI()
CDN = os.environ["CDN_BASE"]

@app.get("/media/{asset_id}")
def media(asset_id: str, response: Response) -> str:
    if not asset_id.isalnum():
        raise HTTPException(status_code=400, detail="invalid asset id")
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return f"{CDN}/assets/{asset_id}.webp"
```

**Production Example:** A marketplace on 41 PoPs serves images from the edge: `/img/*` p95 in São Paulo falls from 420ms to 85ms. Offload reaches 92%, dropping origin traffic from 18k to 1.4k rps and saving ~$11k/month; hashed filenames stay `immutable` while HTML invalidates on deploy.

**Failure Scenarios:**
- Cache poisoning: an unkeyed header changes the stored response — all users get attacker content.
- Private data leak: authenticated HTML cached `public` under a shared key exposes users to each other.
- Stale after deploy: HTML cached 24h loads deleted JS chunks → blank page.
- Origin shield outage: all PoPs stampede the origin at once.

**Best Practices:**
- Fingerprint assets (`app.4f3a9c.js`) and cache them `immutable`; keep HTML short-TTL.
- Define which headers, cookies, and query params enter the cache key.
- Use origin shield to collapse origin fan-out.
- Automate purge-by-prefix or purge-by-tag in the deploy pipeline.

**Anti-Patterns:**
- Caching authenticated responses without per-user keys or `private`.
- One distribution mixing API and static content with a single TTL.
- Manual purges during incidents instead of pipeline invalidation.
- Ignoring `Vary`, serving the wrong encoding or language variant.

**Trade-offs:**
- Big latency and offload wins for cacheable content; misses add a hop.
- Cache-key design and purge workflows are ongoing operational load.
- Edge egress is cheap per GB, but requests and invalidations are billed.
- Copies exist everywhere: freshness depends on TTL discipline.

**Testing:** Load test from multiple regions cold and warm, asserting >90% hit ratio and p95 gains; verify `Age`/`X-Cache-Status`; vary unkeyed headers and confirm identical responses; purge in staging and confirm the refetch.

**Related Concepts:** `#49 Edge Caching`, `#50 Cache Invalidation`, `#2 Caching`, `#97 DNS`, `#75 DDoS Protection`, `#71 TLS`

**Decision Criteria:** Use when: content is public or cacheable, users are geographically spread, and origin latency or bandwidth dominates. Do not use when: responses are authenticated and personalized without a cache-key design, data must revoke in milliseconds, or traffic is low and origin-proximate. Alternatives: edge compute (Workers/Lambda@Edge), regional replicas (`#86 Multi-Region Deployment`), or origin-side reverse proxies (`#4 Reverse Proxies`).

### 49. Edge Caching

**Definition:** Edge caching stores repeatable responses at the network edge — CDN PoPs, Cloudflare, Fastly, or an API gateway edge tier — and serves them without contacting the origin. It is the mechanism of keys, TTLs, revalidation, and eviction that makes a CDN work for dynamic traffic.

**Problem:** Origin round-trips for repeated GETs waste hundreds of milliseconds and saturate origin capacity, even though most reads never change.

**Internal Working:** The edge builds a key `hash(method + host + path + sorted query + Vary-selected headers)` and looks it up in a bounded LRU store. A HIT serves immediately with `Age`; a MISS fetches the origin and stores the body for the TTL from `Cache-Control`/`s-maxage` (`no-store`, `private`, `Vary: *` are uncacheable). Near expiry it revalidates with `If-None-Match` (store only on 200, 304 when unchanged); `stale-while-revalidate` serves stale bytes while refreshing. LRU evicts coldest keys under pressure; surrogate-key purges evict thousands at once.

**Architecture:** `client → edge cache → (miss/stale) origin → app → Redis/DB`. App-written `Cache-Control`/`ETag`/`Vary` headers are the contract the edge obeys.

**Implementation:** Nginx edge cache:

```nginx
proxy_cache_path /var/cache/nginx/api keys_zone=api_edge:200m
                 max_size=10g inactive=120s;
server {
  listen 443 ssl;
  location /public/ {
    proxy_cache           api_edge;
    proxy_cache_key       "$scheme$request_method$host$request_uri$cookie_lang";
    proxy_cache_valid     200 30s;
    proxy_cache_use_stale error timeout updating http_503;
    proxy_cache_lock      on;    # one upstream fetch per hot key
    add_header X-Cache-Status $upstream_cache_status always;
    proxy_pass http://api_upstream;
  }
}
```

**Python Example:** deterministic edge cache keys:

```python
import hashlib, urllib.parse

VARY = ("accept-encoding", "accept-language")

def cache_key(method: str, url: str, headers: dict) -> str:
    p = urllib.parse.urlsplit(url)
    q = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(p.query, keep_blank_values=True)))
    vary = "|".join(f"{h}={headers.get(h, '').lower()}" for h in VARY)
    return "edge:" + hashlib.sha256(f"{method.upper()}|{p.path}|{q}|{vary}".encode()).hexdigest()

h = {"accept-encoding": "gzip", "accept-language": "en-US"}
assert cache_key("GET", "https://a.dev/c?b=2&a=1", h) == cache_key("GET", "https://a.dev/c?a=1&b=2", h)
```

**FastAPI Example:** middleware making responses edge-revalidatable:

```python
import hashlib
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

app = FastAPI()

class EdgeCache(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != "GET" or not request.url.path.startswith("/public/"):
            return await call_next(request)
        resp = await call_next(request)
        body = b"".join([c async for c in resp.body_iterator])
        tag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
        headers = {"ETag": tag,
                   "Cache-Control": "public, s-maxage=60, stale-while-revalidate=30"}
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers=headers)
        return Response(body, status_code=resp.status_code, headers=headers)

app.add_middleware(EdgeCache)
```

**Production Example:** A catalog API doing 4k rps of GETs gets `s-maxage=60` with `stale-while-revalidate=30`. Offload reaches 94% (240 origin rps instead of 4k) and p95 drops 210ms → 60ms in-region, 95ms distant; one hot key (18% of traffic) uses a 15s TTL with `proxy_cache_lock`, holding origin at ~30 rps.

**Failure Scenarios:**
- Thundering herd at TTL expiry: 40k clients revalidate one key in the same second.
- Stale after write: a price changes but the copy lives another 55s.
- Key explosion: `utm_*` params in the key drop hit ratio to 20%.
- `Vary: Cookie` on a public route makes every visitor miss.

**Best Practices:**
- Normalize keys: strip tracking params, sort query strings, key only body-changing headers.
- Set `s-maxage` explicitly; let the app own freshness.
- Use `stale-while-revalidate` plus single-flight locks to smooth expiry spikes.
- Emit `X-Cache-Status`/`Age` and chart hit ratio per route.

**Anti-Patterns:**
- Caching with no invalidation plan.
- Caching personalized responses under a shared key.
- Unbounded cache growth with no size cap.
- Long TTLs on error responses, extending outages.

**Trade-offs:**
- Largest wins for hot repeatable GETs; unique traffic gains little.
- Key design and staleness debugging add real complexity.
- Lower origin cost, billed edge requests, larger key zones.
- Copies age — read-your-writes needs bypass or short TTLs.

**Testing:** Load cold then warm (MISS → HIT, ≥90% ratio, p95 drop); assert `If-None-Match` returns 304 for an unchanged body; audit stored keys for leaked user IDs; disable the cache and confirm the origin still holds SLO.

**Related Concepts:** `#2 Caching`, `#48 CDN`, `#50 Cache Invalidation`, `#93 P99 Latency`, `#99 HTTP/2 & HTTP/3`, `#38 Distributed Locks`

**Decision Criteria:** Use when: traffic skews toward repeat GETs, responses are public or safely keyable, and origin latency or capacity is the constraint. Do not use when: reads must reflect writes immediately, requests are mostly unique, or the response cannot be shared across users. Alternatives: Redis cache-aside (`#2 Caching`), read replicas (`#29 Read Replicas`), or no cache with a faster origin.

### 50. Cache Invalidation

**Definition:** Cache invalidation removes or supersedes cached entries when underlying data changes so readers never observe stale values.

**Problem:** Stale data is a business incident: a revoked permission honored, a price shown after it changed. Manual purges are not a plan.

**Internal Working:** Four mechanisms dominate. Time-based: TTL bounds staleness but guarantees none below it. Delete-on-write races an in-flight read that repopulates old data — delete before commit or version the key. Versioned keys: bump a counter so old keys become garbage — memory for race-free reads. Tag purge: keys sit in tag sets (`SADD tag:product:42 key`) walked on invalidation. `SET NX PX` locks stop stampedes; pub/sub (`#16 Pub/Sub`) fans evictions out.

**Architecture:** Writer → cache-aside get/set on Redis → invalidation event (pub/sub or version bump) → local and edge caches (`#49 Edge Caching`) purged by tag.

**Implementation:** Redis layout: `SETEX` values, tag sets (`SADD`/`SMEMBERS` + `DEL`), lock via `SET key:lock token NX PX 5000` with compare-and-delete Lua; at the edge, Cloudflare purge-by-tag or `Surrogate-Key`.

**Python Example:** cache-aside with stampede lock and tag invalidation:

```python
import json, os, time
import redis

r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end"

def cache_get(key, loader, tags=(), ttl=60):
    if (raw := r.get(key)) is not None:
        return json.loads(raw)
    token = os.urandom(8).hex()
    if r.set(f"{key}:lock", token, nx=True, px=5000):      # single-flight
        try:
            value = loader()
            pipe = r.pipeline().setex(key, ttl, json.dumps(value))
            for tag in tags:
                pipe.sadd(f"tag:{tag}", key).expire(f"tag:{tag}", ttl * 4)
            pipe.execute()
            return value
        finally:
            r.eval(RELEASE, 1, f"{key}:lock", token)
    for _ in range(50):                                    # wait for the winner
        time.sleep(0.01)
        if (raw := r.get(key)) is not None:
            return json.loads(raw)
    return loader()                                        # duplicate fetch beats a 5xx

def invalidate_tags(*tags) -> int:
    removed = 0
    for tag in tags:
        if members := r.smembers(f"tag:{tag}"):
            removed += len(members)
            r.delete(*members, f"tag:{tag}")
    return removed

print(cache_get("product:42", lambda: {"id": 42, "price": 19.99}, tags=("product:42",)))
invalidate_tags("product:42")   # post-write
```

**FastAPI Example:** service-layer cache-aside with invalidation on write:

```python
import json, os, redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
store = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

class ProductIn(BaseModel):
    name: str
    price: float

@app.get("/products/{pid}")
def read_product(pid: str) -> dict:
    if not (raw := store.get(f"product:{pid}")):
        raise HTTPException(status_code=404, detail="not found")
    return json.loads(raw)

@app.put("/products/{pid}")
def write_product(pid: str, body: ProductIn) -> dict:
    data = {"id": pid, **body.model_dump()}        # commit to DB first
    if keys := store.smembers(f"tag:product:{pid}"):
        store.delete(*keys, f"tag:product:{pid}")
    store.setex(f"product:{pid}", 60, json.dumps(data))
    return data
```

**Production Example:** A shop caches 1.2M product keys at 60s TTL. TTL-only invalidation left a $49 item at $39 for 47 minutes; tag invalidation cut the stale window to <2s at 91% offload. Stampede locking capped a hot-key expiry at ~300 fetches instead of 40k, holding p95 at 70ms.

**Failure Scenarios:**
- Thundering herd at TTL expiry: a latency sawtooth every TTL seconds.
- Stale after write: a fire-and-forget delete is lost and old values persist for minutes.
- Divergent copies: an instance misses the pub/sub eviction and keeps serving stale data.

**Best Practices:**
- Decide freshness per route: TTL for tolerant reads, invalidation for read-after-write.
- Invalidate after the commit, or version keys for the refill race.
- Invalidate by tag, never wildcard flush; cap tag sizes.
- Protect hot keys with single-flight locks; publish invalidations to replicas.

**Anti-Patterns:**
- Caching with no invalidation plan: lowering the TTL is not a plan.
- Caching per-user data under a shared key.
- Unbounded cache growth: no `maxmemory` or eviction policy.

**Trade-offs:**
- Stronger invalidation means more coordination; looser rules mean bounded staleness.
- Longer TTLs raise offload but raise stale-read risk; frequent purges push origin traffic back up.
- Tag graphs and version keys are hard to reason about.

**Testing:** Load test cold vs. warm comparing origin rps and p95; write-then-read until the new value appears; `SCAN` for keys missing TTLs; kill Redis and confirm the service holds SLO.

**Related Concepts:** `#2 Caching`, `#49 Edge Caching`, `#38 Distributed Locks`, `#39 Race Conditions`, `#36 Optimistic Locking`, `#16 Pub/Sub`

**Decision Criteria:** Use when: any cached value can change while in flight and readers must not see pre-write data. Do not use when: data is immutable or content-addressed, or invalidation traffic would approach read traffic. Alternatives: versioned keys, write-through caching, shorter TTLs, or read replicas (`#29 Read Replicas`).

Cold starts, serverless constraints, latency distributions, throughput, and the tail-latency disciplines that separate "feels fast" from "measurably fast".

| # | Concept | One-line use case |
|---|---|---|
| 89 | Cold Starts | First-invocation latency of serverless |
| 90 | Serverless Limits | Know the caps before you design |
| 91 | Latency | Time from request to response |
| 92 | Throughput | Requests per unit time |
| 93 | P99 Latency | The number that actually breaks SLAs |
| 94 | Tail Latency | Why the slowest 1% dominates experience |

### 89. Cold Starts

**Definition:** The extra latency of the first invocation after a serverless/container instance is created — runtime boot, dependency load, app initialization (model loading, connection setup) before the first byte of business logic runs.

**Problem:** Spiky p99s, timeouts on the unlucky first request, and quiet ruin of demos and real user flows for serverless workloads with bursty, low traffic.

**Internal Working:** Phases: platform provisioning (VM/microVM — Firecracker ~100-200ms) → runtime init (language boot; JVM slowest) → function init (imports, global scope) → handler execution. Mitigations: **provisioned concurrency** (always-warm instances — pay for idle), snapstart (JVM snapshot restore — ms), custom runtimes (Rust/Go boot fastest; Python/Node modest), lazy-init vs eager-init tradeoff (global scope runs once warm; per-request cold cost lands on first call), smaller deployment packages (cold init scales with code size), dependency trimming, and warming pings (synthetic traffic every N min — works, but burns money and can mask real scale-to-zero economics).

**Architecture:** FaaS (Lambda/Cloud Run) cold path; containers reuse warm instances; keep-alive pools for LLM SDKs; DB connections established outside handler (global).

**Implementation:**

```python
# Lambda-style: init outside the handler
import boto3, os
s3 = boto3.client("s3")          # initialized once per warm instance
import pydantic, heavy_lib       # cost lands on cold start only

def handler(event, context):
    return {"statusCode": 200, "body": do_work(event)}
```

Cloud Run: `min-instances=1`; Lambda: provisioned concurrency = N; measure with `X-Amz-Total-Matched` / trace duration cold vs warm.

**FastAPI Example:** uvicorn worker with model preloaded in lifespan startup; `min_instances ≥ 1` in Cloud Run so first user never pays the load; startupProbe sends traffic only after lifespan completes.

**Production Example:** OCR API on Lambda: 4s cold starts (Tesseract import) killing 2% of requests at the 3s ALB timeout; fixed: provisioned concurrency 2 + lazy DB pool; cold p99 4s→180ms (warm), no failures; cost +$60/month vs lost conversions.

**Failure Scenarios:** Cold start + retry = 2× cold cost (timeout at client while Lambda still runs); container scale-from-zero on cron bursts all cold simultaneously; giant dependency layer (300MB) → every deploy re-cold; "keep-warm" ping firing every 5min prevents scale-to-zero — costs money, no burst benefit at random times; JVM without snapstart; health checks not excluding cold instances → LB sends traffic to booting pods.

**Best Practices:** Global-scope init; small packages (strip dev deps); Go/Rust for latency-critical FaaS; provisioned concurrency where SLOs demand; min-instances=1 for always-feeling-fast; measure cold vs warm separately; connection reuse outside handler; avoid lazy-loading on hot path after init.

**Anti-Patterns:** Eager-loading everything every invocation; 500MB layers; pings every 5min at scale ("it works but costs 4x"); synchronous heavy init per request; no min-instances on user-facing Cloud Run; ignoring cold latency in SLOs.

**Trade-offs:** Performance (0 with warm pool — at cost); complexity (config knobs, not code); cost (provisioned concurrency ≈ always-on 20-100%); consistency (n/a); maintainability (documented in deploy config).

**Testing:** Load test from zero replicas → first-request latency; assert p99 within SLO; deployment canary warms instance; metric for cold-start ratio (`cold_start_total / total`); chaos: scale-to-zero drill.

**Related Concepts:** `#90 Serverless Limits`, `#91 Latency`, `#93 P99 Latency`, `#45 Autoscaling`, `#89 Cold Starts` mitigates `#90 Serverless Limits`.

**Decision Criteria:** Use when: serverless user-facing latency SLOs tight — apply warm pools. Do not use when: batch jobs (cold irrelevant). Alternatives: always-on containers (ECS/K8s — simplest), snapstart, smaller runtimes.

### 90. Serverless Limits

**Definition:** Hard platform ceilings for FaaS/serverless workloads: execution timeout (Lambda 15min), memory (Lambda 10GB), payload (6MB sync / 256KB async invocation), concurrency (1000/region default, soft), ephemeral storage (10GB /tmp), cold-start behavior, and per-request pricing.

**Problem:** Designing unbounded workloads onto bounded primitives — a video transcoder that hits 15min or a WebSocket app needing millions of concurrent connections — fails in production, not in the tutorial.

**Internal Working:** Lambda: 15min max, 10GB RAM (CPU scales with memory — 1 vCPU per 1.5-2GB), 6MB request/256KB response payloads, 10GB /tmp, ~1000 concurrent (soft limit, raisable). Cloud Run: 60min request timeout (HTTP streaming to 60min now), 4 vCPU/8GB, concurrency 250/instance default, cold starts; Azure Functions similar; KV/edge: 25MB response, 50ms CPU on some platforms. Pricing: per-GB-second + per-request — high sustained throughput costs MORE than containers; breakeven around 20-40% sustained utilization.

**Architecture:** Choose primitive by duration/statefulness: HTTP APIs (short, stateless) → Lambda/Cloud Run; streams/websockets → containers; GPU inference → dedicated instances.

**Implementation:**

```yaml
# serverless.yml / SAM (concept)
functions:
  process:
    timeout: 900            # seconds — hard cap
    memorySize: 3008        # ~2 vCPU
    reservedConcurrency: 100
```

```python
# chunk long work to fit limits: Step Functions / SQS fan-out
for batch in chunks(docs, 100):
    sqs.send_message(QueueUrl=Q, MessageBody=json.dumps(batch))  # many small functions
```

**Production Example:** PDF pipeline: 8-minute renders on Lambda 15min cap — 3% of files timed out exactly at the cap; moved to SQS + container workers on K8s (no limit) and split Lambda API (fast) from workers (long) — timeouts gone, cost down 35%.

**Failure Scenarios:** Timeout at exactly 15:00 killing the largest jobs; memory-CPU coupling surprise (128MB Lambda = also tiny CPU); payload limit on LLM contexts (6MB); concurrency cap under flash crowd → 429s from Lambda itself; per-request pricing at 50M req/month = more than a reserved VM; /tmp leftover files from prior invocation (pooled warm container reuses disk!) — sensitive data leaks between invocations on shared instance; sync invocation of heavy LLM call exceeding gateway 29s timeouts.

**Best Practices:** Right primitive for job length; reserved/provisioned concurrency for critical paths; fan-out chunking for big jobs; keep handlers stateless; /tmp cleaned (or use unique filenames); pricing model review quarterly vs utilization; streaming via response streaming for LLM; idempotency for retried functions (limit-induced retries!).

**Anti-Patterns:** 15-minute batch jobs on Lambda; 128MB for compute-heavy work; holding DB connections per invocation (pool per warm instance only); ignoring /tmp reuse; serverless for steady high-throughput sustained services (containers cheaper).

**Trade-offs:** Performance (great for spiky scale, poor for steady heavy compute); complexity (platform handles infra; queue plumbing adds app complexity); cost (winners at low utilization; loses at sustained load); consistency (stateless by necessity); maintainability (platform lock-in).

**Testing:** Timeout-bound test (largest payload completes < cap); load to reserved concurrency; cost model audit; /tmp leak test across invocations on same instance; concurrency exhaustion drill.

**Related Concepts:** `#89 Cold Starts`, `#92 Throughput`, `#88 Cost Optimization`, `#11 Timeouts`, `#46 Horizontal Scaling`.

**Decision Criteria:** Use when: spiky, stateless, short-duration workloads; scale-to-zero savings real. Do not use when: sustained 24/7 throughput (containers win); >15min jobs; heavy GPU; stateful/websockets (containers). Alternatives: K8s/ECS containers, Cloud Run, batch (Fargate/Spot), Kubernetes jobs.

### 91. Latency

**Definition:** The elapsed time from request arrival to response delivery (often split: DNS, connect, TLS, TTFB/wait, body transfer); measured as a distribution, never an average.

**Problem:** "Average latency 120ms" hides that 5% of requests take 3s — and those are exactly the ones making your product feel broken and blowing SLOs.

**Internal Working:** Cost sources: network RTT, queueing (the dominant factor at high utilization — Little's Law: L = λW; as utilization →100%, queue time →∞), GC/runtime, DB (connection pool wait, lock wait, disk), downstream serialization, TLS handshake. Amdahl's Law limits parallel speedup; Universal Scalability Law shows contention (serialization) and coherency (cross-node chatter) dominate at scale. Measure at the edge (client-side) AND server-side — they differ; server sees only handler time. Percentiles from histograms (`histogram_quantile`); never averages; always segment by route — one slow route skews nothing if tracked separately.

**Architecture:** Budget decomposition along the call chain (each hop a line item with an owner); CDN/edge trims network latency; caches trim compute; pooling trims connection cost.

**Implementation:**

```python
@app.middleware("http")
async def timing(request, call_next):
    t = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time"] = f"{(time.perf_counter()-t)*1000:.1f}ms"
    return response
```

```promql
h = histogram_quantile(0.95, sum by (le, route) (rate(http_request_seconds_bucket[5m])))
```

**Production Example:** p95 700ms on `/orders`: breakdown showed 300ms payload encryption at gateway + 200ms DB + 100ms handler; moved serialization off hot path (orjson) and added covering index → 180ms p95; dashboard per hop made the fix obvious in one hour.

**Failure Scenarios:** Optimizing averages (user pain hidden); optimizing the wrong hop (cache the cache, not the DB); measurement at server only (client sees 2x more via network); TLS re-handshake per request (no keepalive); connection pool wait invisible (use pool wait metric); latency regression after a " harmless" dependency bump; no per-route breakdown — global p95 masks one bad endpoint; testing at low load then deploying to 10x.

**Best Practices:** Measure percentiles, per route; decompose along the path (edge → app → DB); budgets per hop with owners; keepalive end-to-end; balance payload size; optimize the top offender only (profile first); test at production-like load; SLOs on tail not mean.

**Anti-Patterns:** Average as success metric; optimizing before profiling; micro-optimizing JSON parsing of a 10ms endpoint while DB takes 2s; no client-side measurement; tools tuned to 95th percentile only (P99 and P999 still hurt).

**Trade-offs:** Performance (the core metric); complexity (profiling discipline); cost (edge capacity/caching infrastructure); consistency (read-your-writes costs latency — choose per feature); maintainability (latency budgets reviewed per PR).

**Testing:** k6/Locust at production-like RPS asserting p95/p99 thresholds; before/after benchmark on the targeted endpoint; load at 2x peak for headroom; CI performance regression gate; real-user monitoring (RUM) verification.

**Related Concepts:** `#92 Throughput`, `#93 P99 Latency`, `#94 Tail Latency`, `#2 Caching`, `#11 Timeouts`, `#28 Connection Pooling`.

**Decision Criteria:** Use when: always — measure everything, budget everything. Do not use when: n/a; but prioritize optimization only after profiling. Alternatives: latency SLOs + budgets (process, not alternative), throughput-vs-latency trade knobs (concurrency, queues).

### 92. Throughput

**Definition:** The rate of completed work per unit time — requests per second, messages per second, rows per second; the system's capacity envelope, bounded by the slowest stage and available resource.

**Problem:** Underprovisioned capacity = queue growth and latency collapse at peak; overprovisioned = pure waste; ignorance of the bottleneck stage = scaling the wrong thing (buying app CPU when the DB is the ceiling).

**Internal Working:** Little's Law (L = λW) relates in-flight work, arrival rate, latency; saturation at any stage throttles everything (constraint theory). Bottlenecks: CPU (serialization, crypto), DB (connection pool, locks, IO), network (bandwidth, TLS termination), downstream quotas. Capacity planning: measure saturation → add the constrained resource; Amdahl: parallelism ceiling; load testing validates the model; autoscale on saturation metric (queue depth/CPU/connections), not guessed traffic. Throughput vs latency: increasing batch size raises throughput at cost of latency (Little's Law again) — batch only where latency budget allows.

**Architecture:** LB → N app instances → DB/queue; autoscaler keyed to the true constraint; DB as shared capacity ceiling.

**Implementation:**

```bash
k6 run --vus 200 --duration 60s loadtest.js    # measure RPS at acceptable p99
```

```promql
rate(http_requests_total[1m])                       # current throughput
```

Capacity test at 2-3x expected peak; watch queue depth, pool wait, CPU steal.

**Production Example:** API "slow under load" — throughput plateaued at 900 RPS with CPU 40%; profiled: PgBouncer pool 20 saturated at 900 RPS (lock waits); pool →100, queries optimized → 2,400 RPS at same p99; CPU never was the bottleneck.

**Failure Scenarios:** Adding app servers when DB is saturated (more clients → more lock contention → worse); SYN backlog overflow (tune net.core.somaxconn + LB); ephemeral port exhaustion at high RPS (`TIME_WAIT` — keepalive end-to-end); throughput test at warm cache only (production cold day = 2x latency); autoscale on CPU but DB pinned (scale-out hammering a ceiling); hidden synchronous work (logging/audit flush) capping RPS.

**Best Practices:** Profile before scaling; identify the shared constraint; load test at 2x; metrics on queue/pool/lock waits; keepalive; capacity review quarterly; headroom 30-50% on the constraint; scale on saturation, not calendar; document known ceilings (provider quotas!).

**Anti-Patterns:** "Just add replicas" without finding the bottleneck; ignoring provider quotas (NAT/VPC/Redis connections); one big server when sharding needed; over-provisioning steady state instead of autoscaling bursts; p99 violated while quoting RPS.

**Trade-offs:** Performance (throughput vs latency tradeoffs explicit); complexity (load modeling); cost (capacity vs SLO); consistency (caching to raise throughput adds staleness); maintainability (capacity dashboards reviewed).

**Testing:** Staged load ramp to failure; capacity test before launches; regression benchmarks per release; production-like data volumes; quota verification tests (DB max_connections vs N pods × pool).

**Related Concepts:** `#91 Latency`, `#93 P99 Latency`, `#45 Autoscaling`, `#46 Horizontal Scaling`, `#44 Backpressure`, `#28 Connection Pooling`.

**Decision Criteria:** Use when: capacity planning phase for any public service. Do not use when: pre-product-market-fit toy (but measure from day one anyway). Alternatives: queue-based load leveling (absorb peaks without sizing for them), backoff/degradation policies.

### 93. P99 Latency

**Definition:** The 99th-percentile response time — 1 in 100 requests is slower than this; the SLO-relevant figure for tail experience.

**Problem:** Averages and even P95s hide the requests that get your service called "slow" — at scale, 1% of 10M requests = 100k bad experiences daily.

**Internal Working:** Percentiles need full distribution info — histograms in metrics (Prom histogram_quantile), HDR histograms (succinct data structure storing percentiles exactly at low cost), or reservoir sampling. Causes of tail: GC pauses, lock/queue waits, cold cache, slow queries (plan flips), noisy neighbors (shared VMs), network retransmits, retry amplification, stragglers in scatter-gather (fanout to 100 shards → P99 determined by slowest shard). Fixes: hedging/cancellation, backup requests, cache warming, pool headroom, isolation of slow tenants, removal of lock convoys.

**Architecture:** Measured at every tier of the call graph; SLOs defined on it; dashboards split by route/tenant; exemplars link slow traces directly.

**Implementation:**

```promql
histogram_quantile(0.99, sum by (le, route) (rate(http_request_seconds_bucket[5m])))
histogram_quantile(0.99, sum by (le, route) (rate(http_engine_request_seconds_bucket{engine="llm"}[5m])))
```

Histogram buckets set deliberately around the SLO (e.g., include 0.3s, 0.5s, 1s boundaries).

**Production Example:** Search API p95 120ms but p99 4s; traces showed 2% of queries hit a stale plan → seq scan on 40M rows; planner hints + index fixed; p99 150ms; ALSO found GC pause tail in the worker — moved to ZGC; variance gone.

**Failure Scenarios:** SLOs on p50 (meaningless for tail); SLO set from a bad histogram boundary configuration (P99 invisible — bucket ends at 500ms, everything above is an overflow bucket); alert at mean only; p99 spike isolated to one tenant (noisy neighbor — needs per-tenant dashboard); ignoring P999 (Fanout/tail for 100+ parallel shards); fixing tail with more retries (amplifies!).

**Best Practices:** SLOs on p99 (and p999 for fanout-heavy); custom histogram buckets incl. SLO boundary; per-route + per-tenant split; trace exemplars on the p99 bucket; budget headroom ≥30%; fanout cancellation (hedged requests after p95 threshold); tail-focused chaos tests.

**Anti-Patterns:** Average-as-SLO; tail ignored because "it only affects 1%"; retries increasing tail; no bucket near SLO boundary; global p99 across heterogeneous routes.

**Trade-offs:** Performance (fixing tail often fixes throughput too); complexity (profiling + hedging logic); cost (headroom and isolation replicas); consistency (hedged reads may duplicate work); maintainability (budget culture + dashboards).

**Testing:** Load test reporting p95/p99/p999 per route; hedged-request integration test (cancel losing request); chaos: GC injection, dependency latency +50% → assert p99 still under SLO; per-tenant hot-key test.

**Related Concepts:** `#91 Latency`, `#94 Tail Latency`, `#66 Observability`, `#92 Throughput`, `#2 Caching`, `#42 Garbage Collection`.

**Decision Criteria:** Use when: any user-facing production service with SLOs — always. Do not use when: n/a. Alternatives: HDR histogram-based percentiles for exactness; tail-sampling traces keyed on the slow ones.

### 94. Tail Latency

**Definition:** The slowest fraction of requests — the tail of the distribution; in distributed calls with N parallel subrequests, the request itself is slow if ANY subrequest is (tail amplification).

**Problem:** A request hitting 50 shards fails its latency budget if the slowest does — p99 of subcalls becomes p90+ of the whole operation; without tail-specific countermeasures, fine components still yield awful UX.

**Internal Working:** Causes: queueing (M/M/1 queue delay explodes near saturation), stragglers (GC pauses, lock waits, disk I/O, retransmits), head-of-line blocking, plan flips, hot partitions (Kafka/DB), synchronization barriers. Countermeasures: **hedged/backup requests** (send duplicate at p95 delay, take first, cancel loser — costs extra load), **tied requests**, micro-batching, avoiding locks, killing GC pauses (low-pause GCs), provision at 60-70% utilization (queueing non-linear above), isolation for multi-tenant, cache-warming for cold paths. Measure fanout contribution: parent p99 vs max child p99.

**Architecture:** Measured per hop across the call graph (edge -> gateway -> service -> fanout children -> DB); SLOs and exemplars anchor it; hedging/deadline propagation happen inside the service client, not the platform.

**Implementation:**

```python
async def hedged(call, p95_threshold=0.08):
    task1 = asyncio.create_task(call())
    done, pending = await asyncio.wait({task1}, timeout=p95_threshold)
    if done: return done.pop().result()
    task2 = asyncio.create_task(call())               # backup request
    done, pending = await asyncio.wait({task1, task2}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending: t.cancel()
    return done.pop().result()
```

(Hedging only for idempotent reads.)

**Production Example:** Recommendation fanout: 40 shard calls per request; shard p99 80ms → parent p99 600ms; hedged requests after 60ms cut parent p99 to 120ms; added 9% read load accepted; budget saved.

**Failure Scenarios:** Hedging non-idempotent writes (double charge!); hedging under overload → extra load speeds collapse (apply only with headroom + circuit breaker); timeout instead of hedging on every child (strict cancellation needed — propagate deadline); fanout without deadline propagation (orphaned children keep hammering); hedging hides the underlying slow component forever (should still fix root cause); per-tenant whale shard unhandled.

**Best Practices:** Hedge only idempotent ops, with deadline propagation; cap hedge extra traffic (<20%); fix straggler root causes; utilization headroom; fanout deadline propagation; monitor parent-vs-shard fanout ratio; design for stragglers (small redundant reads); per-tenant isolation.

**Anti-Patterns:** Tail ignored until SLO breach; hedging writes; hedging during capacity crisis; no cancellation of the loser; uninstrumented fanout internals; "more servers" without fixing queueing near saturation.

**Trade-offs:** Performance (hedged adds latency wins at extra load cost — 5-15%); complexity (deadline propagation discipline); cost (redundant execution); consistency (first-finisher wins — fine for reads); maintainability (dedup of results not needed — first response used).

**Testing:** Inject 100ms straggler in one of 10 children → parent meets budget via hedging; cancellation test asserting no orphan work; load test at p95 queue pressure; fanout ratio dashboard check; chaos GC pause drill.

**Related Concepts:** `#93 P99 Latency`, `#91 Latency`, `#12 Retries`, `#44 Backpressure`, `#43 Thread Safety`, `#60 Distributed Tracing`.

**Decision Criteria:** Use when: fanout/many-parallel architecture or strict tail SLOs with headroom to spare. Do not use when: system at saturation, writes, tight margins. Alternatives: capacity headroom, caching, better partitioning/lock elimination.

<!--END-->
