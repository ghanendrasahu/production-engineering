<div align="center">

# Production Engineering Skills

**Production-grade engineering knowledge for AI coding agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/ghanendrasahu/production-engineering)](https://github.com/ghanendrasahu/production-engineering/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/ghanendrasahu/production-engineering)](https://github.com/ghanendrasahu/production-engineering/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/ghanendrasahu/production-engineering)](https://github.com/ghanendrasahu/production-engineering/pulls)
[![Latest release](https://img.shields.io/github/v/release/ghanendrasahu/production-engineering)](https://github.com/ghanendrasahu/production-engineering/releases)
[![Contributors](https://img.shields.io/github/contributors/ghanendrasahu/production-engineering)](https://github.com/ghanendrasahu/production-engineering/graphs/contributors)

An open-source library of **111 production engineering topics** that teaches AI coding agents —
and the humans directing them — how to build secure, scalable, reliable, observable, and
maintainable software systems.

[**Browse the 111 topics**](#the-111-topics) · [Install](#installation) · [Usage](docs/usage.md) · [Supported agents](docs/supported-agents.md)

</div>

---

## Why This Exists

AI coding agents write code faster than ever. What they still miss is **engineering judgment**:
what to measure before optimizing, what fails at 3 AM, what "works on my machine" hides, and which
architecture is the simplest one that actually meets the requirements.

Production Engineering Skills packages senior-staff-level reasoning — the patterns, failure modes,
trade-offs, and checklists behind real production systems — into **agent-native documents** that get
retrieved on demand. No fluff, no definition dumps: every topic tells an agent *when* to apply a
pattern, *when not to*, and *how to verify it worked*.

## What's Inside

| Guarantee | Detail |
|---|---|
| 111 topics, numbered 1–111 | Original scope preserved — no omissions, no renames |
| 24-section deep documents | Mechanism → implementation → failure modes → testing → checklists |
| Agent-first format | OpenCode-compatible `.agents/skills/` discovery + portable Markdown |
| Real-world focused | FastAPI, Python, PostgreSQL, Redis, Kafka/RabbitMQ, Kubernetes, Terraform, LLM/RAG systems |
| Validated in CI | Numbering, structure, links, frontmatter — checked on every push |
| Community-governed | MIT, Contributor Covenant, security policy, roadmap |

## The 111 Topics (index)

Compact map; full documents with paths in [docs/topic-index.md](docs/topic-index.md).

All 111 topics, numbered 1–111, grouped by category. Topic IDs are stable forever — docs are never renumbered.

| # | Topic (path) | Category |
|---|---|---|
| 1 | [Rate Limiting](.agents/skills/production-engineering/topics/001-rate-limiting.md) | A |
| 2 | [Caching](.agents/skills/production-engineering/topics/002-caching.md) | A |
| 3 | [Load Balancing](.agents/skills/production-engineering/topics/003-load-balancing.md) | A |
| 4 | [Reverse Proxies](.agents/skills/production-engineering/topics/004-reverse-proxies.md) | A |
| 5 | [API Gateways](.agents/skills/production-engineering/topics/005-api-gateways.md) | A |
| 6 | [CI/CD](.agents/skills/production-engineering/topics/006-ci-cd.md) | A |
| 7 | [Docker](.agents/skills/production-engineering/topics/007-docker.md) | A |
| 8 | [Kubernetes](.agents/skills/production-engineering/topics/008-kubernetes.md) | A |
| 9 | [Service Discovery](.agents/skills/production-engineering/topics/009-service-discovery.md) | A |
| 10 | [Circuit Breakers](.agents/skills/production-engineering/topics/010-circuit-breakers.md) | A |
| 11 | [Timeouts](.agents/skills/production-engineering/topics/011-timeouts.md) | A |
| 12 | [Retries](.agents/skills/production-engineering/topics/012-retries.md) | A |
| 13 | [Exponential Backoff](.agents/skills/production-engineering/topics/013-exponential-backoff.md) | A |
| 14 | [Idempotency](.agents/skills/production-engineering/topics/014-idempotency.md) | A |
| 15 | [Message Queues](.agents/skills/production-engineering/topics/015-message-queues.md) | A |
| 16 | [Pub/Sub](.agents/skills/production-engineering/topics/016-pub-sub.md) | A |
| 17 | [Event-Driven Architecture](.agents/skills/production-engineering/topics/017-event-driven-architecture.md) | A |
| 18 | [Distributed Transactions](.agents/skills/production-engineering/topics/018-distributed-transactions.md) | A |
| 19 | [Saga Pattern](.agents/skills/production-engineering/topics/019-saga-pattern.md) | A |
| 20 | [Dead Letter Queues](.agents/skills/production-engineering/topics/020-dead-letter-queues.md) | A |
| 21 | [Cron Jobs](.agents/skills/production-engineering/topics/021-cron-jobs.md) | A |
| 22 | [WebSockets](.agents/skills/production-engineering/topics/022-websockets.md) | A |
| 23 | [Long Polling](.agents/skills/production-engineering/topics/023-long-polling.md) | A |
| 24 | [Server-Sent Events](.agents/skills/production-engineering/topics/024-server-sent-events.md) | A |
| 25 | [Database Indexing](.agents/skills/production-engineering/topics/025-database-indexing.md) | B |
| 26 | [Query Optimization](.agents/skills/production-engineering/topics/026-query-optimization.md) | B |
| 27 | [N+1 Queries](.agents/skills/production-engineering/topics/027-n-plus-1-queries.md) | B |
| 28 | [Connection Pooling](.agents/skills/production-engineering/topics/028-connection-pooling.md) | B |
| 29 | [Read Replicas](.agents/skills/production-engineering/topics/029-read-replicas.md) | B |
| 30 | [Sharding](.agents/skills/production-engineering/topics/030-sharding.md) | B |
| 31 | [Partitioning](.agents/skills/production-engineering/topics/031-partitioning.md) | B |
| 32 | [Replication](.agents/skills/production-engineering/topics/032-replication.md) | B |
| 33 | [Leader Election](.agents/skills/production-engineering/topics/033-leader-election.md) | B |
| 34 | [CAP Theorem](.agents/skills/production-engineering/topics/034-cap-theorem.md) | B |
| 35 | [Eventual Consistency](.agents/skills/production-engineering/topics/035-eventual-consistency.md) | B |
| 36 | [Optimistic Locking](.agents/skills/production-engineering/topics/036-optimistic-locking.md) | B |
| 37 | [Pessimistic Locking](.agents/skills/production-engineering/topics/037-pessimistic-locking.md) | B |
| 38 | [Distributed Locks](.agents/skills/production-engineering/topics/038-distributed-locks.md) | B |
| 39 | [Race Conditions](.agents/skills/production-engineering/topics/039-race-conditions.md) | B |
| 40 | [Deadlocks](.agents/skills/production-engineering/topics/040-deadlocks.md) | B |
| 41 | [Memory Leaks](.agents/skills/production-engineering/topics/041-memory-leaks.md) | B |
| 42 | [Garbage Collection](.agents/skills/production-engineering/topics/042-garbage-collection.md) | B |
| 43 | [Thread Safety](.agents/skills/production-engineering/topics/043-thread-safety.md) | B |
| 44 | [Backpressure](.agents/skills/production-engineering/topics/044-backpressure.md) | B |
| 45 | [Autoscaling](.agents/skills/production-engineering/topics/045-autoscaling.md) | B |
| 46 | [Horizontal Scaling](.agents/skills/production-engineering/topics/046-horizontal-scaling.md) | B |
| 47 | [Vertical Scaling](.agents/skills/production-engineering/topics/047-vertical-scaling.md) | B |
| 48 | [CDN](.agents/skills/production-engineering/topics/048-cdn.md) | B |
| 49 | [Edge Caching](.agents/skills/production-engineering/topics/049-edge-caching.md) | B |
| 50 | [Cache Invalidation](.agents/skills/production-engineering/topics/050-cache-invalidation.md) | B |
| 51 | [Feature Flags](.agents/skills/production-engineering/topics/051-feature-flags.md) | C |
| 52 | [Blue-Green Deployment](.agents/skills/production-engineering/topics/052-blue-green-deployment.md) | C |
| 53 | [Canary Releases](.agents/skills/production-engineering/topics/053-canary-releases.md) | C |
| 54 | [Rolling Deployments](.agents/skills/production-engineering/topics/054-rolling-deployments.md) | C |
| 55 | [Rollbacks](.agents/skills/production-engineering/topics/055-rollbacks.md) | C |
| 56 | [Health Checks](.agents/skills/production-engineering/topics/056-health-checks.md) | C |
| 57 | [Liveness & Readiness Probes](.agents/skills/production-engineering/topics/057-liveness-and-readiness-probes.md) | C |
| 58 | [Monitoring](.agents/skills/production-engineering/topics/058-monitoring.md) | C |
| 59 | [Logging](.agents/skills/production-engineering/topics/059-logging.md) | C |
| 60 | [Distributed Tracing](.agents/skills/production-engineering/topics/060-distributed-tracing.md) | C |
| 61 | [Metrics](.agents/skills/production-engineering/topics/061-metrics.md) | C |
| 62 | [Alerts](.agents/skills/production-engineering/topics/062-alerts.md) | C |
| 63 | [SLOs](.agents/skills/production-engineering/topics/063-slos.md) | C |
| 64 | [SLIs](.agents/skills/production-engineering/topics/064-slis.md) | C |
| 65 | [Error Budgets](.agents/skills/production-engineering/topics/065-error-budgets.md) | C |
| 66 | [Observability](.agents/skills/production-engineering/topics/066-observability.md) | C |
| 67 | [Secrets Management](.agents/skills/production-engineering/topics/067-secrets-management.md) | D |
| 68 | [IAM](.agents/skills/production-engineering/topics/068-iam.md) | D |
| 69 | [OAuth](.agents/skills/production-engineering/topics/069-oauth.md) | D |
| 70 | [JWT Rotation](.agents/skills/production-engineering/topics/070-jwt-rotation.md) | D |
| 71 | [TLS](.agents/skills/production-engineering/topics/071-tls.md) | D |
| 72 | [Encryption at Rest](.agents/skills/production-engineering/topics/072-encryption-at-rest.md) | D |
| 73 | [Encryption in Transit](.agents/skills/production-engineering/topics/073-encryption-in-transit.md) | D |
| 74 | [WAF](.agents/skills/production-engineering/topics/074-waf.md) | D |
| 75 | [DDoS Protection](.agents/skills/production-engineering/topics/075-ddos-protection.md) | D |
| 76 | [CORS](.agents/skills/production-engineering/topics/076-cors.md) | D |
| 77 | [CSRF](.agents/skills/production-engineering/topics/077-csrf.md) | D |
| 78 | [SQL Injection](.agents/skills/production-engineering/topics/078-sql-injection.md) | D |
| 79 | [XSS](.agents/skills/production-engineering/topics/079-xss.md) | D |
| 80 | [SSRF](.agents/skills/production-engineering/topics/080-ssrf.md) | D |
| 81 | [Database Migrations](.agents/skills/production-engineering/topics/081-database-migrations.md) | E |
| 82 | [Schema Versioning](.agents/skills/production-engineering/topics/082-schema-versioning.md) | E |
| 83 | [Disaster Recovery](.agents/skills/production-engineering/topics/083-disaster-recovery.md) | F |
| 84 | [Backups](.agents/skills/production-engineering/topics/084-backups.md) | F |
| 85 | [Failover](.agents/skills/production-engineering/topics/085-failover.md) | F |
| 86 | [Multi-Region Deployment](.agents/skills/production-engineering/topics/086-multi-region-deployment.md) | F |
| 87 | [Chaos Engineering](.agents/skills/production-engineering/topics/087-chaos-engineering.md) | F |
| 88 | [Cost Optimization](.agents/skills/production-engineering/topics/088-cost-optimization.md) | F |
| 89 | [Cold Starts](.agents/skills/production-engineering/topics/089-cold-starts.md) | G |
| 90 | [Serverless Limits](.agents/skills/production-engineering/topics/090-serverless-limits.md) | G |
| 91 | [Latency](.agents/skills/production-engineering/topics/091-latency.md) | G |
| 92 | [Throughput](.agents/skills/production-engineering/topics/092-throughput.md) | G |
| 93 | [P99 Latency](.agents/skills/production-engineering/topics/093-p99-latency.md) | G |
| 94 | [Tail Latency](.agents/skills/production-engineering/topics/094-tail-latency.md) | G |
| 95 | [Network Partitions](.agents/skills/production-engineering/topics/095-network-partitions.md) | H |
| 96 | [Clock Skew](.agents/skills/production-engineering/topics/096-clock-skew.md) | H |
| 97 | [DNS](.agents/skills/production-engineering/topics/097-dns.md) | H |
| 98 | [TCP vs UDP](.agents/skills/production-engineering/topics/098-tcp-vs-udp.md) | H |
| 99 | [HTTP/2 & HTTP/3](.agents/skills/production-engineering/topics/099-http-2-and-http-3.md) | H |
| 100 | [gRPC](.agents/skills/production-engineering/topics/100-grpc.md) | H |
| 101 | [Webhooks](.agents/skills/production-engineering/topics/101-webhooks.md) | H |
| 102 | [API Versioning](.agents/skills/production-engineering/topics/102-api-versioning.md) | H |
| 103 | [Semantic Versioning](.agents/skills/production-engineering/topics/103-semantic-versioning.md) | H |
| 104 | [Infrastructure as Code](.agents/skills/production-engineering/topics/104-infrastructure-as-code.md) | I |
| 105 | [Terraform](.agents/skills/production-engineering/topics/105-terraform.md) | I |
| 106 | [Helm Charts](.agents/skills/production-engineering/topics/106-helm-charts.md) | I |
| 107 | [Build Caching](.agents/skills/production-engineering/topics/107-build-caching.md) | I |
| 108 | [Dependency Hell](.agents/skills/production-engineering/topics/108-dependency-hell.md) | I |
| 109 | [Production Incidents](.agents/skills/production-engineering/topics/109-production-incidents.md) | J |
| 110 | [On-Call](.agents/skills/production-engineering/topics/110-on-call.md) | J |
| 111 | [Postmortems](.agents/skills/production-engineering/topics/111-postmortems.md) | J |

## By Category

### Category A — Backend Architecture & API Engineering (24 topics)

1 Rate Limiting, 2 Caching, 3 Load Balancing, 4 Reverse Proxies, 5 API Gateways, 6 CI/CD, 7 Docker, 8 Kubernetes, 9 Service Discovery, 10 Circuit Breakers, 11 Timeouts, 12 Retries, 13 Exponential Backoff, 14 Idempotency, 15 Message Queues, 16 Pub/Sub, 17 Event-Driven Architecture, 18 Distributed Transactions, 19 Saga Pattern, 20 Dead Letter Queues, 21 Cron Jobs, 22 WebSockets, 23 Long Polling, 24 Server-Sent Events

### Category B — Database Engineering & Distributed Systems (26 topics)

25 Database Indexing, 26 Query Optimization, 27 N+1 Queries, 28 Connection Pooling, 29 Read Replicas, 30 Sharding, 31 Partitioning, 32 Replication, 33 Leader Election, 34 CAP Theorem, 35 Eventual Consistency, 36 Optimistic Locking, 37 Pessimistic Locking, 38 Distributed Locks, 39 Race Conditions, 40 Deadlocks, 41 Memory Leaks, 42 Garbage Collection, 43 Thread Safety, 44 Backpressure, 45 Autoscaling, 46 Horizontal Scaling, 47 Vertical Scaling, 48 CDN, 49 Edge Caching, 50 Cache Invalidation

### Category C — Deployment & Production Operations (16 topics)

51 Feature Flags, 52 Blue-Green Deployment, 53 Canary Releases, 54 Rolling Deployments, 55 Rollbacks, 56 Health Checks, 57 Liveness & Readiness Probes, 58 Monitoring, 59 Logging, 60 Distributed Tracing, 61 Metrics, 62 Alerts, 63 SLOs, 64 SLIs, 65 Error Budgets, 66 Observability

### Category D — Security Engineering (14 topics)

67 Secrets Management, 68 IAM, 69 OAuth, 70 JWT Rotation, 71 TLS, 72 Encryption at Rest, 73 Encryption in Transit, 74 WAF, 75 DDoS Protection, 76 CORS, 77 CSRF, 78 SQL Injection, 79 XSS, 80 SSRF

### Category E — Database Lifecycle (2 topics)

81 Database Migrations, 82 Schema Versioning

### Category F — Disaster Recovery & Reliability (6 topics)

83 Disaster Recovery, 84 Backups, 85 Failover, 86 Multi-Region Deployment, 87 Chaos Engineering, 88 Cost Optimization

### Category G — Performance Engineering (6 topics)

89 Cold Starts, 90 Serverless Limits, 91 Latency, 92 Throughput, 93 P99 Latency, 94 Tail Latency

### Category H — Networking & Communication (9 topics)

95 Network Partitions, 96 Clock Skew, 97 DNS, 98 TCP vs UDP, 99 HTTP/2 & HTTP/3, 100 gRPC, 101 Webhooks, 102 API Versioning, 103 Semantic Versioning

### Category I — Infrastructure & Build Engineering (5 topics)

104 Infrastructure as Code, 105 Terraform, 106 Helm Charts, 107 Build Caching, 108 Dependency Hell

### Category J — Production Incident Management (3 topics)

109 Production Incidents, 110 On-Call, 111 Postmortems

## Repository Architecture

```
.agents/skills/production-engineering/
├── SKILL.md                 # activation contract: when to load, decision framework, risks
├── topics/                  # 111 topic docs, NNN-slug.md, 24 sections each
├── references/              # 15 deep references (architecture, backend, distributed, reliability,
│                            #   security, performance, observability, infrastructure, deployment,
│                            #   testing, database, networking, ai-engineering, incident-management,
│                            #   engineering-checklists)
├── workflows/               # 6 playbooks (new service, readiness, perf, incident, security, architecture)
└── templates/               # ADR, technical design doc, incident report, readiness checklist
docs/                        # installation, usage, agents, architecture, topic index, FAQ
examples/                    # fastapi skeleton, distributed system (RabbitMQ), AI agent orchestrator
scripts/                     # validate_skills.py · check_topic_coverage.py · generate_topic_index.py
tests/                       # pytest suite (structure, coverage, metadata)
.github/                     # CI (validate on push/PR), issue templates, PR template
```

## Installation

### OpenCode

```bash
# Project-local (recommended): clone, OpenCode discovers .agents/skills/ automatically
git clone https://github.com/ghanendrasahu/production-engineering.git
cd production-engineering

# Or user-global: copy the skill into your global skills directory
mkdir -p ~/.config/opencode/skills
cp -r .agents/skills/production-engineering ~/.config/opencode/skills/
```

Or register it in `opencode.jsonc` as a source root:

```jsonc
{ "$schema": "https://opencode.ai/config.json", "skills": ["~/source/production-engineering/.agents/skills"] }
```

Skill ID is `production-engineering`; invoke with `@production-engineering <task>` or let it auto-activate.

### Claude Code

```bash
git clone https://github.com/ghanendrasahu/production-engineering.git
mkdir -p ~/.claude/skills/production-engineering
cp -r production-engineering/.agents/skills/production-engineering/. ~/.claude/skills/production-engineering/
```

### Any agent / manual use

Every topic is plain Markdown at `.agents/skills/production-engineering/topics/NNN-slug.md` — paste the relevant ones into your agent's context. See [docs/installation.md](docs/installation.md) and [docs/supported-agents.md](docs/supported-agents.md).

## Usage Examples

**Design review (architecture):**

> `@production-engineering Review this design: webhooks → Kafka → 3 consumers, Postgres outbox. CRITICAL/HIGH/MEDIUM per item, and the failure modes I must test before launch.`

**Incident triage:**

> `@production-engineering 5xx rate doubled after last night's deploy. p99 went 120ms → 900ms. Give me systematic triage steps with concrete queries, fastest-first.`

**Production readiness:**

> `@production-engineering Run the production readiness checklist on this FastAPI service. What blocks ship?`

**RAG / LLM pipelines:**

> `@production-engineering Design a RAG ingestion pipeline for 50k docs/day — queue choice, idempotency, DLQ, cost controls, eval gates.`

**Performance:**

> `@production-engineering EXPLAIN ANALYZE this plan and fix the N+1. Then tell me the p99 floor I can promise.`

## Decision Framework (what makes this different)

Every recommendation is classified before it's made:

| Class | Meaning |
| --- | --- |
| **CRITICAL** | Security, correctness, availability — fix before ship |
| **HIGH** | Required for safe production use |
| **MEDIUM** | Conditional on scale/workload ("at >N RPS…") |
| **LOW** | Optional polish |
| **NOT APPLICABLE** | Unneeded — do not raise it |

Preferring the simplest architecture that meets requirements; no Kubernetes/Kafka/Redis "just in case"; no caching without invalidation; no retries without idempotency; no locks without TTL + fencing. The skill exists to make agents say **less but better**.

## Contributing

Contributions welcome — from first-PR documentation fixes to new topic proposals.

```bash
git clone https://github.com/ghanendrasahu/production-engineering.git
cd production-engineering
python -m pip install pytest
python scripts/check_topic_coverage.py    # 111/111 expected
python scripts/validate_skills.py         # 0 problems expected
pytest tests/ -q                          # all green expected
```

See [CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [SUPPORT.md](SUPPORT.md) · issue templates · [discussions](https://github.com/ghanendrasahu/production-engineering/discussions).

## Roadmap

See [GitHub Milestones](https://github.com/ghanendrasahu/production-engineering/milestones) and the [Discussions](https://github.com/ghanendrasahu/production-engineering/discussions) planning threads. High level:

- **v1.0.0** — 111 topics, CI validation, OpenCode/Claude Code support (current)
- **v1.1** — AI-agent integration tests (agent-in-the-loop resolution benchmarks), per-topic "failure story" case studies
- **v1.2** — Example app expansion (Java/Go/Node ports), framework-specific expansions (Next.js, Django, Spring)
- **v1.3** — Localization (topics in German, Hindi, Portuguese, Spanish), video walkthroughs
- **v2.0** — 112+ topics via proposal process (deepened LLM evals, ML platform ops), official catalog listing

## Version & Changelog

Current: **v1.0.0** — see [CHANGELOG.md](CHANGELOG.md) and [releases](https://github.com/ghanendrasahu/production-engineering/releases).

## License

[MIT](LICENSE) — © 2026 Ghanendra Sahu. Use it, fork it, ship with it, teach with it.

## Acknowledgements

- The **SRE book and workbook** (Google) — the source of the SLO/error-budget framing.
- **Anthropic** — skill format and agent integration conventions this library targets.
- **The PostgreSQL, RabbitMQ, Kubernetes, Prometheus, OpenTelemetry, and Apache Kafka communities** — the machinery these topics describe.
- **OWASP** — the security content in this library stands on the OWASP corpus.
- Everyone who issues feedback, PRs, and correction notices — this library gets better because you do.

## Maintainer

**Ghanendra Sahu** — [github.com/ghanendrasahu](https://github.com/ghanendrasahu).
Communication: [GitHub Discussions](https://github.com/ghanendrasahu/production-engineering/discussions) and [Issues](https://github.com/ghanendrasahu/production-engineering/issues). Security matters: [SECURITY.md](SECURITY.md).

Please don't send private messages for support — public channels keep answers useful for everyone.
