# Reliability & Disaster Recovery Reference

Preparing for rare, catastrophic events: recovery planning, backups, failover, multi-region topology, chaos testing, and cost.

| # | Concept | One-line use case |
|---|---|---|
| 83 | Disaster Recovery | RPO/RTO plan for catastrophic loss |
| 84 | Backups | Recoverable copies of data |
| 85 | Failover | Automatic move to healthy standby |
| 86 | Multi-Region Deployment | Survive region-wide outage |
| 87 | Chaos Engineering | Inject failure before it finds you |
| 88 | Cost Optimization | Reliability and cost are not enemies |

### 83. Disaster Recovery

**Definition:** The set of policies, runbooks, and infrastructure that restore service after catastrophic events (region loss, data corruption, ransomware, mass accidental deletion); measured by **RPO** (acceptable data loss) and **RTO** (acceptable downtime).

**Problem:** Without a plan, recovery is improvised under maximum stress — the exact conditions guaranteeing mistakes; audits, contracts, and reality all demand tested recovery.

**Internal Working:** Tiers: backup-only (RPO hours/RTO hours), pilot light (core infra always on elsewhere, scale up on disaster), warm standby (scaled-down full system, minutes RPO), multi-site active-active (near-zero). The plan: inventory critical systems, define RPO/RTO per system, codify recovery as runbooks, automate via Terraform/Ansible, **test quarterly** by failing over for real. DR covers both infrastructure and data; data recovery alone is meaningless if you can't redeploy apps.

**Architecture:** Standby region/account; replicated data; IaC for full redeploy; DNS/traffic manager for cutover; comms plan; decision tree (declare disaster vs wait).

**Implementation:**

```
RPO ≤ 5 min  → synchronous replication (#32) or async with lag alert < 5min
RTO ≤ 1 h    → warm standby + IaC deploy + automated smoke tests
DR drill: quarterly: destroy staging region → redeploy → verify RTO/RPO measured
```

**Production Example:** Fintech: primary us-east-1, warm standby eu-west-1 (10% capacity, async replica 30s lag); quarterly drill: full cutover in 47 minutes, measured RPO 25s, RTO 47min — plan validated, audit passed; real event in 2025 (regional S3 outage) was cutover in 32 minutes with zero customer data loss.

**Failure Scenarios:** Backups exist but restoring took 6 hours (never rehearsed); RPO assumed 0 but replication async; DNS TTL 300s delaying cutover (use health-checked global accelerator instead); standby region drifted (config ≠ prod, different instance types); secrets not available in DR region; single person knows the runbook; "DR region" behind same control plane (us-east-1 etcd failure takes both).

**Best Practices:** RPO/RTO per system, agreed with business; IaC reproduces everything; quarterly measured drills; automated smoke verification; data replication lag alerting; cross-region secrets + registry replication; runbook tested by people who weren't in the room; post-drill report to leadership.

**Anti-Patterns:** Backups-only plan sold as DR; DR region never started up; RPO/RTO fiction; manual steps in runbooks; drills skipped ("too costly" — cost of disaster is unbounded); DR plan covers infra not data validation.

**Trade-offs:** Performance (multi-active adds latency consistency tradeoffs); complexity (highest in infra); cost (pilot light ≈ 10-20% extra; active-active ≈ 100%+ extra); consistency (async = data loss window); maintainability (IaC + drills enforce hygiene).

**Testing:** Quarterly destroy-region drill with measured RTO/RPO; restore-backup drill; comms drill; data-integrity verification post-restore; runbook review by fresh engineer; audit score.

**Related Concepts:** `#84 Backups`, `#85 Failover`, `#86 Multi-Region Deployment`, `#32 Replication`, `#87 Chaos Engineering`, `#111 Postmortems`.

**Decision Criteria:** Use when: any production system with business continuity requirements. Do not use when: dev/sandbox. Alternatives: none — but depth scales with RPO/RTO: pilot light for most, active-active only for strict RTO≈0 business cases.

### 84. Backups

**Definition:** Time-stamped, recoverable copies of data at multiple points, protected from the same failures that threaten the primary, with verified restore capability.

**Problem:** Disk failure, ransomware, fat-fingered DELETE, and bad migrations — all unrecoverable without backups that are (a) independent, (b) recent, (c) tested.

