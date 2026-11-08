---
topic: 7
title: Docker
category: A
skill: production-engineering
status: stable
---

# 007 — Docker

## 1. Topic name and metadata

- **Number:** 7 of 111
- **Title:** Docker
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [devops-infrastructure.md](../references/infrastructure.md)
- **Topic file:** `.agents/skills/production-engineering/topics/007-docker.md`

## 2. What it is

A packaging format and runtime for applications + dependencies as immutable, layered images that run identically on laptop, CI, and production.

## 3. Why it exists

Works on my machine' is not a deployment strategy.

## 4. The engineering problem it solves

"Works on my machine"; snowflake servers; unreproducible builds; unmanaged dependencies; deployment drift.

## 5. How it works internally

Image = ordered layers (each Dockerfile instruction = read-only diff layer; content-addressed by hash; shared cache). Union filesystem (overlay2) merges layers; container = layered image + writable top layer + isolated namespaces (pid/net/mnt/uts) + cgroups limits. Build context sent to daemon; multi-stage builds separate build deps from runtime; copy lockfiles first for cache; .dockerignore excludes junk. Registry stores images; tags mutable (use digests for immutability).

## 6. Architecture and design principles

Base image layered filesystem -> registry -> node runtime -> orchestrator. The image is the unit CI builds and K8s schedules; multi-stage builds split build deps from the runtime artifact.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Always — every deployable.

## 8. When NOT to use it

Truly trivial single-binary scripts deployed via scp (rare now).

**Alternatives:** VM images (AMI — coarser), Nix, buildpacks (heroku) for convenience.

## 9. Implementation strategies

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY src ./src

FROM python:3.12-slim
WORKDIR /app
RUN useradd -r app && mkdir -p /app
COPY --from=builder /app /app
USER app
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Compose for dev: `services: api: build: ., depends_on: [db, redis]`; healthchecks in compose.

## 10. Production-grade implementation

**Scenario:** API image 140MB (slim + uv + multi-stage, was 1.2GB); build 45s (cache hit); runs as non-root UID 10001; read-only rootfs in K8s; digest-pinned deploy (`image@sha256:…`); CVE scan gate in CI (trivy) blocks on critical.

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

Model images ship as containers with digest-pinned bases; scan for CVEs; never bake provider keys; mount secrets at runtime.

## 15. Security considerations

Image layers are forever — no secrets in Dockerfiles; non-root USER; scan base images.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Fat images; `docker run --privileged` in prod; `.env` baked; root user; `apt-get update && install` in one layer (cache-hostile); "latest" everywhere; building on laptop for prod; running DBs in the same container as app.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `image_scan_findings`, `build_duration_seconds`, registry pull errors

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Build in CI; smoke-run the image then hit /healthz; trivy gate; digest deploy verification; non-root assertion; docker-compose integration for dev parity (testcontainers in pytest).

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Multi-stage builds
- [ ] Non-root USER
- [ ] Slim/distroless bases
- [ ] Digest pinning
- [ ] .dockerignore
- [ ] Scan images (trivy) in CI
- [ ] Lockfiles copied before source
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Root containers; secrets baked via `COPY .env` (history shows it forever); cache misses (copy src before deps) — rebuild everything; giant images (apt lists, docs); :latest tags (untraceable); no .dockerignore (node_modules 800MB context); rootfs writable + curl exfiltration; missing healthcheck → orchestrator blind; zombie reaping (no init/tini for signals in N+1 signal handling — use tini or K8s handles SIGTERM directly).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.docker.com/build/buildkit/
- https://docs.docker.com/engine/userguide/best-practices/

**Related topics in this library:** `#8 Kubernetes`, `#6 CI/CD`, `#106 Helm Charts`, `#107 Build Caching`, `#67 Secrets Management` (never in images), `#104 Infrastructure as Code`.
