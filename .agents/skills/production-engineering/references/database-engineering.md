# Database Engineering Reference (PostgreSQL & SQLAlchemy)

Indexing, query tuning, pooling, replication, sharding, locking, and schema lifecycle for PostgreSQL and SQLAlchemy-based backends.

| # | Concept | One-line use case |
|---|---|---|
| 25 | Database Indexing | Make lookups cheap with B-tree/index structures |
| 26 | Query Optimization | Read and fix slow plans |
| 27 | N+1 Queries | Kill per-row query fan-out |
| 28 | Connection Pooling | Reuse connections, never exhaust them |
| 29 | Read Replicas | Scale reads off the primary |
| 30 | Sharding | Partition data across databases |
| 31 | Partitioning | Split big tables by key/range inside one DB |
| 32 | Replication | Copies for durability and reads |
| 36 | Optimistic Locking | Detect write conflicts by version, not locks |
| 37 | Pessimistic Locking | Take the row lock first |
| 39 | Race Conditions | Prevent read-modify-write corruption |
| 40 | Deadlocks | Detect and avoid lock cycles |
| 81 | Database Migrations | Versioned, ordered schema changes |
| 82 | Schema Versioning | Keep schema and code in lockstep |

### 25. Database Indexing

**Definition:** An ordered auxiliary structure (usually a B-tree) that lets the database locate rows without scanning the whole table, at the cost of extra storage and slower writes.

**Problem:** Sequential scans collapse at ~1M+ rows: p95 goes seconds, connections exhaust, and the entire service stalls. Missing index is the single most common production database bug.

**Internal Working:** PostgreSQL B-tree stores keys sorted with pointers to tuples; lookups are O(log n). The planner uses statistics (`pg_stats`, `ANALYZE`) to estimate selectivity. Composite indexes are used left-to-right (leftmost prefix rule); partial indexes index only a subset (`WHERE active`); covering indexes (`INCLUDE`) serve index-only scans; expression indexes (`lower(email)`) match the query predicate exactly. `EXPLAIN (ANALYZE, BUFFERS)` shows the real plan.

**Architecture:** Between the ORM/query layer and the storage engine; invisible to the application code except through latency. Migrations must create indexes `CONCURRENTLY` in production.

**Implementation:**

```sql
CREATE INDEX CONCURRENTLY ix_orders_user ON orders (user_id);
CREATE INDEX CONCURRENTLY ix_orders_status_created ON orders (status, created_at DESC);
CREATE INDEX CONCURRENTLY ix_users_email_lower ON users (lower(email));
CREATE INDEX CONCURRENTLY ix_active ON orders (user_id) WHERE status = 'active';
CREATE INDEX CONCURRENTLY ix_covering ON orders (user_id) INCLUDE (total, created_at);
```

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 20;
```

**Python Example:**

```python
class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    __table_args__ = (Index("ix_orders_status_created", "status", text("created_at DESC")),)
```

**FastAPI Example:** Add `index=True` on columns used in `WHERE`/`JOIN`/`ORDER BY`; paginate deep pages with keyset (`WHERE id > :last ORDER BY id LIMIT 50`) not `OFFSET`.

**Production Example:** `orders` 120M rows, p95 1.8s → after composite index (user_id, created_at DESC): p95 4ms. Index build on live traffic used `CONCURRENTLY` — zero downtime.

**Failure Scenarios:** Index never chosen (statistics stale → `ANALYZE`; or `OR` instead of `IN`); write amplification (every INSERT/UPDATE maintains all indexes — a table with 8 indexes updates 8x); unused indexes bloating storage; index on low-selectivity boolean; partial index condition not matching the query.

**Best Practices:** Index predicates and join keys; composite in selectivity order (most selective first, or equality-then-range); `INCLUDE` to cover; `CONCURRENTLY` always in production; drop unused indexes (quarterly `pg_stat_user_indexes` review); monitor bloat; verify with `EXPLAIN` before and after.

**Anti-Patterns:** Index every column; index low-cardinality columns; forgetting leftmost prefix; `SELECT *` defeating covering index; creating without CONCURRENTLY; no maintenance plan (bloat).

**Trade-offs:** Performance (read speed vs write cost); storage (5-20% of table per index); complexity (tuning needs expertise); cost (I/O); consistency (none — indexes are always consistent); maintainability (migration + bloat ops).

**Testing:** `EXPLAIN (ANALYZE, BUFFERS)` on query in CI against a seeded subset; pg_stat_statements before/after; integration test asserting plan does not seq-scan the hot table; load test p95 improvement.

**Related Concepts:** `#26 Query Optimization`, `#28 Connection Pooling`, `#29 Read Replicas`, `#31 Partitioning`, `#26` tuning and `#81 Database Migrations` (CONCURRENT builds).

**Decision Criteria:** Use when: measured slow queries with full scans on hot paths; join-heavy needs. Do not use when: write-heavy tables where index maintenance dominates; tiny tables (<10k rows); columns rarely filtered. Alternatives: materialized views, denormalization, read replicas, `#31 Partitioning`.

### 26. Query Optimization

**Definition:** The discipline of shaping queries, schemas, and plans to minimize database work per request — read plans, remove waste, and verify with measurements.

**Problem:** Slow queries don't just feel bad; they hold locks, exhaust pools, and multiply under load — one bad query can be a whole-incident root cause.

**Internal Working:** Planner costs plans (I/O + CPU) using statistics; chosen plan depends on row estimates (`rows=`, `cost=`). Analyzing `EXPLAIN`: seq scan vs index scan, nested loop vs hash join, sort spilling to disk, estimate vs actual mismatch → stale stats or correlated predicates. Fixes: better indexes, query rewrite, `ANALYZE`, join order, join_collapse_limit, work_mem tuning for sorts, `pg_stat_statements` to find top offenders.

