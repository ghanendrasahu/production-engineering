---
topic: 3
title: Load Balancing
category: A
skill: production-engineering
status: stable
---

# 003 — Load Balancing

## 1. Topic name and metadata

- **Number:** 3 of 111
- **Title:** Load Balancing
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/003-load-balancing.md`

## 2. What it is

Distributing incoming connections or requests across multiple backend instances so no single instance is overwhelmed and failed instances stop receiving traffic.

## 3. Why it exists

No single instance can absorb all traffic or hide its own failure.

## 4. The engineering problem it solves

A single instance caps throughput and is a single point of failure; uneven load wastes capacity and causes tail-latency spikes even when averages look fine.

## 5. How it works internally

Algorithms — round robin (equal), weighted round robin (heterogeneous capacity), least-connections (sends to the least busy), IP hash/consistent hashing (session stickiness), random (surprisingly competitive at scale). L4 balancers forward TCP/UDP flows (fast, no content awareness); L7 balancers terminate HTTP/gRPC (route on path/headers, health-check semantically, inject headers). Health checks mark backends up/down; outlier detection ejects flapping instances.

## 6. Architecture and design principles

Edge LB (cloud ELB/NLB) → app replicas behind an L7 proxy (Nginx/Envoy/Traefik) → service instances → database with its own pool. Health check path (`/healthz`) informs the LB.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

More than one replica (always in production), blue-green/canary traffic splitting, heterogeneous backends.

## 8. When NOT to use it

Single local dev instance; sessions in-process without externalization (fix the app, not the LB).

**Alternatives:** client-side load balancing (gRPC), DNS round-robin, service mesh (Envoy/Istio).

## 9. Implementation strategies

Nginx `upstream { least_conn; server a:8000 max_fails=3 fail_timeout=30s; keepalive 64; }`; Kubernetes `Service` (kube-proxy iptables/IPVS, round-robin per connection); cloud ALB for gRPC/HTTP with target groups and 30s health checks.

```nginx
upstream api { least_conn;
  server 10.0.1.11:8000 max_fails=3 fail_timeout=30s;
  server 10.0.1.12:8000 max_fails=3 fail_timeout=30s;
  keepalive 64; }
server { location / { proxy_pass http://api; } }
```

## 10. Production-grade implementation

**Scenario:** 4 FastAPI replicas behind an ALB, least-connections, target-tracking health checks every 10s, 2 consecutive failures → deregister. p99 dropped from 800ms to 180ms after switching from round robin to least-connections because two replicas were slower (GC pauses) and kept accumulating connections.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

None — load balancing is infrastructure; verify from the app with `httpx.AsyncClient` against the VIP and observe connection reuse.

## 12. FastAPI integration where relevant

Run behind `uvicorn --workers N` (per-machine, not a substitute for LB) or gunicorn `-k uvicorn.workers.UvicornWorker`; rely on the LB for cross-instance balancing; keep `/healthz` cheap (no DB hit) and `/readyz` for dependency checks.

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

LLM fleets scale behind LBs; stickiness hurts batching (vLLM) — least-connections and L7 routing preferred; health-check = model-loaded, not just TCP.

## 15. Security considerations

Load balancers are the first DDoS line — enable L3/L4 protections at the edge.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Single LB instance without redundancy; no health checks (routing to dead nodes); least-connections on L4 TCP with cookie-based stickiness semantics confused; health check = full DB query; weights set once and forgotten.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `upstream_requests_total`, `backend_health` (LB), `connections_active`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Kill a replica and confirm no 5xx (health check removal time); load test verifying even p95 across backends; verify keepalive reuse with `tcpdump` or access logs; failure injection via toxiproxy for flaky-backend behavior.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Least-connections for long-lived or variable-cost requests
- [ ] Dumb fast L4 for gRPC streams when L7 not needed
- [ ] Health checks must test real readiness (but not hard dependencies)
- [ ] Set `max_fails`/`fail_timeout`
- [ ] Enable connection keepalive to backends
- [ ] Multi-AZ
- [ ] Monitor per-backend request rate and error rate.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Sticky sessions via IP hash pinning users to a dying replica; health check endpoint that touches the DB → every replica goes "down" together during a DB blip and traffic collapses to zero; `keepalive` too low causing TIME_WAIT exhaustion; uneven weight config after a canary deploy; LB itself a SPOF (use multi-AZ LB).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://nginx.org/en/docs/http/ngx_http_upstream_module.html
- https://docs.aws.amazon.com/elasticloadbalancing/

**Related topics in this library:** `#4 Reverse Proxies`, `#45 Autoscaling`, `#46 Horizontal Scaling`, `#56 Health Checks`, `#85 Failover`, `#9 Service Discovery`.
