# Distributed Systems & Messaging Reference

Covers topics 15-20 (queues, pub/sub, EDA, distributed transactions, sagas, DLQs), 33-35 (leader election, CAP, eventual consistency), 38 (distributed locks), 41-44 (memory, GC, thread safety, backpressure), and 95-96 (network partitions, clock skew).

Foundational distributed-systems theory and the operational hazards of concurrent code: leader election, CAP, consistency, distributed locks, memory, GC, thread safety, backpressure, partitions, and clock skew.

| # | Concept | One-line use case |
|---|---|---|
| 33 | Leader Election | Pick one writer among replicas |
| 34 | CAP Theorem | Know what fails when the network fails |
| 35 | Eventual Consistency | Accept lag for availability and scale |
| 38 | Distributed Locks | Mutual exclusion across machines |
| 41 | Memory Leaks | Unbounded growth prevention and diagnosis |
| 42 | Garbage Collection | Know when GC pauses your P99 |
| 43 | Thread Safety | Correctness under concurrency |
| 44 | Backpressure | Slow producers, don't drown |
| 95 | Network Partitions | Design for split networks |
| 96 | Clock Skew | Never order events by wall clock |

### 33. Leader Election

**Definition:** The process by which a group of nodes agrees on one leader to coordinate writes or critical sections, with the others standing by to take over on failure.

**Problem:** Without a single leader, two nodes both accept writes and diverge (split-brain), corrupting data or double-charging — or duplicate batch jobs run concurrently.

**Internal Working:** Consensus-based election (Raft/Paxos) or lease-based election with a shared store (etcd/ZooKeeper with TTL + fencing tokens; Consul sessions). Raft: candidate requests votes from majority; majority wins; leader replicates log entries; follower election timer (~150-300ms) triggers new election on silence. Fencing: the leader must attach a monotonically increasing **fencing token** to protected writes; the storage system rejects tokens lower than the last seen — this is what actually stops a deposed leader (e.g., GC pause then write) from corrupting data. Leases need renewal < TTL; holder must prove leadership on every critical write, not just at acquisition.

**Architecture:** Leader + followers behind a virtual IP or through a consensus-backed registry; clients route to leader or through a load balancer that understands leadership.

**Implementation:** Patroni (Postgres HA) uses etcd as the DCS with fencing; Kafka uses controller election via KRaft/ZooKeeper; Redis Sentinel for cache failover; app-level: `SET lease NX PX 10000` with a uniqueness token (uuid) + compare-and-delete renewal via Lua.

```python
import uuid
FENCE = uuid.uuid4().hex
r.set("leader:scheduler", FENCE, nx=True, px=15000)   # acquire
# renew halfway through the lease with Lua: only delete/re-set if we still hold it
```

**Production Example:** Nightly billing scheduler on 3 pods; etcd-backed lease; fencing token passed to the DB so a partitioned leader's stale UPDATE is rejected after a new leader emerges; zero double invoices during a network partition.

**Failure Scenarios:** Leader GC-pauses 30s, lease expires, new leader elected, old leader wakes and writes — without fencing tokens → corruption; split brain with two primaries on both sides of partition; flapping (election every 200ms) due to short timeouts or slow acks; DCS (etcd) unavailable → no new leader can be elected (failover stalls); lease renewal blocked by a full event loop (no election but also no renewal) → leadership lost predictably at ~TTL.

**Best Practices:** Always fencing tokens; TTL ~ 3-10× RTT, renew at 1/3; election timeouts randomized; monitor leadership changes and lease expirations; never assume "I acquired it, I keep it"; test failover; treat DCS as a critical dependency with alerting.

**Anti-Patterns:** Election without fencing (the classic "zombie leader" bug); lease longer than your outage tolerance; heartbeat from the same event loop as the work; leader performing writes without checking the token; "leader" by config flag in a deploy (two leaders after config drift).

