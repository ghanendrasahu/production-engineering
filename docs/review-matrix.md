# Independent Review Matrix — 111 Topics

Method (honest scope):

- **Structure**: every topic programmatically verified — 24 required sections present, frontmatter valid, code fences balanced, no placeholders, ≥300 words (avg ≈1,184), numbering 1–111 unique, canonical titles match scope.
- **Links**: all internal links resolve; all external reference links in §24 were fetched and fixed (22 corrected 2026-11-08); remaining unreachable ones are fake example hosts by design.
- **Fact-check status**:
  - **Verified against primary sources (this pass)**: SRE burn-rate alerting (Google SRE Workbook ch.5: 14.4x/1h long+5m short page, 6x/6h+30m page, 1x/3d+6h ticket); SLO error-budget arithmetic (corrected to 43.2 min at 99.9% / 21.6 min at 99.95% per 30d); WHATWG HTML SSE spec (RFC6202 error fixed); HTTP/2 Rapid Reset CVE id; Raft election-timer range; PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` pattern; Prometheus histogram function names; TLS 1.3 cipher suites listed.
  - **Not fact-checked line-by-line**: narrative production scenarios (illustrative, labeled as such), latency/QPS figures in examples (representative industry values, not benchmarks), legal figures (Capital One SSRF exposure, ~$190M reported).
- **✅ Structure | ✅ Links | — fact-check depth not individually re-verified beyond the scope above; tracked in issue #14.**

| # | Topic | Cat | Structure | Links | Fact depth |
|---|---|---|---|---|---|
| 1 | [Rate Limiting](../.agents/skills/production-engineering/topics/001-rate-limiting.md) | A | ✅ | ✅ | — |
| 2 | [Caching](../.agents/skills/production-engineering/topics/002-caching.md) | A | ✅ | ✅ | — |
| 3 | [Load Balancing](../.agents/skills/production-engineering/topics/003-load-balancing.md) | A | ✅ | ✅ | — |
| 4 | [Reverse Proxies](../.agents/skills/production-engineering/topics/004-reverse-proxies.md) | A | ✅ | ✅ | — |
| 5 | [API Gateways](../.agents/skills/production-engineering/topics/005-api-gateways.md) | A | ✅ | ✅ | — |
| 6 | [CI/CD](../.agents/skills/production-engineering/topics/006-ci-cd.md) | A | ✅ | ✅ | — |
| 7 | [Docker](../.agents/skills/production-engineering/topics/007-docker.md) | A | ✅ | ✅ | — |
| 8 | [Kubernetes](../.agents/skills/production-engineering/topics/008-kubernetes.md) | A | ✅ | ✅ | — |
| 9 | [Service Discovery](../.agents/skills/production-engineering/topics/009-service-discovery.md) | A | ✅ | ✅ | — |
| 10 | [Circuit Breakers](../.agents/skills/production-engineering/topics/010-circuit-breakers.md) | A | ✅ | ✅ | — |
| 11 | [Timeouts](../.agents/skills/production-engineering/topics/011-timeouts.md) | A | ✅ | ✅ | — |
| 12 | [Retries](../.agents/skills/production-engineering/topics/012-retries.md) | A | ✅ | ✅ | — |
| 13 | [Exponential Backoff](../.agents/skills/production-engineering/topics/013-exponential-backoff.md) | A | ✅ | ✅ | — |
| 14 | [Idempotency](../.agents/skills/production-engineering/topics/014-idempotency.md) | A | ✅ | ✅ | — |
| 15 | [Message Queues](../.agents/skills/production-engineering/topics/015-message-queues.md) | A | ✅ | ✅ | — |
| 16 | [Pub/Sub](../.agents/skills/production-engineering/topics/016-pub-sub.md) | A | ✅ | ✅ | — |
| 17 | [Event-Driven Architecture](../.agents/skills/production-engineering/topics/017-event-driven-architecture.md) | A | ✅ | ✅ | — |
| 18 | [Distributed Transactions](../.agents/skills/production-engineering/topics/018-distributed-transactions.md) | A | ✅ | ✅ | — |
| 19 | [Saga Pattern](../.agents/skills/production-engineering/topics/019-saga-pattern.md) | A | ✅ | ✅ | — |
| 20 | [Dead Letter Queues](../.agents/skills/production-engineering/topics/020-dead-letter-queues.md) | A | ✅ | ✅ | — |
| 21 | [Cron Jobs](../.agents/skills/production-engineering/topics/021-cron-jobs.md) | A | ✅ | ✅ | — |
| 22 | [WebSockets](../.agents/skills/production-engineering/topics/022-websockets.md) | A | ✅ | ✅ | — |
| 23 | [Long Polling](../.agents/skills/production-engineering/topics/023-long-polling.md) | A | ✅ | ✅ | — |
| 24 | [Server-Sent Events](../.agents/skills/production-engineering/topics/024-server-sent-events.md) | A | ✅ | ✅ | — |
| 25 | [Database Indexing](../.agents/skills/production-engineering/topics/025-database-indexing.md) | B | ✅ | ✅ | — |
| 26 | [Query Optimization](../.agents/skills/production-engineering/topics/026-query-optimization.md) | B | ✅ | ✅ | — |
| 27 | [N+1 Queries](../.agents/skills/production-engineering/topics/027-n-plus-1-queries.md) | B | ✅ | ✅ | — |
| 28 | [Connection Pooling](../.agents/skills/production-engineering/topics/028-connection-pooling.md) | B | ✅ | ✅ | — |
| 29 | [Read Replicas](../.agents/skills/production-engineering/topics/029-read-replicas.md) | B | ✅ | ✅ | — |
| 30 | [Sharding](../.agents/skills/production-engineering/topics/030-sharding.md) | B | ✅ | ✅ | — |
| 31 | [Partitioning](../.agents/skills/production-engineering/topics/031-partitioning.md) | B | ✅ | ✅ | — |
| 32 | [Replication](../.agents/skills/production-engineering/topics/032-replication.md) | B | ✅ | ✅ | — |
| 33 | [Leader Election](../.agents/skills/production-engineering/topics/033-leader-election.md) | B | ✅ | ✅ | — |
| 34 | [CAP Theorem](../.agents/skills/production-engineering/topics/034-cap-theorem.md) | B | ✅ | ✅ | — |
| 35 | [Eventual Consistency](../.agents/skills/production-engineering/topics/035-eventual-consistency.md) | B | ✅ | ✅ | — |
| 36 | [Optimistic Locking](../.agents/skills/production-engineering/topics/036-optimistic-locking.md) | B | ✅ | ✅ | — |
| 37 | [Pessimistic Locking](../.agents/skills/production-engineering/topics/037-pessimistic-locking.md) | B | ✅ | ✅ | — |
| 38 | [Distributed Locks](../.agents/skills/production-engineering/topics/038-distributed-locks.md) | B | ✅ | ✅ | — |
| 39 | [Race Conditions](../.agents/skills/production-engineering/topics/039-race-conditions.md) | B | ✅ | ✅ | — |
| 40 | [Deadlocks](../.agents/skills/production-engineering/topics/040-deadlocks.md) | B | ✅ | ✅ | — |
| 41 | [Memory Leaks](../.agents/skills/production-engineering/topics/041-memory-leaks.md) | B | ✅ | ✅ | — |
| 42 | [Garbage Collection](../.agents/skills/production-engineering/topics/042-garbage-collection.md) | B | ✅ | ✅ | — |
| 43 | [Thread Safety](../.agents/skills/production-engineering/topics/043-thread-safety.md) | B | ✅ | ✅ | — |
| 44 | [Backpressure](../.agents/skills/production-engineering/topics/044-backpressure.md) | B | ✅ | ✅ | — |
| 45 | [Autoscaling](../.agents/skills/production-engineering/topics/045-autoscaling.md) | B | ✅ | ✅ | — |
| 46 | [Horizontal Scaling](../.agents/skills/production-engineering/topics/046-horizontal-scaling.md) | B | ✅ | ✅ | — |
| 47 | [Vertical Scaling](../.agents/skills/production-engineering/topics/047-vertical-scaling.md) | B | ✅ | ✅ | — |
| 48 | [CDN](../.agents/skills/production-engineering/topics/048-cdn.md) | B | ✅ | ✅ | — |
| 49 | [Edge Caching](../.agents/skills/production-engineering/topics/049-edge-caching.md) | B | ✅ | ✅ | — |
| 50 | [Cache Invalidation](../.agents/skills/production-engineering/topics/050-cache-invalidation.md) | B | ✅ | ✅ | — |
| 51 | [Feature Flags](../.agents/skills/production-engineering/topics/051-feature-flags.md) | C | ✅ | ✅ | — |
| 52 | [Blue-Green Deployment](../.agents/skills/production-engineering/topics/052-blue-green-deployment.md) | C | ✅ | ✅ | — |
| 53 | [Canary Releases](../.agents/skills/production-engineering/topics/053-canary-releases.md) | C | ✅ | ✅ | — |
| 54 | [Rolling Deployments](../.agents/skills/production-engineering/topics/054-rolling-deployments.md) | C | ✅ | ✅ | — |
| 55 | [Rollbacks](../.agents/skills/production-engineering/topics/055-rollbacks.md) | C | ✅ | ✅ | — |
| 56 | [Health Checks](../.agents/skills/production-engineering/topics/056-health-checks.md) | C | ✅ | ✅ | — |
| 57 | [Liveness & Readiness Probes](../.agents/skills/production-engineering/topics/057-liveness-and-readiness-probes.md) | C | ✅ | ✅ | — |
| 58 | [Monitoring](../.agents/skills/production-engineering/topics/058-monitoring.md) | C | ✅ | ✅ | — |
| 59 | [Logging](../.agents/skills/production-engineering/topics/059-logging.md) | C | ✅ | ✅ | — |
| 60 | [Distributed Tracing](../.agents/skills/production-engineering/topics/060-distributed-tracing.md) | C | ✅ | ✅ | — |
| 61 | [Metrics](../.agents/skills/production-engineering/topics/061-metrics.md) | C | ✅ | ✅ | — |
| 62 | [Alerts](../.agents/skills/production-engineering/topics/062-alerts.md) | C | ✅ | ✅ | — |
| 63 | [SLOs](../.agents/skills/production-engineering/topics/063-slos.md) | C | ✅ | ✅ | — |
| 64 | [SLIs](../.agents/skills/production-engineering/topics/064-slis.md) | C | ✅ | ✅ | — |
| 65 | [Error Budgets](../.agents/skills/production-engineering/topics/065-error-budgets.md) | C | ✅ | ✅ | — |
| 66 | [Observability](../.agents/skills/production-engineering/topics/066-observability.md) | C | ✅ | ✅ | — |
| 67 | [Secrets Management](../.agents/skills/production-engineering/topics/067-secrets-management.md) | D | ✅ | ✅ | — |
| 68 | [IAM](../.agents/skills/production-engineering/topics/068-iam.md) | D | ✅ | ✅ | — |
| 69 | [OAuth](../.agents/skills/production-engineering/topics/069-oauth.md) | D | ✅ | ✅ | — |
| 70 | [JWT Rotation](../.agents/skills/production-engineering/topics/070-jwt-rotation.md) | D | ✅ | ✅ | — |
| 71 | [TLS](../.agents/skills/production-engineering/topics/071-tls.md) | D | ✅ | ✅ | — |
| 72 | [Encryption at Rest](../.agents/skills/production-engineering/topics/072-encryption-at-rest.md) | D | ✅ | ✅ | — |
| 73 | [Encryption in Transit](../.agents/skills/production-engineering/topics/073-encryption-in-transit.md) | D | ✅ | ✅ | — |
| 74 | [WAF](../.agents/skills/production-engineering/topics/074-waf.md) | D | ✅ | ✅ | — |
| 75 | [DDoS Protection](../.agents/skills/production-engineering/topics/075-ddos-protection.md) | D | ✅ | ✅ | — |
| 76 | [CORS](../.agents/skills/production-engineering/topics/076-cors.md) | D | ✅ | ✅ | — |
| 77 | [CSRF](../.agents/skills/production-engineering/topics/077-csrf.md) | D | ✅ | ✅ | — |
| 78 | [SQL Injection](../.agents/skills/production-engineering/topics/078-sql-injection.md) | D | ✅ | ✅ | — |
| 79 | [XSS](../.agents/skills/production-engineering/topics/079-xss.md) | D | ✅ | ✅ | — |
| 80 | [SSRF](../.agents/skills/production-engineering/topics/080-ssrf.md) | D | ✅ | ✅ | — |
| 81 | [Database Migrations](../.agents/skills/production-engineering/topics/081-database-migrations.md) | E | ✅ | ✅ | — |
| 82 | [Schema Versioning](../.agents/skills/production-engineering/topics/082-schema-versioning.md) | E | ✅ | ✅ | — |
| 83 | [Disaster Recovery](../.agents/skills/production-engineering/topics/083-disaster-recovery.md) | F | ✅ | ✅ | — |
| 84 | [Backups](../.agents/skills/production-engineering/topics/084-backups.md) | F | ✅ | ✅ | — |
| 85 | [Failover](../.agents/skills/production-engineering/topics/085-failover.md) | F | ✅ | ✅ | — |
| 86 | [Multi-Region Deployment](../.agents/skills/production-engineering/topics/086-multi-region-deployment.md) | F | ✅ | ✅ | — |
| 87 | [Chaos Engineering](../.agents/skills/production-engineering/topics/087-chaos-engineering.md) | F | ✅ | ✅ | — |
| 88 | [Cost Optimization](../.agents/skills/production-engineering/topics/088-cost-optimization.md) | F | ✅ | ✅ | — |
| 89 | [Cold Starts](../.agents/skills/production-engineering/topics/089-cold-starts.md) | G | ✅ | ✅ | — |
| 90 | [Serverless Limits](../.agents/skills/production-engineering/topics/090-serverless-limits.md) | G | ✅ | ✅ | — |
| 91 | [Latency](../.agents/skills/production-engineering/topics/091-latency.md) | G | ✅ | ✅ | — |
| 92 | [Throughput](../.agents/skills/production-engineering/topics/092-throughput.md) | G | ✅ | ✅ | — |
| 93 | [P99 Latency](../.agents/skills/production-engineering/topics/093-p99-latency.md) | G | ✅ | ✅ | — |
| 94 | [Tail Latency](../.agents/skills/production-engineering/topics/094-tail-latency.md) | G | ✅ | ✅ | — |
| 95 | [Network Partitions](../.agents/skills/production-engineering/topics/095-network-partitions.md) | H | ✅ | ✅ | — |
| 96 | [Clock Skew](../.agents/skills/production-engineering/topics/096-clock-skew.md) | H | ✅ | ✅ | — |
| 97 | [DNS](../.agents/skills/production-engineering/topics/097-dns.md) | H | ✅ | ✅ | — |
| 98 | [TCP vs UDP](../.agents/skills/production-engineering/topics/098-tcp-vs-udp.md) | H | ✅ | ✅ | — |
| 99 | [HTTP/2 & HTTP/3](../.agents/skills/production-engineering/topics/099-http-2-and-http-3.md) | H | ✅ | ✅ | — |
| 100 | [gRPC](../.agents/skills/production-engineering/topics/100-grpc.md) | H | ✅ | ✅ | — |
| 101 | [Webhooks](../.agents/skills/production-engineering/topics/101-webhooks.md) | H | ✅ | ✅ | — |
| 102 | [API Versioning](../.agents/skills/production-engineering/topics/102-api-versioning.md) | H | ✅ | ✅ | — |
| 103 | [Semantic Versioning](../.agents/skills/production-engineering/topics/103-semantic-versioning.md) | H | ✅ | ✅ | — |
| 104 | [Infrastructure as Code](../.agents/skills/production-engineering/topics/104-infrastructure-as-code.md) | I | ✅ | ✅ | — |
| 105 | [Terraform](../.agents/skills/production-engineering/topics/105-terraform.md) | I | ✅ | ✅ | — |
| 106 | [Helm Charts](../.agents/skills/production-engineering/topics/106-helm-charts.md) | I | ✅ | ✅ | — |
| 107 | [Build Caching](../.agents/skills/production-engineering/topics/107-build-caching.md) | I | ✅ | ✅ | — |
| 108 | [Dependency Hell](../.agents/skills/production-engineering/topics/108-dependency-hell.md) | I | ✅ | ✅ | — |
| 109 | [Production Incidents](../.agents/skills/production-engineering/topics/109-production-incidents.md) | J | ✅ | ✅ | — |
| 110 | [On-Call](../.agents/skills/production-engineering/topics/110-on-call.md) | J | ✅ | ✅ | — |
| 111 | [Postmortems](../.agents/skills/production-engineering/topics/111-postmortems.md) | J | ✅ | ✅ | — |

## Notable corrections from this review

| Area | Finding | Action |
|---|---|---|
| topics 063/065, references/observability.md, CONTRIBUTING.md | "43.8 min/30d at 99.9%" and "21.9 min at 99.95%" — arithmetic error | Fixed → 43.2 / 21.6 |
| references/observability.md, topics 062 | Alert windows described as "14d long" / "6h+3d" — not SRE-recommended pairing | Fixed → multiwindow pairing per SRE Workbook ch.5 |
| topics 024 | RFC 6202 cited for SSE — invalid; no RFC defines SSE | Fixed → WHATWG HTML SSE spec |
| topics 044 | Dead link (O'Reilly "Release It!" URL rotated) | Fixed → release-it-2nd URL |
| 19 topic files | 21 dead external URLs (404/DNS) in §24 | All fixed to verified-200 URLs |

Review log: structure 111/111 ✅ · links 111/111 ✅ · fact corrections applied: 5 (all verified above)