**Architecture:** Database engine + your query layer; optimization feedback loop: observe (pg_stat_statements/APM) → hypothesize → rewrite → verify.

**Implementation:**

```sql
SELECT query, mean_exec_time, calls FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20;
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;   -- look at actual time vs cost, buffers hit/read
SET work_mem = '64MB';  -- for a sort/hash spill in that session
ANALYZE table_name;
```

SQLAlchemy: `.options(selectinload(...))`, explicit joins; never `SELECT *`.

**Python Example:**

```python
orders = session.scalars(
    select(Order).where(Order.status == "paid").order_by(Order.created_at.desc()).limit(50)
).all()
```

**FastAPI Example:** Debug toolbar / `SQLALCHEMY_ECHO=1` locally; production uses pg_stat_statements + slow-query log (`log_min_duration_statement=200`); endpoint timeouts set per route.

**Production Example:** Report query at 8s (nested loop over 3M rows); estimate off 100x due to stale stats → `ANALYZE` + composite index + replacing `NOT IN (subquery with NULLs)` with `NOT EXISTS` → 80ms.

**Failure Scenarios:** Optimizing by average hides p95 (one plan flip once in a while); index added but unused (planner still seq-scans due to stats); cache hiding query regressions until cache expires; `work_mem` raised globally → OOM under concurrency; the "fix" works at 10k rows, breaks at 10M.

**Best Practices:** Measure first (`pg_stat_statements`); hypothesis → change → measure; keep statistics fresh (autovacuum); index for the query, not in general; set slow-query logging; pagination by keyset; avoid correlated subqueries; test at production-scale data.

**Anti-Patterns:** Premature micro-tuning without stats; "index everything"; fixing one literal query while the same N+1 exists elsewhere; OFFSET pagination over 100k pages; assuming the ORM generates good SQL.

**Trade-offs:** Performance (transformative); complexity (tuning skill required); cost (free, mostly); consistency (none); maintainability (documented plans + indexes in migrations).

**Testing:** EXPLAIN diff before/after in PR description; CI seed at 1M rows; regression test asserting no seq scan on `orders` for the endpoint query; load test.

**Related Concepts:** `#25 Database Indexing`, `#27 N+1 Queries`, `#28 Connection Pooling`, `#29 Read Replicas`, `#93 P99 Latency`.

**Decision Criteria:** Use when: slow queries identified by measurement. Do not use when: you don't have pg_stat_statements or EXPLAIN — set them up first. Alternatives: caching the expensive result, materialized views, denormalization, OLAP offload.

### 27. N+1 Queries

**Definition:** Issuing one query for a parent list and then one additional query per row for the children — N+1 round trips instead of one.

**Problem:** Endpoints that feel fine locally at 20 rows issue 1001 queries for 1000 rows in production; latency scales linearly with page size and saturates the connection pool.

**Internal Working:** ORM lazy loading emits a query per attribute access. Fix strategies: eager loading (JOIN or batched `IN (...)` "selectin" style), joined load, or explicit two queries. Batching selects by key is usually optimum (no duplicate rows). In SQLAlchemy 2.0: `selectinload` for collections, `joinedload` for many-to-one.

**Architecture:** Between route handler and database; invisible until measured with query logging or counting.

**Implementation:**

```python
from sqlalchemy.orm import selectinload
orders = session.scalars(
    select(Order).options(selectinload(Order.items)).limit(100)
).all()          # 2 queries total, regardless of len(orders)
```

Or raw: `SELECT * FROM items WHERE order_id IN (:ids)` after fetching orders.

**FastAPI Example:** Serialization helper taking `selectinload(Order.items)` option; test with `assert db.query_count == 2` using pytest + event listener on `before_cursor_execute` or `SQLALCHEMY_ECHO`.

**Production Example:** `/api/orders` listing 200 orders → 201 queries → 900ms; with selectinload: 2 queries, 12ms. Found by `log_min_duration_statement=0` showing 200 identical `SELECT * FROM items WHERE order_id=?`.

**Failure Scenarios:** Lazy-load in async context (MissingGreenlet) causing exceptions; N+1 reappearing via a new nested serialization field; join-eager-load Cartesian explosion (parent rows duplicated ×children) — prefer selectin; pagination applied after join (limit applies to duplicated rows); default relationships silently lazy in new code.

**Best Practices:** Default to selectinload for collections, joinedload for many-to-one; count queries in tests; log query counts per request in dev; cap page sizes; code review rule: no attribute access in loops without eager loading; use `contains_eager` for custom filters.

**Anti-Patterns:** Lazy loading "because it's convenient"; `len()` on a lazy collection triggering full load; 5 nested loops of lazy relations; hiding N+1 with a cache.

**Trade-offs:** Performance (often 10-100x endpoint speedup); complexity (mention options in query code); memory (eager load materializes children — selectin keys); consistency (none); maintainability (explicit options beat implicit lazies).

**Testing:** pytest with `before_cursor_execute` listener counting statements per request — assert ≤ expected; CI at realistic page size; profile endpoint in staging with echo=True.

**Related Concepts:** `#26 Query Optimization`, `#25 Database Indexing`, `#28 Connection Pooling`, `#27 N+1 Queries` pairs with `#66 Observability` query tracing.