**Internal Working:** RPO vs cost curve. Types: full/incremental/differential (incremental chains need all links), continuous WAL archiving for Postgres (PITR to any second), VSS/snapshots coordinated with app quiescence (flush buffers; pg_start_backup). 3-2-1 rule: 3 copies, 2 media, 1 offsite. Immutability: object-lock/WORM storage against ransomware deletion; backups encrypted (`#72`); retention policy (daily 30d, monthly 12mo) and deletion hygiene (GDPR right-to-erasure applies to backups too — plan). Restore drills are the only proof.

**Architecture:** Primary -> WAL/snapshot stream -> immutable object storage (3-2-1) in a separate account/region; lifecycle tiers hot->cold; restore-tested into an isolated account; backups are first-class IaC-managed resources.

**Implementation:**

```bash
pg_basebackup -U replicator -D backup_dir -Ft -z -P
pg_dump --format=custom -f app.dump mydb        # logical, portable
# WAL archiving: archive_command = 'aws s3 cp %p s3://wal/%f'
restic backup /data --repo s3:s3.amazonaws.com/bucket --exclude-caches
```

Managed: RDS automated backups (7-35d) + cross-region snapshots.

**Production Example:** Postgres fleet: nightly `pg_dump` to S3 + continuous WAL to separate region; object-lock 30 days; monthly restore into an isolated account; the 2026 bad-migration incident: PITR restored to 4 minutes before the bad deploy; 20 minutes of lost writes replayed from the outbox; zero customer-visible corruption.

**Failure Scenarios:** Backup runs but restore impossible (encryption key unavailable, format mismatch); backups 3 days old (retention misconfigured); production and backups in same account (ransomware deletes both); logical dumps during heavy write (inconsistent without snapshot); backup job silently failing (no alert on last-successful-age); unencrypted dumps on laptop; GDPR erasure meaningless because backup retains PII forever.

**Best Practices:** 3-2-1-1; encrypted offsite immutable storage; age-of-latest-backup alert; monthly restore test; WAL/PITR for transactional DBs; backup credentials different from prod credentials; test restore into isolated account; retention schedule documented; chaos: delete random snapshot and verify others survive.

**Anti-Patterns:** Untested restores; backup on same array/provider/account; `pg_dump` from cron nobody monitors; retention forever (cost + privacy); backup of app but not config/secrets/IaC; treating snapshots as backups (snapshots are not logical-corruption protection).

**Trade-offs:** Performance (pg_dump load; incremental + WAL minimize); complexity (low-moderate); cost (storage ≈ small % of DB size); consistency (online snapshot consistency + WAL = point-in-time); maintainability (automated + verified = set and forget).

**Testing:** Monthly automated restore; checksum verification; PITR to random recent minute on staging; deletion-restoration test; backup-failure alert fire-drill.

**Related Concepts:** `#83 Disaster Recovery`, `#72 Encryption at Rest`, `#55 Rollbacks`, `#32 Replication` (replication ≠ backup), `#81 Database Migrations` (backup before DDL).

**Decision Criteria:** Use when: always for any state. Do not use when: n/a. Alternatives: none — replication is availability, not a backup substitute.

### 85. Failover

**Definition:** The automatic or manual reassignment of traffic from a failed component (node, DB, AZ, region) to a healthy standby, minimizing error rate and duration.

**Problem:** Without failover, a single node failure = hard outage; with slow manual failover, a 30-second incident becomes a 30-minute one.

**Internal Working:** Detection (heartbeat/probe with ~seconds budget), decision (majority vote/consensus/DCS to avoid split brain), action (promote replica, swap LB targets, update DNS/accelerator), fencing (reject old leader — STONITH), draining (in-flight requests). Active-passive vs active-active. HA solutions: Patroni+etcd (Postgres), K8s leader election for singletons, Route 53 health-checked failover routing, Redis Sentinel. RPO/RTO trade: synchronous replication gives RPO=0; async gives small loss but less latency.

**Architecture:** Health probes → DCS (etcd/Consul) → orchestration → LB/DNS/DB promotion.

**Implementation:**

```
Patroni: etcd DCS, ttl=30, loop_wait=10, maximum_lag_on_failover=5MB
Route 53: failover routing policy, PRIMARY/SECONDARY + health checks (fast, 10s)
K8s: migrating Deployment to healthy zone = pod reschedule + probes
```

