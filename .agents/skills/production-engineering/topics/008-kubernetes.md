---
topic: 8
title: Kubernetes
category: A
skill: production-engineering
status: stable
---

# 008 — Kubernetes

## 1. Topic name and metadata

- **Number:** 8 of 111
- **Title:** Kubernetes
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [devops-infrastructure.md](../references/infrastructure.md)
- **Topic file:** `.agents/skills/production-engineering/topics/008-kubernetes.md`

## 2. What it is

A declarative container-orchestration platform: you describe desired state (Deployments, Services, ConfigMaps) and controllers continuously reconcile reality toward it.

## 3. Why it exists

You cannot operate a fleet by hand once hosts stop being pets.

## 4. The engineering problem it solves

Managing dozens/hundreds of containers by hand — scheduling, health, scaling, rollouts, service discovery — is untenable; K8s automates the control loop.

## 5. How it works internally

Control plane (API server, etcd, scheduler, controller-manager) + nodes (kubelet, kube-proxy, container runtime). You apply YAML; controllers reconcile: ReplicaSet maintains replica count; readiness/liveness probes gate traffic; Services give stable virtual IPs (ClusterIP) with EndpointSlices; HPA scales; Jobs/CronJobs run batch; namespaces isolate; RBAC/PSA secure; admission webhooks intercept config. Desired-state reconciliation means partial failure self-heals (node dies → pods rescheduled).

## 6. Architecture and design principles

Control plane (API server/etcd/scheduler/controllers) + worker nodes; you apply desired-state YAML, controllers reconcile; Services/EndpointSlices handle discovery; HPA and probes close the feedback loop.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Multiple services, team size to operate, or managed K8s (EKS/GKE/AKS) with platform support.

## 8. When NOT to use it

One small app, one VM — Docker Compose or FaaS is correct (`agent` anti-enterprise-complexity rule).

**Alternatives:** Docker Compose, Nomad, ECS, FaaS, fly.io, PaaS (Render/Heroku).

## 9. Implementation strategies

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: api }
spec:
  replicas: 4
  strategy: { type: RollingUpdate, rollingUpdate: { maxSurge: 1, maxUnavailable: 0 } }
  selector: { matchLabels: { app: api } }
  template:
    metadata: { labels: { app: api } }
    spec:
      containers:
        - name: api
          image: registry.example.com/api@sha256:abc
          ports: [{ containerPort: 8000 }]
          resources: { requests: { cpu: 250m, memory: 256Mi }, limits: { memory: 512Mi } }
          startupProbe: { httpGet: { path: /healthz, port: 8000 }, failureThreshold: 30, periodSeconds: 5 }
          readinessProbe: { httpGet: { path: /readyz, port: 8000 }, periodSeconds: 5 }
          livenessProbe:  { httpGet: { path: /healthz, port: 8000 }, periodSeconds: 10 }
---
apiVersion: v1
kind: Service
metadata: { name: api-svc }
spec: { selector: { app: api }, ports: [{ port: 80, targetPort: 8000 }] }
```

## 10. Production-grade implementation

**Scenario:** 12-service SaaS on EKS: HPA (CPU+custom metric lag) 2→30 pods; zero-downtime rolls with preStop drain + readiness; pod disruption budgets (minAvailable 60%); namespace RBAC; external-dns; cert-manager; 2 years without a hand-touched node.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (inline in section 9)

This concept has no standalone Python surface — its artifacts are configuration,
templates, or pipeline steps. All runnable material for it lives inline in **section 9 (Implementation strategies)** and **section 12 (FastAPI integration)** where applicable. Do not force a toy example here.

## 12. FastAPI integration where relevant

Not applicable — this concept is infrastructure/protocol level; there is no FastAPI-specific surface. Apply it underneath FastAPI through configuration, middleware, or dependencies (section 9). Do not force a fake integration.

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

GPU node pools (taints + nodeSelector `nvidia.com/gpu`), HPA on queue depth/GPU-util via KEDA, PDB on inference Deployments, readiness = model warm.

## 15. Security considerations

K8s RBAC + PSA restricted; no secrets in manifests; etcd at rest encrypted.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Pets-as-cattle failure (SSH into pods to fix); monolith in one giant pod; `kubectl exec` as deployment strategy; no PDB; `:latest`; skipping staging parity; single-node "K8s" sold as prod.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `kube_pod_container_restarts_total`, node pressure, `probe_failures`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Kindest/kind dry-run; staging cluster parity; rollout drill (`rollout undo`); chaos (node kill); quota enforcement test; policy tests (conftest/kyverno).

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Requests+limits always (Guaranteed QoS for critical)
- [ ] Probes trio
- [ ] Digests not tags
- [ ] PDB
- [ ] Namespaces + RBAC + PSA restricted
- [ ] GitOps (ArgoCD/Flux) — no ad-hoc applies
- [ ] Resource quotas
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Resource requests unset → scheduler blind → OOM kills/noisy neighbors; liveness with DB check → restart cascades (see `#57`); image `:latest` (no traceability); no resource limits → node pressure; ConfigMap updated but pods not restarted (checksum annotation pattern); etcd backup never tested; single control-plane cluster (control plane outage = no deploys/reschedules but workloads keep running — learn this distinction); HPA flapping at threshold (enable stabilization windows); kubectl apply from laptops in prod.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kubernetes.io/docs/
- https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

**Related topics in this library:** `#7 Docker`, `#106 Helm Charts`, `#104 Infrastructure as Code`, `#57 Liveness & Readiness Probes`, `#9 Service Discovery`, `#45 Autoscaling`, `#58 Monitoring`.