**Decision Criteria:** Use eager loading when: serializing nested relations. Do not use when: children are never touched (don't load); payload too large (paginate children separately or use streaming). Alternatives: explicit two-step queries, GraphQL dataloaders, views.

### 28. Connection Pooling

**Definition:** Maintaining a reusable set of database connections so request handlers borrow and return them instead of opening a TCP+TLS+auth handshake per query.

**Problem:** Postgres forks a backend process per connection (~5-10MB RAM each); without pooling, a 500-thread app tries to open 500 backends, Postgres falls to its knees, and everything queues behind connection setup (10-100ms per query).

**Internal Working:** Client pool (SQLAlchemy: `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`; TCP keepalive; pre-ping `pool_pre_ping=True` for stale detection) reuses connections and validates them before checkout. Server side: PgBouncer in transaction pooling mode multiplexes thousands of clients to few server connections (limits supported statements in transaction mode; session-level state breaks). Sizing math: pool_size ≈ (CPU cores × 2) + disk spindles, split per replica; total across replicas must stay under `max_connections` (default 100 — raise carefully).

**Architecture:** App instances (each with pool) → PgBouncer (optional shared pool) → Postgres. K8s: pool per pod, so `replicas × pod_pool` is what you budget.

**Implementation:**

```python
engine = create_engine(
    url, pool_size=10, max_overflow=20, pool_timeout=30,
    pool_recycle=1800, pool_pre_ping=True, pool_use_lifo=True,
)
# async:
engine = create_async_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True)
```

PgBouncer: `pool_mode=transaction`, `max_client_conn=1000`, `default_pool_size=25`.

**FastAPI Example:** One engine singleton per process; `Depends(get_db)` yields a session; session closed in `finally`; never create engines per request; startup event does a warm `SELECT 1` per worker.

**Production Example:** 30 pods × pool_size 10 = 300 > max_connections 200 → Postgres refusing connections. Fix: PgBouncer transaction mode, default_pool_size=20; pod pool 5; connection storms eliminated; p95 900ms→120ms.

**Failure Scenarios:** Pool exhaustion (leaked sessions not returned → `pool_timeout` errors after 30s); stale connections after DB restart (pre_ping fixes); transaction-mode PgBouncer breaks prepared statements/named portals/`SET` (use session mode or `max_prepared_statements=0`); all pods × overflow = server OOM; pool_size set to 100 per pod ×20 pods.

**Best Practices:** pre_ping; pool_recycle < server `tcp_keepalives` and LB idle timeout; LIFO reuse (pool_use_lifo) frees idle connections; measure wait time (`pool_wait_seconds`); keep transactions short (no network calls inside); budget total connections; PgBouncer for many replicas; separate pool for migrations.

**Anti-Patterns:** Opening connections in request handlers; pool_size=max_connections per pod; long transactions holding borrowed connections; no monitoring of pool checkout failures; pool with zero pre_ping behind a NAT/LB that drops idle TCP.

**Trade-offs:** Performance (avoids 10-100ms per request; huge under load); memory (each conn ~5-10MB server-side); complexity (PgBouncer adds an ops hop); consistency (transaction mode changes semantics — be precise); maintainability (single engine factory).

**Testing:** Load test beyond pool size and assert timeouts not server crashes; kill DB → verify pre_ping reconnect; measure `pool.checkout()` wait with a metric; failover drill to replica.

**Related Concepts:** `#25 Database Indexing`, `#40 Deadlocks`, `#32 Replication`, `#28 Connection Pooling` interacts with `#45 Autoscaling` (replica churn), `#40 Deadlocks`.

**Decision Criteria:** Use when: always — every production service. Do not use when: CLI one-shot script. Alternatives: PgBouncer, RDS Proxy, lazy connection per batch job.

### 29. Read Replicas

**Definition:** One or more asynchronous (or semi-sync) standby copies of the primary database that serve read-only traffic, offloading the primary.

**Problem:** Reads outgrow the primary long before writes do; without replicas, scaling headroom is one machine, and any spike (reports, dashboards) browns out transactional traffic.

**Internal Working:** Primary streams WAL (physical replication, LSN positions) to standbys; recovery replays logs continuously. Standbys are hot and read-only (`hot_standby=on`). Replication lag = LSN distance, typically < 1s, grows under write bursts or slow replica I/O. Read-your-writes is not guaranteed — route "read after write" to the primary or use LSN-wait (`pg_current_wal_lsn` vs replay LSN, or `statement_timeout` trick). Managed services (RDS/Cloud SQL) automate provisioning and promotion.

**Architecture:** Writers → primary; readers → replica(s); analytics → separate replica; router (PgBouncer read mode / app routing / RDS reader endpoint) sends SELECTs to replicas, writes to primary.

**Implementation:**

```ini
# postgresql.conf on replica
primary_conninfo = 'host=primary port=5432 user=replicator password=...'
hot_standby = on
```

```python
PRIMARY = create_engine(url_primary, ...)
REPLICA = create_engine(url_replica, ...)
def read(...): REPLICA.connect()   # or per-request routing via dependency
```

**FastAPI Example:** Dependency `get_read_db()` vs `get_write_db()`; after any write in this request, set a flag on the request state to force primary reads for consistency.

**Production Example:** Product catalog read-heavy: 25k read QPS; 2 replicas absorb reads; primary handles writes + session reads; p95 read 90ms→12ms; replica lag alert at >2s; nightly report job pinned to a dedicated replica.

**Failure Scenarios:** Lag spike → stale reads (user sees pre-write data); failover splits brain if old primary doesn't fence (use managed failover + fencing); replica overloaded by batch queries → lag grows unbounded; connection routing sends writes to replica → errors/500s; promotion on unplanned outage without synchronous backup → data loss window (RPO > 0).

**Best Practices:** Route user-facing "read-your-write" reads to primary; alert on lag (`pg_stat_replication`); promote via managed tooling; size replicas ≤ primary; analytics on separate replica; statement_timeout on replica sessions; test failover quarterly.

**Anti-Patterns:** Reading from replica immediately after write without consistency strategy; replicas sized smaller than primary under read+write-burst load; no lag monitoring; manual promotion; long analytics on the OLTP replica.

**Trade-offs:** Performance (read scale-out); cost (full copy per replica); complexity (routing + lag handling); consistency (eventual for replicas reads); maintainability (managed services reduce this).

**Testing:** Simulate lag (pause replay via `pg_wal_replay_pause()`) and verify app behavior; failover drill; verify write-to-read path after write returns primary result; load test reads on replica.

**Related Concepts:** `#32 Replication`, `#85 Failover`, `#30 Sharding`, `#34 CAP Theorem`, `#35 Eventual Consistency`, `#45 Autoscaling`.

**Decision Criteria:** Use when: read:write ratio > 3:1 and reads dominate; analytics need isolation. Do not use when: write-heavy workload (replicas won't help; consider `#30 Sharding`); strong consistency required everywhere; tiny database. Alternatives: caching (`#2 Caching`), materialized views, `#31 Partitioning`, vertical scale-up (`#47 Vertical Scaling`).

### 30. Sharding

**Definition:** Horizontal partitioning of a dataset across multiple independent database instances (shards), each owning a subset by key range or hash.

**Problem:** Beyond one machine's write capacity/storage, vertical scaling tops out; sharding is the only way to scale writes and storage indefinitely — at substantial complexity cost.

**Internal Working:** Shard key selection dominates outcomes (customer_id, tenant_id). Hash ring or modulo maps key → shard. Cross-shard queries scatter-gather; global unique IDs need snowflakes or UUIDs. Resharding = reshashing with minimal movement (consistent hashing) or online resharding tooling (gh-ost/Vitess). Vitess/Citus automate this; hand-rolled is rarely advisable.

**Architecture:** Router (or Citus coordinator) → shard shards (e.g., shard_0..63 PostgreSQL nodes) → per-shard replicas. App layer pins tenant to shard; caches sharded by same key.

**Implementation:** Citus: `SELECT create_distributed_table('orders', 'user_id');` — query planner scatters. Vitess keyspaces with VReplication for resharding. Application: `shard = hash(user_id) % N` then connect to that shard; keep a directory table for migrations.

**Python Example:** Modulo routing helper + connection per shard dict; transactions only within one shard.

**Production Example:** Tenant-per-shard SaaS, 40 shards × replica pairs, 2TB data, 80k write QPS; per-shard blast radius small; hot tenant identified by shard metrics → moved to dedicated shard.

**Failure Scenarios:** Hot shard (one whale tenant) → uneven load; cross-shard joins become application code; resharding with downtime; scatter-gather latency = slowest shard (tail); backups and migrations ×N complexity; replica lag per shard.

**Best Practices:** Pick the shard key from access patterns; keep all hot-path transactions within one shard; co-locate related tables on same key; plan resharding from day 1; managed (Citus/Vitess/Cloud SQL) strongly preferred over hand-rolled; monitoring per shard; tenant injection testing.

**Anti-Patterns:** Sharding before measuring (cache/replica first); random/auto-increment shard keys (destroys locality); cross-shard transactions; ignoring backup complexity; no hot-key handling.

**Trade-offs:** Performance (massive write/storage scale; scatter-gather latency); complexity (very high); cost (many nodes); consistency (within shard strong, across shards eventual); maintainability (hardest DB topology — needs platform team).

**Testing:** Deterministic shard routing tests; hot-shard simulation; failover drill per shard; data-consistency audit across shards; full resharding rehearsal on copies.

**Related Concepts:** `#31 Partitioning`, `#32 Replication`, `#29 Read Replicas`, `#28 Connection Pooling`, `#95 Network Partitions`, `#46 Horizontal Scaling`.

**Decision Criteria:** Use when: dataset > 1 machine's write capacity or storage, tenant isolation required, growth projected. Do not use when: read-heavy (replicas + cache suffice); < 500GB (single Postgres handles plenty); no ops maturity. Alternatives: read replicas, caching, `#31 Partitioning` (cheaper, same DB), vertical scaling, managed distributed DB (CockroachDB, Spanner).

### 31. Partitioning

**Definition:** Splitting one large table into physical partitions (by range, list, or hash of a key) inside a single database for faster scans, cheaper purges, and better maintenance.

**Problem:** A 300M-row `events` table makes every vacuum, index build, and backup brutal; dropping 30 days of data with `DELETE` creates bloat and locks.

**Internal Working:** PostgreSQL declarative partitioning: parent table + per-partition child tables; planner prunes partitions by constraint (`WHERE created_at >= now() - interval '7 days'` touches only recent partitions); partition pruning at plan time (static) or runtime (dynamic, for prepared statements/`EXECUTE`). Partition-wise joins and aggregates parallelize. `DETACH PARTITION` is instant vs DELETE + VACUUM.

**Architecture:** Inside the same Postgres; partitions stored as separate relations; global (cross-partition) unique constraints impossible — uniqueness must include partition key.

**Implementation:**

```sql
CREATE TABLE events (id bigint, created_at timestamptz NOT NULL, user_id bigint, payload jsonb)
PARTITION BY RANGE (created_at);
CREATE TABLE events_2026_11 PARTITION OF events
  FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
-- monthly pg_partman or manual:
ALTER TABLE events DETACH PARTITION events_2026_08 CONCURRENTLY;  -- instant drop
```

**Python Example:** SQLAlchemy model with `postgresql_partition_by="RANGE (created_at)"`; create partition tables via scheduled migration/pg_partman.

**Production Example:** 400M-row `audit_log` partitioned monthly; delete of > 180 days = instant DETACH; quarterly partition creation automated (pg_partman); backups of hot partitions separate; p95 queries only recent partitions stay < 20ms.

**Failure Scenarios:** Queries without partition-key predicate scan ALL partitions (slower than before); unique constraint missing partition key → rejected; forgetting to create next month's partition → INSERT into parent fails ("no partition found"); partition count explosion (>1000 children degrades planner); wrong granularity (too small → partition overhead).

**Best Practices:** Partition by the dominant filter (time); monthly range + retention by detach; pg_partman to automate create/drop; keep partition count < 100; include partition key in unique indexes; test pruning with EXPLAIN (look for "Partitions chosen").

**Anti-Patterns:** Partitioning small tables; hash partition across one DB for "sharding feel"; range by a non-filtered column; default partition catching everything (hides bugs); forgetting index per partition (each child needs its own).

**Trade-offs:** Performance (pruning + maintenance wins; cross-partition queries worse); complexity (moderate); cost (same DB — cheap); consistency (full ACID preserved); maintainability (automated partition lifecycle required).

**Testing:** EXPLAIN verifying pruning; detach/attach test; next-partition-missing drill; query timing at full scale; vacuum/bloat check monthly.

**Related Concepts:** `#25 Database Indexing`, `#26 Query Optimization`, `#29 Read Replicas` (partition + replica combo), `#81 Database Migrations`.

**Decision Criteria:** Use when: very large tables with time-range filters or retention drop requirements. Do not use when: table < 10M rows; dominant access pattern is by non-key (global scan unavoidable); cross-partition uniqueness required. Alternatives: `#30 Sharding`, archival to object storage + external tables, materialized rollups.

### 32. Replication

**Definition:** Copying data from a source database to one or more targets continuously, so multiple nodes hold the same data for durability, availability, and read scale.

**Problem:** A single database is a durability and availability liability (disk failure, accident, corruption); without replication, recovery = restore from backup, meaning minutes-to-hours of data loss and downtime.

**Internal Working:** Streaming replication ships WAL records; logical replication decodes logical change sets. Sync vs async: sync (semi-sync `synchronous_commit=remote_apply`) waits for standby ack — durability over latency; async has possible data loss (RPO>0) on failover but better availability. Failover promotion selects a standby; `repmgr`/Patroni/managed services orchestrate leader election and fencing. Replication slots pin WAL if standby is down (disk fill risk).

**Architecture:** Primary ↔ replicas (same AZ + cross-AZ); watchers (Patroni via etcd) elect and fence; apps route via proxy.

**Implementation:** Postgres: WAL archive + standby; `synchronous_standby_names = 'ANY 1 (s1, s2)'`; Patroni ensures one leader (fencing via etcd/DCS lease). Managed: RDS Multi-AZ + read replicas; monitor `pg_stat_replication.replay_lag`.

**Production Example:** Orders DB: 1 primary + 1 sync replica same AZ + 2 async cross-region replicas; nightly restore test; RPO = 0 (sync), RTO = 5min via automated failover.

**Failure Scenarios:** Async replica promoted → lost committed transactions; replication slot abandoned → WAL disk fill; split-brain after network partition (two primaries) without fencing → corruption; sync replica slow → write latency = replica latency; backup restore untested → backup is useless.

**Best Practices:** Patroni/managed failover with fencing; sync for zero-RPO; cross-region for DR; alert on lag; test restores; monitor slots; never rely on one region only.

**Anti-Patterns:** Async replica without knowing your RPO; manual promotion; replication as backup replacement; no failover testing; ignoring replication slot bloat.

**Trade-offs:** Performance (sync adds replica RTT to writes); complexity (moderate-high with self-managed); cost (multiple full copies); consistency (sync=strong, async=eventual); maintainability (managed >> DIY).

**Testing:** Failover drill monthly (promote replica, verify app reconnect); restore drill; lag measurement at load; verify no dual-primary after partition (chaos test).

**Related Concepts:** `#29 Read Replicas`, `#85 Failover`, `#33 Leader Election`, `#83 Disaster Recovery`, `#84 Backups`, `#95 Network Partitions`, `#86 Multi-Region Deployment`.

**Decision Criteria:** Use when: always, for any production DB. Do not use when: ephemeral dev data. Alternatives: backups only (insufficient), distributed SQL (CockroachDB/Spanner — built-in replication), cloud multi-AZ.

### 36. Optimistic Locking

**Definition:** A concurrency control that assumes conflicts are rare: instead of taking a lock first, it reads a version (or timestamp) with the row and rejects the update if the version changed since the read.

**Problem:** Read-modify-write across a request (fetch → user edits → save) can silently overwrite another user's concurrent edit (last-writer-wins), losing data.

**Internal Working:** Add a `version` integer column. Update: `UPDATE orders SET ..., version = version + 1 WHERE id = :id AND version = :seen_version`. Affected rows = 0 → conflict → reload and retry or surface 409. No DB locks held between read and write — great for web request flows. SQLAlchemy: `version_id_col` on the Mapped column; conflict raises `StaleDataError`.

**Architecture:** Between the service layer and Postgres; the check is part of the UPDATE's WHERE clause.

**Implementation:**

```python
from sqlalchemy.orm import Mapped, mapped_column
class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    total: Mapped[int] = mapped_column(Numeric(10, 2))
    version_id: Mapped[int] = mapped_column(version_id_col=True)  # SQLAlchemy auto-increments + checks
```

orraw SQL as above with explicit retry loop (max 3).

**FastAPI Example:** On `StaleDataError`/0-rows → `HTTP 409 Conflict` with `current_version` + current data so UI can merge; clients retry the mutation.

**Production Example:** Collaborative inventory edit: warehouse A and B open the same item; A saves (v3→v4); B's save (based on v3) rejected → 409, UI refreshes, B re-applies → no lost update. Zero locks held during the 4-minute edit session.

**Failure Scenarios:** Hot contention → high 409 rate (that's the signal to switch to pessimistic locking or a queue); retry loop infinite without cap; version not incremented (manual SQL forgotten) → check is no-op; conflict resolution pushed to users with no merge help → support burden.

**Best Practices:** Use for low-contention, long-edit flows; cap client retry attempts; return the latest version on 409; expose `version` in API payloads; keep transactions short around the UPDATE; metric the conflict rate.

**Anti-Patterns:** Optimistic locking on hot rows (flash-sale counters); version check in app code instead of WHERE (TOCTOU race); swallowing 409s; identical "retry forever" loops.

**Trade-offs:** Performance (zero read-time locks; retry cost on conflict); complexity (low); cost (free); consistency (detects, doesn't prevent); maintainability (simple, but conflicts need UX design).

**Testing:** pytest: two concurrent sessions read v1; first writes (→v2); second write must raise/return 0 rows; API-level 409 test; conflict-rate metric assertion.

**Related Concepts:** `#37 Pessimistic Locking`, `#39 Race Conditions`, `#35 Eventual Consistency`, `#14 Idempotency`, `#40 Deadlocks`.

**Decision Criteria:** Use when: low-contention writes, long user edits, API-driven updates. Do not use when: counters/balances under high contention (lock or atomic SQL); operations with external side effects where retry duplicates work. Alternatives: `#37 Pessimistic Locking`, atomic `SET x = x + 1` expressions, `#38 Distributed Locks`.

### 37. Pessimistic Locking

**Definition:** A concurrency control that takes a row-level lock before reading/writing so no other transaction can modify (or depending on level, read) the row until commit.

**Problem:** When conflicts are *likely* (inventory decrement on hot SKU), optimistic retry loops thrash; you need mutual exclusion to keep correctness simple.

**Internal Working:** `SELECT ... FOR UPDATE` takes an exclusive row lock; `FOR UPDATE SKIP LOCKED` skips locked rows (classic queue pattern); `NOWAIT` errors instead of waiting. Locks held until transaction commit/rollback. Postgres also has predicate locks for serializable isolation. Deadlocks possible — keep lock order and transaction length small.

**Architecture:** Within one DB transaction, wrapping the critical section; the transaction is the lock boundary.

**Implementation:**

```sql
BEGIN;
SELECT id, stock FROM items WHERE id = 42 FOR UPDATE;   -- blocks concurrent decrementors
UPDATE items SET stock = stock - 1 WHERE id = 42 AND stock >= 1;
COMMIT;
```

Queue pattern: `SELECT * FROM jobs WHERE state='pending' ORDER BY id LIMIT 10 FOR UPDATE SKIP LOCKED;`

```python
job = session.scalar(select(Job).where(Job.state == "pending")
                     .order_by(Job.id).with_for_update(skip_locked=True).limit(1))
```

**FastAPI Example:** Checkout: `with session.begin(): item = locked_select(...); if item.stock < qty: raise 409` — entire read+write in one request transaction.

**Production Example:** Flash sale: 5000 concurrent checkouts on SKU with 100 units; FOR UPDATE serializes decrements; last 4900 get 409/sold-out cleanly — zero negative stock, zero oversell. p95 checkout 240ms.

**Failure Scenarios:** Lock held over network/LLM call inside transaction → pool exhaustion and 30s queueing; lock order inversion across tables → deadlock; long transaction blocks all writers on hot rows; forgetting WHERE clause locks whole table via predicate range; NOWAIT errors treated as 500s instead of 409.

**Best Practices:** Lock the narrowest row set; keep transactions < 100ms; consistent lock ordering (by ID); handle deadlock victim (retry the transaction); SKIP LOCKED for job queues; never call external services inside a lock transaction; monitor lock wait time (`pg_stat_activity.wait_event`).

**Anti-Patterns:** SELECT FOR UPDATE without WHERE; locks around user think-time; entire endpoint in one giant transaction; ignoring deadlock victims; locking whole table (LOCK TABLE) to fix a bug.

**Trade-offs:** Performance (serializes hot rows — throughput capped); complexity (simple mental model); cost (free); consistency (strong within transaction); maintainability (easy to reason, easy to deadlock).

**Testing:** pytest: spawn two transactions, assert second blocks until first commits; deadlock-injection test with reversed lock order; assert `SKIP LOCKED` consumer never double-processes; load test hot-row decrement for invariants (stock never < 0).

**Related Concepts:** `#36 Optimistic Locking`, `#40 Deadlocks`, `#39 Race Conditions`, `#28 Connection Pooling`, `#38 Distributed Locks` (lock across services).

**Decision Criteria:** Use when: high-contention rows with critical invariants (stock, balances); queue consumers. Do not use when: long user edit flows (optimistic wins); cross-service consistency (use `#38 Distributed Locks` or saga). Alternatives: atomic single-statement updates, `#36 Optimistic Locking`, application-level semaphore via Redis.

### 39. Race Conditions

**Definition:** A bug class in which the correctness of an operation depends on the interleaving of concurrent execution — outcome varies nondeterministically with scheduling.

**Problem:** Classic lost-update: two requests read balance 100, both add 50, both write 150 — one 50 vanishes. In production: money, inventory, counters, and file replacements silently corrupt.

**Internal Working:** Interleavings: read-modify-write without atomicity; check-then-act across async boundaries; time-of-check vs time-of-use (TOCTOU). Fixes: atomic operations (single SQL statement with math `SET x = x + 1`), transactions with locking, optimistic version checks, compare-and-swap (Redis `WATCH`/Lua, DB serializable), or single-writer serialization.

**Architecture:** Anywhere two execution contexts touch shared mutable state — threads, coroutines, replicas, cron + API.

**Implementation:**

```sql
UPDATE accounts SET balance = balance + 50 WHERE id = 1;   -- atomic
```

```python
# Redis compare-and-set via Lua (atomic)
lua = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('set',KEYS[1],ARGV[2]) else return 0 end"
```

```python
import asyncio
async with lock:  # asyncio.Lock for single-process; Redis lock across processes
    balance = get(); set(balance + 50)
```

**FastAPI Example:** Use `asyncio.Lock` only within one process; for multi-replica use Postgres atomic statement or Redis lock — never `asyncio.Lock` alone as correctness for money.

**Production Example:** Coupon redemption counter: 200 parallel "first 100 users" requests, all read redeemed=99 → all pass → 180 redemptions. Fixed with `UPDATE coupons SET redeemed = redeemed + 1 WHERE code='X' AND redeemed < 100` — affected-rows check enforces the cap.

**Failure Scenarios:** GET-then-POST double submit (no idempotency); check-then-create violating unique constraint (add unique index and catch IntegrityError instead of pre-check); counters drifting; file "replace" half-written (write temp + atomic rename); test suite passes, production interleaves differently.

**Best Practices:** Prefer atomic SQL over read-then-write; unique constraints + INSERT ... ON CONFLICT over pre-checks; idempotency keys for client retries; avoid check-then-act between separate round trips; serialize money operations; code review for shared mutable state.

**Anti-Patterns:** `if not exists: create`; in-memory counters in multi-worker apps; `asyncio.Lock` as distributed correctness; fixing by adding sleep(); relying on single-threaded dev environment.

**Trade-offs:** Performance (atomic ops are fast — better than locking); complexity (design for invariants, not timing); cost (free); consistency (strong); maintainability (explicit constraints outlive clever code).

**Testing:** pytest with `threading`/`asyncio.gather` hammering the operation 50x asserting invariant; force interleavings with barriers/monkeypatched sleeps; property test (hypothesis) generating concurrent op sequences; integration test at real concurrency.

**Related Concepts:** `#36 Optimistic Locking`, `#37 Pessimistic Locking`, `#40 Deadlocks`, `#43 Thread Safety`, `#14 Idempotency`, `#38 Distributed Locks`.

**Decision Criteria:** Use when: always — ask "what if two run at once?" for every write path. Do not use when: operation is provably single-threaded and single-process (rare). Alternatives: event-sourced single writer, `#38 Distributed Locks`, serializable isolation (Postgres SSI — heavy).

### 40. Deadlocks

**Definition:** A cycle of transactions each waiting for a lock held by another; none can proceed; the database detects the cycle and aborts one victim.

**Problem:** Under concurrency, deadlocks spike during contention-heavy flows and show up as intermittent 40P01 errors that look random and are maddening to reproduce.

**Internal Working:** Each transaction acquires row/page locks; lock manager detects wait cycles (waits-for graph) → aborts the cheapest victim → client sees `deadlock detected`. Prevention: consistent lock acquisition order (always lock rows in ascending ID), short transactions, fewer locks per transaction, `NOWAIT`, `SKIP LOCKED`, avoiding user think time inside transactions. Retry the victim transaction — deadlocks are expected under concurrency.

**Architecture:** Inside the transaction manager; invisible to the app except error code `40P01` (Postgres).

**Implementation:**

```python
from tenacity import retry, stop_after_attempt, wait_random
@retry(stop=stop_after_attempt(3), wait=wait_random(0.05, 0.3), retry=retry_if_exception(is_deadlock))
def transfer_funds(a, b, amount):
    with session.begin():
        x, y = sorted([a, b])          # consistent lock order — prevents most deadlocks
        lock_rows(x); lock_rows(y)
        debit(x); credit(y)
```

**FastAPI Example:** Retry-on-deadlock decorator in the service layer; return generic 503 after 3 victims with correlation id logged.

**Production Example:** Nightly bulk reconcile deadlocking against day-time order writes every run; reordered to lock by `order_id` ascending; deadlocks 40/day → 0.

**Failure Scenarios:** Two transactions locking accounts A,B vs B,A in opposite order (classic); `UPDATE ... WHERE status='x'` touching unindexed predicate → row lock escalation; long transaction holding locks blocks everyone; retrying victim without fixing order re-deadlocks; pool full of deadlock victims.

**Best Practices:** Lock in one deterministic global order; keep transactions < 100ms; index predicates so locks are precise; log lock waits (`log_lock_waits=on`); retry victim with jitter; monitor deadlock rate per query — top offender tells you the design flaw; prefer `SKIP LOCKED` in workers.

**Anti-Patterns:** Blanket retry without ordering fix; transactions spanning HTTP calls; `SELECT FOR UPDATE` then user input; table locks; ignoring `log_lock_waits`.

**Trade-offs:** Performance (avoidance usually improves throughput too); complexity (discipline, not machinery); cost (free); consistency (deadlock aborts preserve it); maintainability (documented lock ordering).

**Testing:** pytest forcing opposite-order transactions with threads; assert one aborts and retry succeeds; load test the suspected query under contention; chaos test killing a victim mid-cycle.

**Related Concepts:** `#37 Pessimistic Locking`, `#39 Race Conditions`, `#36 Optimistic Locking`, `#28 Connection Pooling`, `#12 Retries` (victim retry).

**Decision Criteria:** Use when: diagnosis + prevention — always watch for it. Do not use when: you don't have consistent ordering anywhere (fix design first). Alternatives: optimistic locking, single-statement atomic updates, `SKIP LOCKED`, queue-based single-writer serialization.

### 81. Database Migrations

**Definition:** Version-controlled, sequential, reversible scripts that evolve the schema in lockstep with the code — the database's own change history.

**Problem:** Ad hoc `ALTER TABLE` in production causes drift, failed deploys, and unrecoverable split states between code and schema.

**Internal Working:** A ledger table (`alembic_version` / `schema_migrations`) records applied revisions. Each migration has upgrade + downgrade (or is marked irreversible). Dependency chain enforced by revision ids. Safe migrations: **expand → migrate data → contract** (add nullable column → backfill → add constraint in a later deploy). Locking: `CONCURRENTLY` for indexes, batch tools (gh-ost, pg_repack) for big tables, avoiding long-held exclusive locks.

**Architecture:** Alembic migrations run as part of CI/CD (or a pre-deploy Job), not by hand; app code expects schema at revision N.

**Implementation:**

```bash
alembic revision -m "add orders.status" --autogenerate
alembic upgrade head
alembic downgrade -1
# big table:
CREATE INDEX CONCURRENTLY ix_big ON big_table (col);   -- manual, non-transactional
```

```python
def upgrade():
    op.add_column("orders", sa.Column("status", sa.String(20), nullable=True))
    op.create_index("ix_orders_status", "orders", ["status"], postgresql_concurrently=True)
```

**Production Example:** 90-day fleet migration: expand (add nullable), backfill 120M rows in batches of 5k with pg_sleep throttle, switch reads behind `status IS NOT NULL` flag, deploy contract (NOT NULL after 2 weeks). Zero downtime.

**Failure Scenarios:** Migration holds AccessExclusiveLock on big table → all queries queue → timeout storm → deploy rollback (fix: batched/concurrent); irreversible data-loss migration deployed without backup; migration graph diverges between environments; partial failure leaves half-backfilled data with ambiguous state; autogenerate producing wrong ops (manual review required).

**Best Practices:** Small, frequent, reversible migrations; expand/contract for breaking changes; backup before contract; CONCURRENTLY indexes; backfill in bounded batches with throttling; CI runs migrations against disposable DB; never edit applied migrations — write a new one; keep downgrade or explicitly mark irreversible; separate schema change from data deletion by days.

**Anti-Patterns:** One giant migration per release; NOT NULL without default on huge table (full rewrite + lock); editing merged migration files; dropping column before code stops reading it; migrations as deploy side effect without readiness gates.

**Trade-offs:** Performance (concurrent/batched = slow but safe); complexity (expand/contract ceremony); cost (free); consistency (guaranteed ordering); maintainability (excellent — same PR code+schema).

**Testing:** Migrate up/down on empty DB in CI; up/down on a production-like data copy; concurrency test (migration while traffic runs); rollback drill; schema-drift check (`alembic check`).

**Related Concepts:** `#82 Schema Versioning`, `#25 Database Indexing`, `#55 Rollbacks`, `#6 CI/CD`, `#52 Blue-Green Deployment`, `#81 Database Migrations`.

**Decision Criteria:** Use when: always. Do not use when: never applicable — every schema change needs one. Alternatives: none; manual DDL is the anti-pattern this replaces.

### 82. Schema Versioning

**Definition:** Tracking which schema version each environment and application instance expects, and enforcing that code and schema evolve together safely.

**Problem:** Code at rev N+1 against schema at N (missing column) crashes at runtime; rolling deploys need compatibility windows where two code versions coexist on one schema.

**Internal Working:** `alembic_version` table is the source of truth. Rolling deploy compatibility rule: for any deploy, N and N+1 code must both run against the current schema (expand-migrate-contract). Backward-compat window: keep old columns until all fleet is on new code (track rollout). Also version the *data contract* for events (schema registry) — same idea, for messages.

**Architecture:** Migration ledger + deployment pipeline ordering (migrate → deploy app) + compatibility checklist in PR template.

**Implementation:** `alembic current`, `alembic upgrade head` in CI pre-deploy job; app startup assertion: compare `alembic_version` with code's expected revision; refuse to boot on mismatch (fail fast).

**Production Example:** `orders.status` added nullable at rev 041; blue-green deploy; 100% fleet on 041 code for 48h; rev 042 adds NOT NULL; rollout; zero errors. `alembic check` in CI fails PRs that drifted models from migrations.

**Failure Scenarios:** Deploy new code before migration completes → 500s; downgrade path broken → can't roll back code without breaking schema; hotfix migration edited in place → environments diverge silently; multiple parallel branches create conflicting revisions; schema-aware feature flags forgotten after split-brain deploy.

**Best Practices:** Fail-fast startup check; expand-migrate-contract always; no editing applied revisions; PR checklist "migrations backwards compatible"; registry for event schemas alongside DB; verify `alembic check` in CI; document compatibility windows.

**Anti-Patterns:** "Deploy and migrate together and hope"; deleting columns in same release as code change; one-way-only migrations with no tested downgrade; migration scripts not in the same PR as code.

**Trade-offs:** Performance (none); complexity (discipline); cost (free); consistency (forced); maintainability (pristine environments, zero drift).

**Testing:** CI: migrate → boot app → smoke test; two-version coexistence test (old code against new schema); `alembic check`; drift audit across envs.

**Related Concepts:** `#81 Database Migrations`, `#51 Feature Flags`, `#55 Rollbacks`, `#102 API Versioning` (same philosophy), `#6 CI/CD`.

**Decision Criteria:** Use when: always. Do not use when: n/a. Alternatives: schema registry for messages, contract tests against live schema.

<!--END-->