**Production Example:** Primary DB AZ-1 disk failure at 14:03; Patroni detected in 2s, DCS promoted AZ-2 replica (lag 0.4s); fence issued to old primary's IPMI; app reconnected within 8s; 3 write errors during cutover retried transparently; zero data loss; RTO 8 seconds.

**Failure Scenarios:** Split brain (both primary and new-primary accept writes — must fence); failover of a lagging replica → seconds of data loss (max_lag threshold); flapping (failure detector too sensitive — hysteresis needed); failover of the control plane (consensus dead in both AZs); clients caching old IP past TTL (use LB/accelerator, short TTL); "automatic" but runbook actually says "wait for human"; failover test that freezes the witness.

**Best Practices:** Fence the old primary (never trust "it's probably dead"); lag threshold for promotion; health checks ≠ deep app checks (cheap); hysteresis against flapping; test failover monthly (gameday); application reconnect logic with backoff; document manual trigger; monitor promotion count on dashboards; prefer managed failover (RDS/Cloud SQL/Patroni).

**Anti-Patterns:** Manual-only failover; no fencing; auto-promote replicas regardless of lag; identical AZs for "different" datacenters; health checks that pass while degraded; app assumes provider DNS instantly converges.

**Trade-offs:** Performance (sync replication adds quorum RTT); complexity (moderate-high); cost (standby capacity); consistency (RPO choice); maintainability (managed >> DIY).

**Testing:** Monthly automated failover drill measuring RTO; fencing verification (old leader write rejected); DNS TTL test; client reconnect storm test; chaos AZ kill.

**Related Concepts:** `#33 Leader Election`, `#32 Replication`, `#83 Disaster Recovery`, `#86 Multi-Region Deployment`, `#56 Health Checks`, `#95 Network Partitions`.

**Decision Criteria:** Use when: any single point of unavailability is unacceptable. Do not use when: acceptable RTO of hours (backup/restore suffices — `#84`). Alternatives: n/a — failover is the mechanism; breadth depends on RPO/RTO tier.

### 86. Multi-Region Deployment

**Definition:** Running the system in two or more geographic regions concurrently — active-active (both serve) or active-passive (standby serves failover) — for survive-region loss, latency, or data residency.

**Problem:** A single region is a single blast radius: region-wide cloud outages (they happen regularly) can take your service, and only multi-region survives them.

**Internal Working:** Data replication across regions: sync (only same-metro, e.g., us-east-1a→1b) or async (us-east-1→eu-west-1, RPO seconds-minutes). Global ingress: anycast/global accelerator/Route 53 latency routing steers users to nearest healthy region. Active-active data needs conflict handling (CRDTs, LWW, or shard-write-own-region with follow-the-sun) or accept divergent reads briefly. Stateless app layer replicates trivially; the database is the hard part (DynamoDB global tables, Spanner multi-region, CockroachDB, Aurora Global, logical replication).

**Architecture:** Two regions; each with LB+app+DB; replication link(s); global DNS/accelerator health-based routing; IaC for both; replication lag alerting; conflict-resolution policy documented.

**Implementation:**

```
Route 53 latency routing + health checks → region endpoints
DynamoDB global tables (multi-active, last-writer-wins) or
Aurora Global Database (async <1s lag, region promotion ~1min)
S3 CRR replication; SQS per region + cross-region fanout
```

**Production Example:** Chat/SaaS: active-active us-east-1 + eu-west-1 (users pinned by latency to nearest; writes to primary-of-user region; reads local; PII residency for EU pinned to eu); eu region loss → accelerator routes all traffic to us, 40s degraded reads, zero data loss; us-east outage in 2026 handled transparently for 63% of traffic.

**Failure Scenarios:** Async replication lag spike → users switching regions see older data; dual-active write conflict (same cart in both regions) → corrupt cart unless LWW/CRDT; failover during partition: both regions think the other is dead → divergent writes (must define one writer or use conflict-free types); inter-region latency (~35-120ms) eating p99; costs double+; config drift between "identical" regions (they never are — inventory both with tooling); observability split per region; replication of secrets/certs/images forgotten.

