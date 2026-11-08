---
topic: 9
title: Service Discovery
category: A
skill: production-engineering
status: stable
---

# 009 — Service Discovery

## 1. Topic name and metadata

- **Number:** 9 of 111
- **Title:** Service Discovery
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/009-service-discovery.md`

## 2. What it is

The mechanism by which services locate the network addresses of their dependencies dynamically, so instances can come and go without static configuration.

## 3. Why it exists

Hardcoded addresses break every deploy and every failover.

## 4. The engineering problem it solves

Hardcoded IPs/hostnames break deployments, autoscaling, failover, and blue-green rollouts; manual address management causes 100% outages when an instance dies and traffic still routes to it.

## 5. How it works internally

Client-side discovery (client queries registry — Consul/Eureka/etcd — and load-balances itself) vs server-side discovery (LB/router queries the registry or K8s Services route via iptables/IPVS DNAT to pod IPs). Registrations happen on startup with TTL/heartbeat leases (Consul session TTL, K8s readiness gates); deregistration is automatic on health failure. DNS is the universal baseline (SRV/A records, e.g. `headless` Services in K8s); watches (etcd watch/Consul blocking queries) push updates instead of polling.

## 6. Architecture and design principles

Service A → resolver/registry (K8s API, Consul, etcd) → healthy instances of Service B. In K8s this is free: `ClusterIP` + `Service` + probe-driven endpoint removal from EndpointSlices.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Any environment with ephemeral instances (K8s, autoscaling, containers) — i.e., always outside static VMs.

## 8. When NOT to use it

A single-host monolith; stable VM fleet without containers (static config acceptable).

**Alternatives:** DNS (K8s headless), K8s Gateway API, cloud service maps, Consul Connect/mesh.

## 9. Implementation strategies

Kubernetes: create `Service` + Deployment; use `http://users-svc.payments.svc.cluster.local:8000`; headless service for direct pod discovery (gRPC client-side LB). Consul: `consul agent -dev`, services registered via annotations/config, `consul.watch` in clients. etcd: lease + keepalive, `Watch` on prefix for endpoints. Application must gracefully deregister on shutdown (drain + SIGTERM hook).

## 10. Production-grade implementation

**Scenario:** Blue-green deploy of the `orders` service: new pods pass readiness → EndpointSlice adds IPs → all proxies receive endpoints within seconds; old pods deregister and connections drain via preStop hook + termination grace. Zero hardcoded addresses anywhere.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

```python
import httpx
async def call_users_service(path: str):
    # K8s DNS round-robin; refresh connections so pod changes are picked up
    async with httpx.AsyncClient(timeout=2.0, limits=httpx.Limits(max_keepalive_connections=20)) as c:
        return await c.get(f"http://users-svc.prod.svc.cluster.local:8000{path}")
```

## 12. FastAPI integration where relevant

Read peer URLs from env (`USERS_SVC_URL=http://users-svc:8000`) injected by the platform — K8s DNS resolves at connect time; do not resolve once and cache forever; for gRPC use `dns:///` targets.

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Model registry + service discovery: routes resolve to healthy inference pods; client-side LB (gRPC) suits long-lived streaming connections.

## 15. Security considerations

Registry/lease tokens are bearer credentials — store fenced, protect registration endpoints.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Static IPs in config; discovery without health filtering; heartbeat intervals >> MTTR requirements; custom registry built in-house before evaluating K8s/Consul; discovery lookups on the hot path without caching (N+1 network calls).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `registry_endpoints_current`, `lease_expirations_total`, resolution errors

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

`dig SRV users-svc...` lists only ready pods; kill a pod mid-traffic and confirm no client errors after deregistration; registry-failure test (stop Consul) verifying cached fallback and alert; rollout drill measuring time-to-100%-routing.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Let the platform do discovery (K8s Services) before building your own
- [ ] Deregister on SIGTERM (preStop sleep + grace period)
- [ ] Keep TTLs small with lease renewal
- [ ] Health checks orthogonal to discovery
- [ ] Client-side: shuffle endpoints
- [ ] Export resolution latency/errors
- [ ] Document the registry as a critical dependency and test its failure mode.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Consul agent dies → stale views and split-brain membership; readiness probe too shallow (TCP-only) keeps routing to broken pods; DNS TTL too high caches dead endpoints; client caches registry snapshot without refresh; simultaneous all-replicas deregister during a full rollout → 503 storm; `headless` service used by a non-LB client → all traffic to one pod.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://developer.hashicorp.com/consul/docs
- https://kubernetes.io/docs/concepts/services-networking/service/

**Related topics in this library:** `#3 Load Balancing`, `#45 Autoscaling`, `#56 Health Checks`, `#57 Liveness & Readiness Probes`, `#8 Kubernetes`, `#85 Failover`.