**Trade-offs:** Performance (election is rare, negligible steady-state cost); complexity (high when hand-rolled — use Patroni/K8s/etcd); cost (DCS infra); consistency (strong within leader's term); maintainability (standard engines ≫ custom).

**Testing:** Network-partition chaos test (block leader); GC-pause injection; verify stale-token write rejected; failover drill measuring time-to-new-leader; election-storm test under flaky links.

**Related Concepts:** `#32 Replication`, `#95 Network Partitions`, `#38 Distributed Locks`, `#85 Failover`, `#96 Clock Skew` (lease timing), `#8 Kubernetes`.

**Decision Criteria:** Use when: one writer must exist — schedulers, primary DB, partition assignment. Do not use when: stateless handlers (LB handles this), reads-only. Alternatives: K8s leader election (Lease object), single replica + Patroni, consensus DB (etcd/ZooKeeper) as source of truth.

### 34. CAP Theorem

**Definition:** In the presence of a network partition (P), a distributed system must choose between consistency (C — all nodes see the same data) and availability (A — every request gets a non-error response). When the network is healthy you get both; the theorem only constrains partition behavior.

**Problem:** Teams discover too late that their "highly available" system returned divergent data during a partition — or that their "consistent" system returned 100% errors instead of reads.

**Internal Working:** Partition tolerance is not optional for anything crossing a network (the network *will* partition). During a partition, a node that cannot see its peers must either serve potentially stale data (favor A — Dynamo/Cassandra, AP) or refuse to serve (favor C — Spanner/etcd via consensus, CP). Genuine CA exists only within one machine. Important refinements: PACELC extends the trade-off to normal operation (latency vs consistency); many systems mix modes (MongoDB per-node read concern, etcd linearizable reads). CAP is about *availability of the whole system during partitions*, not about consistency quality otherwise.

**Architecture:** DB selection + replication mode + client routing decisions; all derived from which side of CAP you pick for each operation.

**Implementation:** CP: etcd/Consul/ZooKeeper, Postgres synchronous replication, Spanner. AP: Cassandra (tunable consistency per query: QUORUM, ONE), DynamoDB (eventually + conditional writes for critical keys), Redis (AP-ish with async replication). Mixed: read replicas with consistency routing.

**Production Example:** Cart service on Cassandra with `LOCAL_QUORUM` writes/reads; during an AZ partition the store keeps serving (AP) — carts may briefly diverge; checkout reconciles via conflict resolution (last-write-wins with timestamp + business rule for money-ish fields). Analytics reads never block writes.

**Failure Scenarios:** AP system shows stale/price-drift data during partition → customer anger, support tickets; CP system hard-fails everything → 100% error rate during partition; quorum loss (2 of 3 down) → no majority, no writes; "CA" assumptions invalidated by a single cross-AZ link; misreading CAP as "pick 2 of 3" and ignoring partition as inevitability.

**Best Practices:** Choose per data class: money → CP; cart/session → AP with reconciliation; presence → AP; accept stale reads only with explicit contract; document the chosen behavior during partitions; test partitions (chaos), not just theory; monitor quorum health.

**Anti-Patterns:** "We're CA"; claiming MongoDB is CP/AP without understanding read/write concern; strong consistency required but AP DB chosen for scale; AP for financial balance without reconciliation; ignoring quorum sizing (even counts split).

**Trade-offs:** Performance (AP wins latency; CP pays consensus RTT); complexity (AP needs conflict resolution; CP needs quorum ops); cost (CP consensus quorum more nodes; AP eventual reads cheaper); consistency (the theorem itself); maintainability (AP requires reconciliation discipline).

**Testing:** Chaos partition test (drop traffic between DCs); assert documented behavior: CP rejects, AP serves; verify conflict-resolution rules at scale; quorum-loss drill; verify alerting on quorum degradation.

**Related Concepts:** `#35 Eventual Consistency`, `#32 Replication`, `#33 Leader Election`, `#95 Network Partitions`, `#96 Clock Skew`, `#86 Multi-Region Deployment`.

**Decision Criteria:** Use when: choosing storage/replication semantics — it is a decision lens, not a feature. Do not use when: single-node deployment (CAP is meaningless there). Alternatives: per-operation consistency levels, CP consensus for control plane, AP for data plane.

### 35. Eventual Consistency

**Definition:** A consistency model in which, absent new updates, all replicas converge to the same value after some (usually sub-second) propagation delay; readers may observe stale data in the interim.

**Problem:** Requiring synchronous global consistency destroys availability and latency at scale; but unmodeled staleness causes user-visible contradictions (cart shows item, checkout says sold out).

**Internal Working:** Writes accepted by one replica, propagated asynchronously (WAL streaming, gossip, log shipping). Convergence mechanisms: last-write-wins (needs timestamps — beware `#96 Clock Skew`), CRDTs (counters, sets with mathematical merge — Riak, Redis CRDT Enterprise), version vectors for detecting concurrent writes, read-repair and hinted handoff in Dynamo-style systems. Bounded staleness SLAs (e.g., Cosmos DB's ≤ 5s, or session tokens guaranteeing read-your-writes within a session) make it usable.

**Architecture:** Replicas/caches/read models everywhere; consistency is restored by propagation + occasional reconciliation (anti-entropy, read repair, scheduled audits).

**Implementation:** Read replicas with LSN check for session consistency:

```python
ws = write_engine.connect().scalar(select(func.pg_current_wal_lsn()))   # after write
# route subsequent reads to replica; wait until replay_lsn >= ws (or fallback to primary)
```

Cassandra per-query `CONSISTENCY QUORUM`; cache TTL as bounded staleness (60s); outbox/CDC projection lag metric; client `X-Session-ID` + token for read-your-writes.

**Production Example:** Product pages served from Redis cache with 60s TTL and invalidation on write via pub/sub — 95% cache hits, max 60s staleness; inventory counts always read from primary (strongly consistent) while descriptions come from cache.

**Failure Scenarios:** Unbounded lag without monitoring → day-old data in dashboards; last-write-wins silently overwrites earlier write depending on clock; read-your-writes violation right after write (user sees stale profile); no reconciliation job → permanent divergence in projections; cache invalidation missed → user sees deleted content forever (TTL saves you); using eventual data for authorization decisions (cached role revoked 60s late — acceptable? define it).

**Best Practices:** Define per-field staleness budgets; read-your-writes for the writing user; monotonic reads within session; version vectors instead of wall clocks; reconciliation/anti-entropy jobs; lag metrics with alerts; invalidation on write, TTL as backstop; never for security-critical revocation unless TTL is tiny.

**Anti-Patterns:** "Eventually consistent" with no bound stated; relying on TTL alone for invalidation; wall-clock ordering; ignoring convergence testing; stale authz caches without TTL discipline.

**Trade-offs:** Performance (excellent — no cross-node waits); complexity (moderate — conflict rules); cost (cheaper reads); consistency (the model itself); maintainability (needs lag observability).

**Testing:** Convergence test (write once, assert all replicas equal within bound after poll); lag-injection test; conflict-resolution unit tests (concurrent writes); user-facing read-your-writes assertion; chaos test killing a replica and verifying no stale reads beyond bound.

**Related Concepts:** `#34 CAP Theorem`, `#50 Cache Invalidation`, `#29 Read Replicas`, `#14 Idempotency`, `#96 Clock Skew`, `#30 Sharding`.

**Decision Criteria:** Use when: high read scale, availability over immediacy, social/feed/cart/profile data. Do not use when: balances, inventory enforcement, authz revocation, anything where stale = money or access. Alternatives: strong consistency (primary reads), session consistency, CRDTs for collaborative state.

### 38. Distributed Locks

**Definition:** A mutual-exclusion mechanism spanning multiple processes/nodes — exactly one holder across the fleet — typically implemented on Redis, etcd, or a database.

**Problem:** When correctness requires one-and-only-one actor across machines (billing job, inventory leader, outbound webhook sender), in-process locks do nothing.

**Internal Working:** Redis `SET key uuid NX PX ttl` acquire; heartbeat renewal via Lua compare-and-PEXPIRE; release via Lua compare-and-del (only delete if we hold the token). Redlock (multiple Redis nodes) is controversial — Martin Kleppmann showed timing assumptions break it; the robust answer is a consensus-backed lease (etcd) with a **fencing token**. Database advisory locks (`pg_advisory_lock`) work within Postgres. Critical requirements: (1) TTL — holder may die silently; (2) unique token per acquisition; (3) TTL > worst-case critical section; (4) fencing at the protected resource.

**Architecture:** App nodes → shared lock store (Redis/etcd/Postgres advisory) → protected resource (DB, external API). The lock only coordinates; correctness still requires the resource to validate the fencing token.

**Implementation:**

```python
import time, uuid, redis
r = redis.Redis()

def with_lock(key, ttl_ms=10000, tries=3):
    token = uuid.uuid4().hex
    for _ in range(tries):
        if r.set(f"lock:{key}", token, nx=True, px=ttl_ms):
            try:
                yield token                      # critical section
            finally:
                r.eval("if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
                       1, f"lock:{key}", token)
            return
        time.sleep(0.1 * (tries + 1))
```

Celery: `lock = redis.lock("nightly-close", timeout=3600, blocking_timeout=0)`; DB: `SELECT pg_try_advisory_lock(42)`.

**FastAPI Example:** Dependency that acquires `lock:endpoint-name` for a guarded admin operation; returns 409 if not acquired; the guarded action then carries a fencing token to the DB.

**Production Example:** 3 replicas of the invoice-email sender before a Black Friday deploy; Redis lock with 30s TTL + fencing column `sent_by_token` in the `invoices` table guarantees exactly one email even if a GC pause runs the holder past TTL; the surviving lock holder's fencing token is honored only if higher.

**Failure Scenarios:** Lock holder GC-pauses past TTL; new holder starts; both "hold" — without fencing, both act on shared state; lock acquired but renewal thread starved (same loop as work) → lease expires mid-task; unlock by simple DEL without compare → unlocks someone else's lock; Redis down → lock service down → decide fail-open (split-brain) or fail-closed (unavailability) deliberately; lock scope too broad (whole job vs the single record) → unnecessary serialization.

**Best Practices:** TTL > critical section with margin; renew at TTL/2 via dedicated heartbeat; fencing tokens on the protected write; unique tokens; narrow-scope keys per resource; handle acquisition failure explicitly (409/skip); monitor lock hold time and contention; chaos test the holder pause.

**Anti-Patterns:** `SETNX` without TTL (deadlock forever); unlocking without compare-and-delete; locks without fencing as a correctness guarantee; TTL == critical section duration exactly; using a lock for rate limiting; lock contention on the hot path (queue instead).

**Trade-offs:** Performance (serialization — hold as briefly as possible); complexity (moderate; subtle failure modes); cost (tiny); consistency (fencing required for rigor); maintainability (fencing discipline in every protected write).

**Testing:** Pause-holder test (monkeypatch sleep > TTL) asserting fencing rejects stale writes; concurrent acquirer test; lock-store-down drill (fail-open vs fail-closed documented); verify unlock releases only own lock.

**Related Concepts:** `#33 Leader Election`, `#21 Cron Jobs`, `#12 Retries`, `#14 Idempotency`, `#39 Race Conditions`, `#96 Clock Skew` (TTLs assume bounded error).

**Decision Criteria:** Use when: cross-node single-writer for a short critical section (job dedup, migration gate). Do not use when: hot path with high contention (queue/serialize instead); you need strict correctness — then use consensus + fencing (etcd) not Redis Redlock; single process (asyncio.Lock is enough). Alternatives: DB row locks (`#37 Pessimistic Locking`), unique constraints, `SKIP LOCKED` queue, single-leader scheduling.

### 41. Memory Leaks

**Definition:** Memory allocated but never released, growing unboundedly over process lifetime — caches without eviction, unclosed resources, accumulating lists, reference cycles, or leaks in native extensions.

**Problem:** The service works for hours then OOMs (Linux OOM-killer takes it down) or GC-thrash; Kubernetes restarts it in a crash loop; p99 latency spikes; data lost mid-request.

**Internal Working:** Python growth sources: module-level dict/list/set caches (no eviction); ORM session identity map holding objects; unclosed file/socket/DB handles; listener/callback registrations accumulating; C-extension leaks; circular references through __del__ (rare) — CPython ref counting usually cleans cycles via generational GC but cycles with finalizers can persist. Diagnose: `tracemalloc` snapshots diffed over hours, `objgraph` growth by type, `py-spy dump --native` for native, RSS trend via Prometheus `container_memory_working_set_bytes`. Restart band-aids mask but never fix — find the retained object.

**Architecture:** Any process: API servers, workers, schedulers. Leaks matter most in long-lived processes (not request-scoped ones).

**Implementation:**

```python
import tracemalloc
tracemalloc.start()
snap1 = tracemalloc.take_snapshot()
# ...hours later...
for line in snap1.compare_to(tracemalloc.take_snapshot(), "lineno")[:10]:
    print(line)
```

Rules: caches use LRU with maxsize (functools.lru_cache(maxsize=512) / cachetools TTLCache); close resources (`with` / async context managers); SQLAlchemy sessions per-request and closed; no global mutable lists; periodic RSS alert (container_memory_working_set_bytes > 80% limit for 10min).

**FastAPI Example:** Dependency creates/closes `Session` per request (GC'd); module-level `lru_cache` capped; streaming endpoints close upstream clients in finally; app factory avoids import-time globals holding refs.

**Production Example:** Embedding worker grew RSS 300MB → 4.2GB over 36h; tracemalloc showed a global list of every processed document's vector reference never cleared; fixed with bounded TTLCache; RSS flat at 700MB; alert added at 1.5GB.

**Failure Scenarios:** OOM-kill under load spike (not steady state) — hard to reproduce in staging; GC-thrash P99 (memory near limit → GC work explodes); leak in a rarely-hit error path (only triggered on failures — nobody notices); connection pool sessions retained via long-lived registry → 500s from exhausted pools masquerading as DB issues; container restart hides leak → from metrics, "it self-heals" — until it doesn't.

**Best Practices:** Bounded caches only; close everything (with/finally); per-request scopes; RSS alerting at 80% limit; leak reproduction test running N iterations asserting flat-ish RSS; py-spy/tracemalloc in staging profile; periodic dependency/native lib updates; review globals.

**Anti-Patterns:** "It restarts nightly, ship it"; unbounded module-level list/dict caches; catching and swallowing exceptions while holding references; long-lived ORM session as registry; no RSS metric — leaks discovered by customers.

**Trade-offs:** Performance (leak fixes often also cut GC pressure); complexity (diagnosis is forensic work); cost (sized-down containers mask it); consistency (n/a); maintainability (code review + metrics prevent recurrence).

**Testing:** Long-running pytest/soak test: 5k iterations of a representative request, assert tracemalloc growth < 10MB; RSS plateau test; CI leak gate on micro-benchmarks; staging soak under production-like traffic; alert-verification drill.

**Related Concepts:** `#42 Garbage Collection`, `#28 Connection Pooling`, `#58 Monitoring`, `#40 Deadlocks` (different but often co-investigated), `#90 Serverless Limits` (memory ceiling).

**Decision Criteria:** Use when: long-lived processes — always hunt leaks; batch jobs can be looser. Do not use when: short-lived CLI (not worth deep profiling). Alternatives: process-per-request isolation (FaaS), scheduled restarts (band-aid, not a fix), bounded queues.

### 42. Garbage Collection

**Definition:** Automatic reclamation of unreachable memory; in CPython, reference counting plus a generational cycle detector; in JVM/Go/JavaScript-style engines, tracing collectors (G1, ZGC, concurrent mark-sweep) with pause characteristics.

**Problem:** GC pauses manifest as P99/P999 spikes that look like "slow DB" or "noisy neighbor"; misconfigured collectors cause stop-the-world freezes or excessive CPU overhead.

**Internal Working:** CPython: every object has a refcount; reaching zero frees immediately (deterministic) — no long pauses; cycles broken by generational GC (3 generations, thresholds 700/10/10 allocations — tunable via `gc.set_threshold`); `gc.disable()` can help short-lived fork-heavy workers but hides cycles. JVM: allocation in young gen, survivors promoted; G1/ZGC aim for < 200ms pauses; humongous objects and old-gen pressure cause full GCs. Go: concurrent mark-sweep, sub-millisecond pauses typical, assist overhead under high allocation rate. Practical rule: know your runtime's pause profile and measure allocation rate, not just heap size.

**Architecture:** Runtime feature; visible to ops via GC metrics, allocation rates, heap utilization, pause histograms.

**Implementation:** Python: measure `gc.get_stats()` and counts; freeze long-lived objects (`gc.freeze()` on startup) to cut cycle GC work; avoid creating reference cycles in hot paths (return new objects, don't tangle graphs); prefer streaming generators over giant lists. JVM: ZGC (`-XX:+UseZGC`) or G1 tuning (`-XX:MaxGCPauseMillis=100`); Go: `GOGC=100` default, tune up with heap headroom.

**FastAPI Example:** Avoid per-request allocations of large structures; reuse serializers/clients; streaming responses yield chunks instead of building whole bodies; `gc.freeze()` after loading models/warmup in the lifespan handler so startup objects are never scanned.

**Production Example:** Inference API p99 = 900ms; profiling showed allocation rate 800MB/s and G1 full GC every 4 minutes (200-400ms pauses); fixed by streaming embeddings + object reuse → full GCs gone, p99 = 60ms.

**Failure Scenarios:** Latency spikes every N minutes correlating to GC log; cgroup memory limit — GC sees less memory than heap needs → constant collection; C-extension allocated buffers invisible to GC but counted in RSS → OOM; disabling GC in CPython with cycles → true memory infinite growth; promotion of short-lived objects into old gen (premature tenure) thrashing.

**Best Practices:** Emit GC/pause metrics; know your runtime defaults; reduce per-request allocations; stream, don't materialize; freeze startup state; test P99 under sustained load, not just throughput; coordinate GC with deploys (warm before LB routes); review container memory vs GC headroom.

**Anti-Patterns:** "Just add more memory"; ignoring GC logs during incident RCA; `gc.disable()` without leak audit; giant in-memory structures as "cache"; allocating per request in hot async paths; misreading GC time as database latency.

**Trade-offs:** Performance (tracing GC overhead ~5-15% CPU; ZGC/Shenandoah near-zero pauses, higher overhead); complexity (tuning needs runtime expertise); cost (memory headroom); consistency (n/a); maintainability (allocation discipline in code review).

**Testing:** Load test measuring p99 + GC logs; allocation-rate benchmark; memory growth curve over 1h soak; container-limit test (GC behavior near ceiling); assert absence of full GCs in staging profile.

**Related Concepts:** `#41 Memory Leaks`, `#93 P99 Latency`, `#94 Tail Latency`, `#90 Serverless Limits`, `#58 Monitoring`.

**Decision Criteria:** Use when: you operate any runtime — GC tuning is always relevant for latency-sensitive services. Do not use when: short scripts. Alternatives: allocation-free hot paths, manual memory arenas (Rust/C++), region-based allocators off-heap.

### 43. Thread Safety

**Definition:** A property of code that is correct when accessed by multiple threads concurrently — no data races, corrupted invariants, or visibility anomalies.

**Problem:** Concurrent access to shared mutable state produces heisenbugs that pass all tests and corrupt production data exactly when it matters most (payroll, midnight batch).

**Internal Working:** Data race = two threads access same memory, at least one writes, no synchronization. Fixes: mutual exclusion (locks/semaphores), atomic operations (CAS), immutability, message passing (CSP/actor model), thread-local storage, confinement. CPython's GIL serializes bytecode — protects the interpreter, **not** your invariants: check-then-act across bytecodes still races, and the GIL is per-interpreter (3.13+ per-subinterpreter GILs change the picture).asyncio is single-threaded — races appear between await points, not between bytecodes; `asyncio.Lock` covers await-spanning critical sections.

**Architecture:** In-process concurrency model; crosses into distributed coordination at `#38`.

**Implementation:**

```python
import threading
_lock = threading.Lock()
_counter = 0
def increment():
    global _counter
    with _lock:
        _counter += 1

import asyncio
_alock = asyncio.Lock()
async def aupdate(state):
    async with _alock:
        state.total += state.amount
```

Rules: no mutable module-level globals mutated per request; use immutable DTOs; queue-based handoff (`queue.Queue`, asyncio.Queue) for producer/consumer; `concurrent.futures` with proper futures handling; thread-local DB sessions.

**FastAPI Example:** Handlers are async — shared request-independent clients (httpx, Redis) fine; per-request state passed as parameters; never store per-request data on module-level objects; sync endpoints (def) run in a threadpool — avoid shared mutable singletons entirely; middleware must not hold references across requests.

**Production Example:** A global `dict` metrics registry in a sync Flask shim under gunicorn threads: concurrent `+=` lost 0.3% increments; fixed with `threading.Lock` (or `prometheus_client` its own locking — delegate to it).

**Failure Scenarios:** Check-then-act race on shared cache (both compute, both write); double-checked locking without proper memory barriers; iterating a dict being mutated (RuntimeError); `list.append` is atomic-ish under GIL but logically not a transaction; coroutine race across `await` boundaries; requests leaking state through module globals; forked workers sharing CoW structures unexpectedly.

**Best Practices:** Immutability by default (frozen dataclasses, tuples); confine state; locks narrow and short; avoid shared state via message passing; use thread-safe primitives (Queue, prometheus_client); review `await` spacing for invariant breaks; run with `PYTHONASYNCIODEBUG=1`; document synchronization design.

**Anti-Patterns:** "The GIL makes me safe"; `global` counters without locks; mutable default arguments shared (def f(x, cache={})); check-then-act without lock; lock copied into background thread while original expires; asserting thread safety by running the test 1000 times on one machine.

**Trade-offs:** Performance (locks serialize; message passing scales out); complexity (design discipline); cost (free); consistency (the whole point); maintainability (explicit ownership model in code review).

**Testing:** Stress tests: N threads hammering one counter, assert exact final value; hypothesis with concurrent futures; asyncio interleaving tests (gather with monkeypatched awaits); CI with forced GC/scheduling pressure; review of await boundaries in critical sections.

**Related Concepts:** `#39 Race Conditions`, `#44 Backpressure`, `#42 Garbage Collection`, `#40 Deadlocks` (in-process variant), `#38 Distributed Locks`.

**Decision Criteria:** Use when: always — review every shared mutable object. Do not use when: pure functions, no shared state (ideal). Alternatives: immutable data structures, single-writer event pipelines, processes over threads (fork isolation), SQLite/Postgres for coordination.

### 44. Backpressure

**Definition:** Flow control that propagates demand signals upstream so producers stop overwhelming consumers — the opposite of unbounded queueing that hides overload until collapse.

**Problem:** Unbounded queues are invisible until they aren't: latency grows to minutes, memory blows up, timeouts fire everywhere, and the overloaded consumer dies anyway — with the backlog unprocessed.

**Internal Working:** Pull-based demand (Reactive Streams: `request(n)`; gRPC flow control windows; HTTP/2 `WINDOW_UPDATE`), bounded queues (block/fail/drop oldest when full), token buckets for rate shaping, semaphores capping concurrency (`asyncio.Semaphore(50)`), credit-based consumers (Kafka pull-based prefetch ≈ backpressure built-in), Little's Law: concurrency = throughput × latency — cap concurrency to protect the slowest stage. LLM inference: admit limited concurrent sequences; extra tokens/requests wait rather than degrade all.

**Architecture:** Between every producer/consumer boundary: HTTP handler → broker → worker → DB. Each hop needs a bounded buffer and a rejection/shedding policy.

**Implementation:**

```python
import asyncio
sem = asyncio.Semaphore(20)               # at most 20 in-flight LLM calls
async def infer(prompt):
    async with sem:
        return await llm.complete(prompt)   # request 21 waits, never overload provider
```

Bounded queue: `queue.Queue(maxsize=500)`; policy on full: block with timeout → 503, or drop with metric. K8s: KEDA scale-to-queue-depth (queue → add pods), not CPU-based scaling.

**FastAPI Example:** Middleware capping concurrent requests to the expensive endpoint (return 429/503 when saturated): FastAPI + `anyio` semaphore or a reverse proxy (limit_req). Streaming endpoints: apply backpressure per-chunk, don't materialize whole responses.

**Production Example:** RAG ingestion: 10k docs/min burst; bounded 200-doc queue in Celery (backpressure to API → 503 with Retry-After); KEDA scales workers 3→40; DB write stage throttled by semaphore (pool limit 20); pipeline absorbs burst without data loss — excess is rejected cleanly at the edge, not corrupted in the middle.

**Failure Scenarios:** N+1 retries after shedding re-floods the system; full healthcheck passing while semaphore is saturated; producer ignores 503 and retries immediately; unbounded in-memory buffer "temporarily"; measuring throughput but not queue depth — no visibility until collapse; mixed priority traffic (low-priority batch starves user requests).

**Best Practices:** Bound everything (queues, concurrency, request bodies, streams); shed with 503 + Retry-After at saturation; metric queue depth and wait time; scale consumers on lag not CPU; priority lanes for user vs batch; document the shed policy; alert on sustained saturation (not transient spikes).

**Anti-Patterns:** Unlimited `asyncio.create_task` fanout; unbounded `create_task` per request; relying on broker's disk to absorb infinite lag; retrying on shed responses; healthcheck that ignores saturation; unlimited concurrency against third-party APIs.

**Trade-offs:** Performance (protects P99 under load at the cost of rejected excess); complexity (policy choices: block vs shed vs drop); cost (capacity still needed); consistency (shed = visible non-completion, safe); maintainability (explicit limits documented).

**Testing:** Load test 2x capacity and assert 503s, not 30s latencies; verify queue never exceeds bound; KEDA scale-up/scale-down drill; cancellation test (client disconnect frees slot); downstream-slow chaos test.

**Related Concepts:** `#15 Message Queues`, `#1 Rate Limiting`, `#45 Autoscaling`, `#90 Serverless Limits`, `#11 Timeouts`, `#93 P99 Latency`.

**Decision Criteria:** Use when: every stage boundary with a slower consumer. Do not use when: uniformly low load (limits never bind). Alternatives: load shedding via `#1 Rate Limiting`, priorities/QoS, queue-per-tenant fairness, scale-up (`#46 Horizontal Scaling` + `#45 Autoscaling`).

### 95. Network Partitions

**Definition:** A failure mode in which nodes in a distributed system are alive but cannot communicate with each other (dropped packets, saturated links, routing failure, AZ isolation) — the defining failure of distributed systems.

**Problem:** Treating the network as reliable produces split-brain, lost quorum, and half-written systems; partitions are guaranteed to happen eventually — your only choice is behavior during them.

**Internal Working:** Detection: heartbeats, TCP keepalive timeouts, Phi accrual failure detector (Cassandra) vs fixed thresholds (false positives), gossip. Behavior: CP systems halt (no quorum); AP systems serve and reconcile; leases must outlive the partition duration with fencing; majority quorum requires ⌊N/2⌋+1 votes; even-sized clusters split evenly (never use 2 nodes); multi-AZ latency ~1-2ms is the usual partition trigger; MTU/MTU mismatch, security groups, DNS TTL — many "partitions" are misconfig, not physics.

**Architecture:** Placement of voters, witnesses, quorum configs, FD detectors, control-plane vs data-plane separation (data plane keeps serving stale reads; control plane halts).

**Implementation:** etcd cluster of 3 or 5 voters across AZs; `raft-heartbeat = 100ms`, election timeout 1s; Patroni: `ttl=30 loops_wait=5`; chaos mesh/toxiproxy to inject partition in test; monitor `node_network_*` and inter-node RTT.

**Production Example:** 3-AZ Kubernetes control plane + etcd; an AZ network incident isolated one zone; etcd lost no quorum (2/3 alive), all services kept serving; failover plan executed — control plane reads/writes continued; the isolated AZ re-joined and caught up via log replication; zero data loss.

**Failure Scenarios:** Split-brain dual-write after failed fencing (worst case — silent corruption); 2-node cluster partitions 50/50 → no writes anywhere; asymmetric partition (A→B works, B→A dropped) fooling heartbeats; flaky MTU blackholing large packets — consensus traffic stalls but pings pass; DNS pointing to dead AZ after partition; client-side caches masking the partition until TTL expiry.

**Best Practices:** Odd voters (3/5) across AZs; fencing tokens everywhere mutable state is protected; majority quorum for anything strong; timeouts tuned above RTT, below detection SLO; runbook for partition response; chaos-test partitions quarterly; design for partition: what keeps working, what halts — and document it.

**Anti-Patterns:** 2-node "HA" clusters; same-zone replicas; no fencing; fixed heartbeat failure detectors with tight thresholds (false positives cause flapping); assuming partitions are mythical; client retries hammering partitioned backends (make them fail fast).

**Trade-offs:** Performance (odd voters add latency? no — same RTT class; quorum writes cost RTT); complexity (high — requires DCS and fencing); cost (multi-AZ redundancy); consistency (CP halts vs AP diverges); maintainability (managed services take much of this).

**Testing:** Quarterly chaos drill: sever one AZ/DC; assert (a) CP halts writes but control plane stays consistent, or (b) AP keeps serving; fencing verified by rejecting stale tokens; quorum-loss test (kill 2 of 3) → system correctly refuses; MTU blackhole test on staging.

**Related Concepts:** `#33 Leader Election`, `#34 CAP Theorem`, `#32 Replication`, `#38 Distributed Locks`, `#96 Clock Skew`, `#85 Failover`, `#86 Multi-Region Deployment`.

**Decision Criteria:** Use when: architecting any system >1 node with shared state — always. Do not use when: single point by definition (laptop). Alternatives: n/a — partitions are inevitable; only the response design is optional.

### 96. Clock Skew

**Definition:** The difference in wall-clock time between nodes (NTP-synced clocks typically ± 10-100ms on LAN, worse over WAN/VMs; unsynced clocks can be minutes off).

**Problem:** Ordering logic that trusts `time.time()` across machines breaks during skew: TTLs expire early, tokens rejected, events order incorrectly, "last write wins" picks the wrong winner — silently.

**Internal Working:** NTP discipline: clock error measurable via `ntpstat`/`chronyc sources`; monotonic clocks (`time.monotonic()`) never jump backward and are for durations/timeouts; wall clocks for display/TTL only. Lamport clocks / vector clocks / hybrid logical clocks (CockroachDB, Spanner TrueTime with bounded uncertainty) for causal ordering. Leases (`#33`/`#38`) rely on bounded drift; if skew > TTL margin, correctness breaks — hence fencing. Spanner's TrueTime exposes uncertainty interval and waits out `commit-wait` to guarantee external consistency.

**Architecture:** Everywhere: TTLs, tokens, TLS certs, event ordering, lease math, rate windows, log correlation (`trace_id` better than timestamps), `created_at` defaults.

**Implementation:**

```python
import time
monotonic = time.monotonic()     # durations only
wall = time.time_ns() / 1e9      # ordering across machines? NO — use sequence/version
import itertools
seq = itertools.count()          # in-process causal order
```

NTP: `chrony`/`ntpd` with multiple sources; cloud: use Amazon Time Sync/Azure NTP; alert on offset > 50ms; Postgres `now()` = transaction start time; prefer `clock_timestamp()` for wall.

**Production Example:** JWT `exp` checked on servers with 3-minute skew — half of valid tokens rejected by one pod; fixed by `leeway=60` in PyJWT decode and chrony alignment to <20ms fleet-wide; alert added on NTP offset.

**Failure Scenarios:** Events sorted by timestamp arrive out of order (skew > inter-event gap); cache TTL "expires" early on fast-clock nodes → stampede; TLS certificate "not yet valid" errors during VM boot before NTP sync; distributed log merge scrambling audit trails; lease renewer concludes lease valid while holder's timer expired long ago; "check then act" with wall-clock deadline racing across hosts.

**Best Practices:** Monotonic for all durations; wall clock never for ordering; NTP everywhere with offset monitoring (alert > 50ms); bounded leeway in token/cert validation; fenced leases, not bare timestamps; sequence numbers/versions for causal order; time-sync in base images and golden AMIs; test with clock-skew injection.

**Anti-Patterns:** `time.time()` for elapsed measurement; no NTP config on VMs; ordering multi-node events by timestamps; JWT/cert leeway = 0; TTL assumptions < skew bound; assuming `NOW()` is synchronized across replicas.

**Trade-offs:** Performance (commit-wait like TrueTime trades latency for certainty); complexity (logical clocks are subtle — prefer versions); cost (NTP is free); consistency (ordering fundamentally affected); maintainability (standard libraries + chrony beat custom time code).

**Testing:** Inject clock offset (libfaketime/toxiproxy) and assert token/TTL behavior; assert monotonic usage in code review; NTP offset alert test; skew-injection in integration environment; verify ordering with logical sequences under skew.

**Related Concepts:** `#33 Leader Election`, `#38 Distributed Locks`, `#95 Network Partitions`, `#96` pairs with `#35 Eventual Consistency` (LWW), `#81 Database Migrations` (timestamp ordering of migrations), `#69 OAuth`/`#70 JWT Rotation`.

**Decision Criteria:** Use when: any lease, token TTL, or multi-node ordering depends on time — always apply the rules above. Do not use when: pure single-node logic. Alternatives: HLC/vector clocks (Spanner, CockroachDB), versions/sequence numbers, consensus-ordered logs (Raft), logical event IDs.

<!--END-->

Asynchronous communication patterns — queues, topics, event streams, distributed transactions, sagas, and dead-letter handling — for decoupling producers and consumers in production systems.

| # | Concept | One-line use case |
|---|---|---|
| 15 | Message Queues | Decouple work; buffer bursts; at-least-once delivery |
| 16 | Pub/Sub | Fan one event out to many consumers |
| 17 | Event-Driven Architecture | Services react to facts instead of commands |
| 18 | Distributed Transactions | Coordinate writes across service boundaries |
| 19 | Saga Pattern | Long-running multi-service transactions with compensation |
| 20 | Dead Letter Queues | Quarantine messages that cannot be processed |

### 15. Message Queues

**Definition:** A broker that stores messages from producers until consumers acknowledge them, providing at-least-once delivery, buffering, and load leveling.

**Problem:** Synchronous call chains couple availability (any hop down blocks the user), amplify load during bursts, and drop work during deploys. Queues let the system absorb 10x bursts and retry safely.

**Internal Working:** Producer publishes to a queue; broker persists (page cache + fsync in RabbitMQ, partition logs in Kafka); consumer prefetches N messages, processes, acks (or nacks → requeue/DLX). Delivery semantics: at-most-once (ack before work), at-least-once (ack after work — the sane default), exactly-once (transactions, Kafka EOS — real but narrow). Ordering holds per partition/queue only with single consumer or keyed partitions. Durability = durable queue + persistent messages in RabbitMQ; replication factor + min.insync.replicas in Kafka.

**Architecture:** API → broker (RabbitMQ / Redis Streams / SQS / Kafka) → worker fleet → results store. Web/API tier stays thin; workers scale independently.

**Implementation:** RabbitMQ: declare durable queue + DLX; prefetch 10-50; Celery against Redis/RabbitMQ; Kafka: topic with 6-12 partitions keyed by `user_id`, `acks=all`, `enable.idempotence=true`, `isolation.level=read_committed` for EOS pipelines.

```bash
rabbitmqadmin declare queue name=emails durable=true arguments='{"x-dead-letter-exchange":"dlx","x-max-length":100000}'
```

```python
import pika
conn = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq", heartbeat=30))
ch = conn.channel(); ch.queue_declare("emails", durable=True, arguments={"x-dead-letter-exchange": "dlx"})
ch.basic_qos(prefetch_count=20)
ch.basic_consume("emails", on_message, auto_ack=False)  # ack only after side effect commits
```

**FastAPI Example:**

```python
from fastapi import FastAPI
from celery import Celery
celery = Celery("tasks", broker="redis://redis:6379/0")

@app.post("/signup")
def signup(payload: Signup):
    user = create_user(payload)
    celery.send_task("tasks.send_welcome", args=[user.id])   # async, returns 202
    return {"id": user.id}, 202
```

**Production Example:** Image-thumbnail pipeline: 5k uploads/min peak vs 500 steady. API writes job to `images` queue; 30 Celery workers autoscale on queue depth (KEDA); prefetch 2 (CPU-bound); 99.5% of jobs finish < 2s; broker absorbs deploys without dropping work; failed jobs after 5 retries → DLQ + alert.

**Failure Scenarios:** Poison message requeued forever (no max attempts/DLQ) → consumer hot-loops, queue backs up; consumer acks before side effect → message lost on crash; unbounded queue → memory pressure, latency hours later (always cap `x-max-length` or alert on depth); consumer group rebalance storm during deploys; broker disk fills (unacked messages, no TTL) → broker down; visibility timeout shorter than job duration → duplicate concurrent processing.

**Best Practices:** At-least-once + idempotent consumers; ack after commit; prefetch sized to throughput; explicit max queue length / TTL; DLQ wired from day one; alert on depth and consumer lag; persistent messages for anything that matters; graceful shutdown: stop consuming, finish in-flight, then exit; single responsibility per queue.

**Anti-Patterns:** Auto-ack; no DLQ "because it never fails"; one giant queue for everything (no prioritisation); infinite retry on deterministic failures; producers that block indefinitely on a full broker; consumers without graceful shutdown.

**Trade-offs:** Performance (async frees the request path; adds broker hop ~0.5-5ms); complexity (worker fleet + monitoring, real ops); cost (broker infra, always-on workers); consistency (eventual by design); maintainability (schema of messages is a contract — version it).

**Testing:** pytest + testcontainers (RabbitMQ/Redis): enqueue → consume → assert side effect; kill worker mid-task → message redelivered; poison message lands in DLQ after max attempts; load test at 3x expected rate to verify drain time; alert-fire drill on depth.

**Related Concepts:** `#16 Pub/Sub`, `#17 Event-Driven Architecture`, `#20 Dead Letter Queues`, `#44 Backpressure`, `#14 Idempotency`, `#92 Throughput`.

**Decision Criteria:** Use when: work is longer than an HTTP budget, bursty, retryable, or must survive restarts — emails, reports, thumbnails, webhooks, inference. Do not use when: the user needs the result of the work synchronously; volume is trivial (a DB table with `poll FOR UPDATE` is fine); team cannot operate a broker. Alternatives: Postgres `SKIP LOCKED` queue table, Redis Streams, managed SQS, cron batches for very low frequency.

### 16. Pub/Sub

**Definition:** A messaging pattern where producers publish to a topic and every subscribed consumer group receives its own copy — one-to-many fanout, no consumer competing for a single stream of messages.

**Problem:** When many services need to react to the same business fact (order placed → email, inventory, analytics, fraud scoring), point-to-point calls multiply and couple producers to all consumers; adding a consumer means changing the producer.

**Internal Working:** Topic/exchange holds named subscriptions or consumer groups; each group keeps an independent cursor/offset. Kafka: one topic → N consumer groups, each group re-reads the log independently; ordering per key within a partition; retention time/size-based. RabbitMQ: exchange type `fanout` or `topic` (routing keys with `*`/`#`) → queue binding per subscriber — classic pub/sub. Redis `PUBLISH` is fire-and-forget, no persistence (Redis Streams are the durable option). Delivery still at-least-once; each group needs its own DLQ.

**Architecture:** Service emits domain events to a topic → independent consumers (billing, email, search indexer, warehouse) each subscribe with their own group.

**Implementation:**

```yaml
# RabbitMQ topic exchange
exchange: events (topic)
binding: orders.* → queue email-svc (routing key orders.created)
binding: orders.* → queue inventory-svc (same key)
```

```python
# Publisher (kafka-python style)
producer = KafkaProducer(bootstrap_servers=["kafka:9092"])
producer.send("orders", key=b"user:42", value=b'{"type":"order.created","id":"o_9","total":129.0}')
```

**FastAPI Example:** Dependency that injects a cached `KafkaProducer` (singleton) into routes; publish after DB commit, key by user to preserve order per user.

**Production Example:** `order.created` topic with 8 partitions; consumers: search-indexer (lag p99 300ms), recommendation-trainer (batch micro-batch of 500, lag 30s), fraud-scorer (synchronous-ish, lag 50ms). One consumer crashes; its group falls behind — others unaffected; replay via resetting offsets.

**Failure Scenarios:** Consumer group lag explodes silently (no lag alerting); slow consumer blocks partition processing for its group (head-of-line blocking); event schema breaks consumers (no schema registry/versioning); duplicate events after rebalance (at-least-once) — consumers must dedupe; one poison event crash-loops a consumer for the whole group; topic retention too short → late consumer cannot replay.

**Best Practices:** Version events; schema registry (Avro/Protobuf) with compatibility rules; independent DLQs per group; lag alerting per group; small events (carry IDs, fetch details; not megabyte payloads); idempotent consumers; document replay procedure; consider event size limit (Kafka `message.max.bytes` ~1MB).

**Anti-Patterns:** Pub/sub with no consumer ownership ("everyone may read"); giant events; no replay story; mixing command and event semantics in one topic; Redis PUBLISH for work that must not be lost; shared consumer groups meant to be separate.

**Trade-offs:** Performance (excellent fanout, no broker bottleneck per consumer); complexity (schema governance, consumer ownership); cost (log storage/retention × partitions); consistency (eventual, per-group); maintainability (contracts evolve — registry and versioning pay for themselves quickly).

**Testing:** Publish synthetic event; assert each group received and applied it; simulate consumer down → replay after recovery; contract test event schema in CI; load test verifying lag within SLO at 3x; duplicate-delivery test.

**Related Concepts:** `#15 Message Queues`, `#17 Event-Driven Architecture`, `#14 Idempotency`, `#20 Dead Letter Queues`, `#100 gRPC` (sync alternative), `#101 Webhooks`.

**Decision Criteria:** Use when: multiple independent consumers of the same fact, event sourcing-ish audit needs, replayability matters. Do not use when: only one consumer exists (a queue is simpler); you need request/response semantics; sub-millisecond latency required (use sync RPC). Alternatives: `#15 Message Queues` (competing consumers), CDC (Debezium) from the DB, direct service calls with a circuit breaker.

### 17. Event-Driven Architecture

**Definition:** An architectural style in which services communicate by emitting and reacting to immutable facts (events) rather than by issuing remote procedure calls; the event is the integration contract.

**Problem:** Synchronous chains mean the slowest dependency sets every request's latency and the least reliable one sets every caller's availability; features change by editing every participant. Events invert this: producers don't know their consumers.

**Internal Working:** Domain events (`OrderPlaced`) vs notification events (thin "something changed") vs event-carried state transfer (fat events with full payload). Delivery at-least-once; consumers maintain own state projection. Choreography (no central coordinator — emergent flow, risk of implicit control flow) vs orchestration (a saga/orchestrator commands services — explicit flow, easier to reason). Event store or log (Kafka, EventStoreDB) provides replay and temporal audit; exactly-once is only achievable as effectively-once via idempotency + transactions at consumers.

**Architecture:** Services own their data, publish facts, other services project their read models. No "distributed monolith" via synchronous calls pretending to be events.

**Implementation:** Outbox pattern to avoid dual-write: write event to an `outbox` table in the same transaction as the state change; a relay (Debezium CDC or a poller) publishes to the broker; services consume idempotently.

```sql
CREATE TABLE outbox (id uuid PRIMARY KEY, topic text NOT NULL, key text, payload jsonb NOT NULL,
                     created_at timestamptz DEFAULT now(), published boolean DEFAULT false);
```

```python
# inside the same DB transaction as the business write
session.add(Outbox(topic="orders", key=str(user_id), payload={"type": "order.created", "id": order_id}))
session.commit()  # relay publishes afterwards — no dual-write inconsistency
```

**FastAPI Example:** Order endpoint validates + commits + outbox row atomically; returns 202 or 201 with `order_id`; the consumer services update their own projections asynchronously.

**Production Example:** E-commerce: `order.created` → billing creates invoice, inventory reserves, email sends receipt, search/reco project state. p95 checkout 180ms (no downstream calls); warehouse lag 2s; one new consumer (loyalty points) added with zero changes to the order service.

**Failure Scenarios:** Dual-write bug (DB commit succeeds, broker publish fails) → outbox required; event schema drift breaks consumers silently; "event as god-object" carrying PII into analytics topics (data governance); replay causes non-idempotent side effects (emails re-sent); implicit choreography becomes untraceable (who does what on `payment.failed`?); poison events stall a consumer group.

**Best Practices:** Outbox or CDC — never dual-write; thin events + consumer-side fetch, or fat events by design choice; schema registry; explicit event ownership; versioned topics (`orders.v2`); idempotent consumers; DLQs; document the event catalog; choreography for simple fanout, orchestration (saga) for multi-step with compensation; trace events with `trace_id` (OpenTelemetry context propagation).

**Anti-Patterns:** Calling the broker inside the request path for mandatory synchronous outcomes; events with no schema; PII sprayed into all topics; no replay strategy; mixing query events and commands; "event-driven" as a label for async calls with no contract to fall back on.

**Trade-offs:** Performance (great decoupling, great scale); complexity (debugging emergent flows, eventual consistency); cost (broker infra); consistency (per-projection lag; no cross-service transactions); maintainability (explicit contracts (registry) vs implicit coupling — the registry is the price of sanity).

**Testing:** Integration tests with the full pipeline (publish → consumers → projections); contract tests per event type; replay test (reset group, reprocess a day of events into a scratch DB); chaos test dropping the broker; verify outbox relay marks rows published exactly once.

**Related Concepts:** `#16 Pub/Sub`, `#15 Message Queues`, `#19 Saga Pattern`, `#18 Distributed Transactions`, `#50 Cache Invalidation` (events invalidate caches), `#66 Observability` (trace across events).

**Decision Criteria:** Use when: multiple consumers need the same fact, decoupling deploy/scale boundaries, audit/replay needs, temporal decoupling acceptable. Do not use when: strictly sequential request/response with need for immediate confirmation; a monolith that can use in-process calls — events inside one process buy nothing; team immature in operations. Alternatives: direct synchronous calls behind circuit breakers, outbox + webhooks, CDC.

### 18. Distributed Transactions

**Definition:** A transaction spanning multiple services or databases that must commit or roll back as a unit; in practice achieved via 2PC/XA protocols or via saga orchestration, since strict atomic durability across services is rarely available.

**Problem:** A business operation ("reserve inventory + charge card + ship") cannot fail halfway: partial commits leave stock reserved without payment, or payment without stock.

**Internal Working:** Two-phase commit: coordinator asks all participants to prepare (hold locks, vote), then commit/abort on unanimous yes. Guarantees atomicity but blocks on coordinator crash and holds locks across the network — fragile, rarely used across microservices. XA exists in Java/some DBs (not native in Python/FastAPI). Practical alternative: sagas — a sequence of local transactions, each with a compensating action (refund, release reservation). Outbox per service guarantees event emission aligns with local commit. Exactly-once across systems does not exist; effectively-once = local transaction + idempotent consumers.

**Architecture:** Saga orchestrator (Temporal workflow, custom DB state machine, AWS Step Functions) drives service A→B→C with timeouts and compensations; each service keeps its own atomic local commit.

**Implementation:** Avoid 2PC across services. If atomicity truly required within one Postgres: single-phase, same instance, one transaction. Across two databases: XA not available cleanly in Python → prefer saga + outbox, or make one database the system of record and the other a derived projection.

```python
# outbox + idempotency gives effectively-once between your DB and downstream
with session.begin():
    order = create_order(session, ...)           # local commit
    session.add(Outbox(topic="orders", key=order.id, payload={...}))
```

**FastAPI Example:** Checkout endpoint: validate → local transaction (order + outbox) → return 202. Saga worker calls billing → shipping → marks saga complete; on ship failure it publishes `refund.requested`.

**Production Example:** Airline booking: reserve seat (inventory service) → charge card (payments) → issue ticket (fulfilment). Charge succeeds, ticket fails → saga compensates: refund payment, release seat; customer emailed "booking failed, refunded"; all steps logged with saga_id.

**Failure Scenarios:** Coordinator crash mid-2PC → participants locked until recovery (classic deadlock/blocker); compensation itself fails (refund error) → needs retry/DLQ ("compensate the compensation"); outbox relay down → state committed but events missing → projections drift; duplicate compensation (retry) triggers double refund unless keyed; long-running sagas hold semantic locks (reserved seat) blocking other customers — need timeouts and TTLs.

**Best Practices:** Local transactions only inside a service — never hold a lock across a network call; outbox for event emission; idempotent everything; saga timeouts with automatic compensation; explicit saga state table; alert on stuck sagas; human-in-the-loop for failed compensations; prefer idempotent re-drive over manual DB surgery.

**Anti-Patterns:** 2PC across microservices; "best effort" multi-service writes with no compensation plan; distributed transactions across a third-party API with no refund endpoint; sagas with no monitoring (they rot silently); compensations not idempotent.

**Trade-offs:** Performance (sagas add latency vs 2PC's locking but don't block other work); complexity (significantly — state machines, compensation testing); cost (orchestrator infra); consistency (semantic atomicity, not isolation — anomalies visible mid-saga; read models may temporarily diverge); maintainability (explicit state beats implicit distributed cleverness).

**Testing:** pytest per saga step incl. compensation path (force ship failure → assert refund + release); crash-injection between steps; replay test with duplicated events; verify no orphan reservations after N failed sagas; load test for lock contention on reservations.

**Related Concepts:** `#19 Saga Pattern`, `#14 Idempotency`, `#15 Message Queues`, `#17 Event-Driven Architecture`, `#30 Sharding` (same-shard writes can be single-phase), `#109 Production Incidents` (stuck sagas are incidents).

**Decision Criteria:** Use when: multi-service writes that must not silently diverge — money, inventory, bookings. Do not use when: everything fits in one database (one transaction wins); data loss tolerable (queue + replay); operational maturity for sagas missing. Alternatives: modular monolith (single DB transaction), saga orchestration, CDC-based synchronization, accept eventual consistency with reconciliation jobs.

### 19. Saga Pattern

**Definition:** An implementation of a distributed transaction as a sequence of local transactions, each publishing an event/message, with compensating actions defined for each step to undo prior steps on failure.

**Problem:** Cross-service workflows (multi-minute, with human waiting) cannot hold row locks or 2PC barriers; without compensation, partial multi-service writes strand inconsistent state that nobody notices until customers complain.

**Internal Working:** Two styles — **choreography**: each service listens for an event and emits the next; no coordinator; flows emerge; good for short chains. **Orchestration**: a coordinator (Temporal, Step Functions, or a state table in Postgres with a worker) issues commands, waits for replies/timeouts, decides next or compensate; explicit, observable, easy to add a step. Each step: idempotency key, timeout, retry with cap, compensation action. States: started → step_k done → completed | compensating → compensated | failed (needs human). Semantic locks (reservation with TTL) prevent oversell during the saga.

**Architecture:** Orchestrator + participant services; durable saga log (workflow history or DB rows) survives crashes, so a restarted worker resumes the saga rather than losing it.

**Implementation:**

```sql
CREATE TABLE sagas (id uuid PRIMARY KEY, type text, state jsonb NOT NULL, status text NOT NULL DEFAULT 'started',
                    created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now());
```

```python
# Pseudocode — each step: call, then persist progress atomically
def run_booking_saga(booking_id):
    saga = start_saga("booking", booking_id)
    try:
        reserve_seat(idempotency_key=f"{saga.id}:reserve")     # step 1
        advance(saga, "reserved")
        charge_card(idempotency_key=f"{saga.id}:charge")      # step 2
        advance(saga, "charged")
        issue_ticket(idempotency_key=f"{saga.id}:ticket")     # step 3
        complete(saga)
    except StepFailed as e:
        compensate(saga, completed_steps)   # refund, release — in reverse order
        mark_failed(saga, e)
```

With Temporal: `@workflow.defn` with activities + automatic retries + compensation code — the platform persists history, so worker crashes resume the workflow.

**FastAPI Example:** `POST /book` writes saga row (status=started) and enqueues the saga runner; returns `202 + saga_id`; `GET /book/{saga_id}` polls status; UI subscribes via SSE for long-running sagas (#24).

**Production Example:** Marketplace order saga (inventory → payment → shipment → notification), ~6k sagas/day, 0.3% enter compensation; compensations automated (release + auto-refund), 3/month escalated to on-call for refund API failures; average saga completion 800ms, p99 4s (payment gateway tail).

**Failure Scenarios:** Orchestrator stopped (worker down) → sagas stall at a step; must have lag monitoring + dead-man's switch; compensation fails permanently (refund API down > 72h) → human runbook; participant not idempotent → double-charge on retry; timeout too tight → sagas compensate healthy slow steps; choreography chain edits without registry → events nothing consumes; TTL semantic lock expiry mid-saga → oversell; saga table bloat (no archival).

**Best Practices:** Prefer orchestration for >2 steps; idempotency keys derived from saga_id per step; every step has a defined compensation or is declared irreversible; store saga state durably (DB/workflow engine), not memory; alert on sagas stuck > 10min; reconciliation job sweeping stale sagas; human escalation path for failed compensations; include trace IDs in every step's logs/metrics; cap compensation retry count; document saga graph in the repo.

**Anti-Patterns:** Saga with steps that cannot be compensated (email already sent — make it a final irreversible step with explicit acknowledgment); no timeout on a step call (saga waits forever); compensations that are best-effort without alerting; state in process memory; compensating before all participants are known; using a saga when a single DB transaction would do.

**Trade-offs:** Performance (parallel steps possible; sequential default adds service hops); complexity (highest of the messaging patterns — test the compensation matrix); cost (orchestrator + extra DB/workflow infra; Temporal OSS vs self-built table); consistency (semantic atomicity, never isolation; anomalies visible in projections — design UI/read models accordingly, e.g. "pending" states); maintainability (explicit explicit — a documented saga graph is an asset).

**Testing:** pytest for each step and each compensation path; crash between steps (subprocess kill mid-saga) and assert resume; duplicated delivery to compensation → exactly one refund; end-to-end staging booking including forced failures; assert no reserved-seat leak after 1000 failing sagas; chaos test with dependency outage.

**Related Concepts:** `#18 Distributed Transactions`, `#17 Event-Driven Architecture`, `#14 Idempotency`, `#15 Message Queues`, `#20 Dead Letter Queues`, `#24 Server-Sent Events` (status streaming), `#109 Production Incidents`.

**Decision Criteria:** Use when: multi-service write flows spanning seconds to minutes where partial completion is unacceptable (money, inventory, provisioning). Do not use when: single-database transaction suffices (always prefer); flow fits an event fanout with independent consumers and no need for all-or-nothing (choreography/EDA is simpler); team lacks durable-execution tooling or discipline. Alternatives: 2PC (rarely), saga via Temporal/Step Functions, synchronous orchestration with generous timeouts, accept-and-reconcile weekly job.

### 20. Dead Letter Queues

**Definition:** A holding queue (or parking lot) where messages that repeatedly fail processing are diverted after a retry limit, so one poison message cannot stall the pipeline and failures stay visible for inspection and replay.

**Problem:** Without a DLQ, a single malformed message is nacked and requeued forever — hot-looping the consumer, consuming the broker, blocking every message behind it, and being retried until it corrupts throughput for healthy traffic.

**Internal Working:** Broker-enforced: RabbitMQ dead-letter-exchange (`x-dead-letter-exchange` on the queue; rejection/TTL/max-length expiry routes the message with original metadata + `x-death` header). SQS: `RedrivePolicy` (`maxReceiveCount`) → DLQ. Kafka: no native DLQ — implement by reading to an error topic on processing failure, or framework (Spring Kafka, kafka-dlt). Retention limits (`x-message-ttl` on DLQ) must not silently drop evidence. Replay is manual/controlled: inspect → fix consumer or data → re-publish (preserve order if possible).

**Architecture:** Consumer NACK/reject after max attempts → DLX/DLQ → alert + dashboard → operator imports or re-drive tool → producer/topic again.

**Implementation:**

```bash
rabbitmqadmin declare exchange name=dlx type=direct
rabbitmqadmin declare queue name=orders-dlq durable=true arguments='{"x-message-ttl":1209600000}'
rabbitmqadmin declare binding source=dlx destination=orders-dlq routing_key=orders
rabbitmqadmin declare queue name=orders durable=true arguments='{"x-dead-letter-exchange":"dlx","x-dead-letter-routing-key":"orders"}'
```

```python
# consumer: reject without requeue after final attempt → routed to DLX
def on_message(ch, method, props, body):
    try:
        handle(body)
        ch.basic_ack(method.delivery_tag)
    except Retryable:
        ch.basic_nack(method.delivery_tag, requeue=True)   # broker counts deliveries
    except Unrecoverable as e:
        record_failed(body, str(e))
        ch.basic_reject(method.delivery_tag, requeue=False)  # → DLQ
```

**FastAPI Example:** An admin endpoint `POST /admin/dlq/redrive` (internal-only, ops auth) that re-publishes DLQ messages after a fix, disabled by default and audit-logged.

**Production Example:** Order-fulfilment consumer crashing on a schema change (`weight_kg` renamed). 4,000 messages hit max-receive-5 overnight, all in `orders-dlq`; alert fired at 02:10; team fixed the parser (accepts both keys), redrove DLQ at 09:00 — zero lost orders, one uncomfortable morning.

**Failure Scenarios:** DLQ with no alerting (messages rot for months); DLQ TTL too short — auto-purge before triage; DLQ unbounded growth fills disk; replay without fixing root cause (poison returns); DLQ missing `x-death` metadata → debugging blind; auto-requeue-on-deploy of "poison" messages that fail for code reasons; redrive out of order breaking dependency sequences.

**Best Practices:** Every consumer DLQ wired at queue creation; alert on any DLQ message (or depth > 0); retain at least 14 days; store full error + original payload + attempt count; redrive tooling with dry-run; DLQ dashboards per queue; poison-message quarantine should include expiry hygiene; document the redrive runbook; treat DLQ arrival as a defect, not routine.

**Anti-Patterns:** NACK requeue forever; swallowing exceptions (ack always); no DLQ alerts ("we'll check manually"); DLQ as a garbage bin nobody owns; redriving everything blindly; using DLQ to hide schema mismatch instead of versioning events.

**Trade-offs:** Performance (protects throughput entirely); complexity (low — broker feature); cost (negligible storage); consistency (DLQ messages are NOT processed — state can diverge; redrive restores); maintainability (runbook + tooling pays off in every incident).

**Testing:** Unit test the unrecoverable path → assert DLQ routing (testcontainers); integration test redrive; verify `x-death` attempts increment; alert fire-drill; replay-safety test on staging.

**Related Concepts:** `#15 Message Queues`, `#16 Pub/Sub`, `#12 Retries`, `#13 Exponential Backoff`, `#14 Idempotency`, `#62 Alerts`.

**Decision Criteria:** Use when: always, with any retry-capable queue — it is not optional plumbing. Do not use when: message loss is acceptable and volume is trivial (in-memory job list) — but you still need failure visibility somehow. Alternatives: broker-less retry with inline DLQ table + sweeper job, SQS redrive policy, Kafka error topics.

<!--END-->