**Best Practices:** Pin data residency where legal; global accelerator not DNS TTL for cutover; one designated writer per entity (or CRDT); lag SLOs with alerts; IaC ×2; identical observability stack per region with a unified dashboard; quarterly failover drill cross-region; cost model pre-agreed; warm-capacity in DR region sized ≥ 30%.

**Anti-Patterns:** "Multi-region" DNS-only without data replication (advertised DR, actual total loss); two writers on strongly-consistent data without conflict resolution; same cloud region pair behind one control plane domain; replication without monitoring; 100% active-active when active-passive would do (2x cost for 1% gain); forgetting artifacts (image registry, helm charts) replication.

**Trade-offs:** Performance (locality wins for latency; cross-region RTT losses inside); complexity (very high, especially data); cost (most expensive tier — 1.6-2.5x); consistency (async staleness; conflicts); maintainability (fleet-wide discipline; IaC non-negotiable).

**Testing:** Kill-region game day; replication-lag alarm test; conflict injection test (same key written both regions → resolution correct); RTO/RPO measurement; cross-region restore verification; residency compliance audit.

**Related Concepts:** `#83 Disaster Recovery`, `#85 Failover`, `#34 CAP Theorem`, `#32 Replication`, `#48 CDN`, `#33 Leader Election`.

**Decision Criteria:** Use when: regulatory data residency, SLO unattainable in one region, active legal/executive commitment to region-loss survival. Do not use when: single-region RPO/RTO acceptable (most products — cost not justified). Alternatives: warm standby (pilot light), cross-AZ HA (covers 90% of failures), managed global services (DynamoDB Global Tables/Aurora Global).

### 87. Chaos Engineering

**Definition:** The discipline of injecting controlled failures (kill instances, delay networks, fill disks, corrupt caches) into systems to discover weaknesses before they cause incidents, under observation with a clear hypothesis.

**Problem:** Untested resilience claims are theory; the first time your failover logic runs under real stress may not be during your drill — it's usually during your worst outage.

**Internal Working:** Scientific method: hypothesis ("if AZ-1 DB replica dies, writes continue with < 10s impact") → blast radius control (start with one staging instance, synthetic traffic) → steady-state metrics → inject (kill, partition, latency, CPU, error injection, dependency outage) → observe → fix → repeat in production with guardrails (abort on SLO breach). Tools: Chaos Mesh (K8s), LitmusChaos, AWS FIS, Gremlin, steady-state via Prometheus. Start small, narrow, rehearsed — not "delete prod".

**Architecture:** Chaos controller (Chaos Mesh/Litmus/AWS FIS) -> injects into targeted pods/zones -> steady-state metrics watched on dashboards -> auto-abort on SLO breach; experiments defined as versioned manifests in Git.

**Implementation:**

```yaml
# Chaos Mesh pod kill (excerpt)
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata: { name: kill-api-pod }
spec: { action: pod-kill, mode: one, selector: { namespaces: [prod], labelSelectors: {app: api} }, duration: "5m" }
```

```bash
# aws fis or litmusctl run experiment <id>  — then watch dashboards, abort on SLO breach
```

**Production Example:** Quarterly game day: kill the primary Redis mid-cache-refresh and the team discovered the app had no fallback — cold cache + no stampede protection → 40% error rate; fixed with lock + stale-while-revalidate; next drill: clean recovery in 20s.

**Failure Scenarios:** Blast radius unbounded (experiment in prod without caps) → actual outage caused by "chaos"; hypothesis absent (random destruction, learned nothing); SLO breach ignored (drill became real incident — set automatic abort); fixing nothing afterward (drill theater); injecting during peak without warning; blaming people not systems; "chaos" as substitute for missing retries/timeouts.

**Best Practices:** Hypothesis + steady state required; narrow blast radius first (single pod, staging, then prod canary); abort on SLO breach; one variable at a time; fix findings and re-run; game days quarterly; include dependency third-parties (fake their outages); document results publicly inside the org; never as punishment.

**Anti-Patterns:** Chaos without monitoring/abort; "delete a random prod host" (unplanned blast); chaos to prove smartness rather than find bugs; never re-testing the same failure; chaos instead of fixing known weaknesses; skipping the human comms plan.

**Trade-offs:** Performance (none if budgeted); complexity (tooling + runbooks); cost (minimal infra); consistency (n/a); maintainability (cultural practice — needs executive buy-in and no-blame culture).

**Testing:** The practice itself is the test; verify abort switches work; staging-first protocol; game-day scorecard tracked over quarters (mean time to detect, mean time to recover).

**Related Concepts:** `#83 Disaster Recovery`, `#85 Failover`, `#10 Circuit Breakers`, `#95 Network Partitions`, `#109 Production Incidents`, `#111 Postmortems`.

**Decision Criteria:** Use when: production systems serving real users where unexpected failure is unaffordable (so most systems). Do not use when: staging doesn't exist; system unobservable (no metrics — fix that first); team forbidden to touch prod. Alternatives: failover drills only, disaster recovery tabletop exercises, simulation testing (Jepsen-style).

### 88. Cost Optimization

**Definition:** Continuous engineering of spend against value — sizing, pricing models, architecture efficiency, idle waste elimination — while never compromising required reliability.

**Problem:** Cloud bills drift up silently (over-provisioned instances, unmanaged storage, forgotten environments, inefficient queries) while nobody owns the number; cost is a reliability-adjacent discipline, not finance's problem.

**Internal Working:** Levers: right-sizing (CPU/memory utilization < 40% for 2 weeks → downsize), pricing models (on-demand → savings plans/RIs/spot for fault-tolerant workers), storage lifecycle (hot→warm→cold tiering, orphan volumes), architecture (cache hot reads, serverless off-peak, spot fleets), data transfer (biggest hidden cost — cross-region egress $0.02-0.09/GB), LLM cost control (token limits, caching, smaller models, prompt trimming). FinOps loop: measure (tag by team/service) → report (showback/chargeback) → optimize (top offenders) → budget alerts. Never cut below the reliability floor — cost decisions use the same decision framework (`#63 SLOs`): budget cuts only capacity that headroom wasn't using, or optimizations with no SLO impact.

**Architecture:** Tagging + cost allocation + FinOps tooling + PR-level cost review.

**Implementation:**

```bash
aws ce get-cost-and-usage --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY --metrics BlendedCost --group-by Type=TAG,Key=service
kubectl top pods -A | sort -k2 -rn   # oversized requests
```

K8s: VPA recommendations; cluster autoscaler; spot node pools for queues; `kubectl idle` analysis.

**Production Example:** 14 services tagged; $180k/month bill reviewed; findings: two m5.4xlarge at 8% CPU → m5.xlarge (saves $4k); unattached EBS 9TB ($800); NAT gateway cross-AZ chatter ($2k); LLM prompt regression burning $12k → prompt trim + cache (saves $9k); total −$15k/month with zero SLO change.

**Failure Scenarios:** Cost hunting that disables HA (cuts the standby — false economy); cutting cache layer → DB overload → outage (cost "saving" = incident); spot capacity revoked at peak → worker fleet vanishes (use spot only for retry-tolerant queues); ignoring data egress (biggest line item surprise); cutting observability to save 2%; no budget alert → $40k surprise month; optimizations applied once and forgotten (reservations expire).

**Best Practices:** Tag everything; monthly top-5 cost review; utilization < 40% → downsize; RI/Savings Plans for baseline, spot for burst/batch; storage lifecycle rules; egress minimization; cost as a design review item; alert at 80% budget; measure LLM spend per feature; FinOps dashboard shared with teams (showback drives behavior).

**Anti-Patterns:** Cutting redundancy first; spot for stateful primaries; no tagging (can't attribute); one-time optimization without recurring review; cost policing by finance alone with no engineering context; "just delete the DB" energy on usage-based features.

**Trade-offs:** Performance (under-provisioning risks latency — headroom is a feature; target right, not minimum); complexity (FinOps practice); cost (obviously reduced); consistency (n/a); maintainability (automation of right-sizing recommendations).

**Testing:** Budget alert test; spot interruption drill; quarterly right-size review against p95 latency and SLO (never degrade below SLO); cost regression as PR gate for big changes.

**Related Concepts:** `#63 SLOs`, `#88 Cost Optimization` pairs with `#45 Autoscaling`, `#47 Vertical Scaling`, `#50 Cache Invalidation`, `#90 Serverless Limits` (LLM spend), `#2 Caching`.

**Decision Criteria:** Use when: always — as a continuous review. Do not use when: never justifiable; always weigh against SLOs. Alternatives: n/a — this is the process for spending wisely.

<!--END-->
