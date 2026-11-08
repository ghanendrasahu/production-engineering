# Workflow — New Production Service

Use this playbook from empty repo to first production deploy. Adapt steps, keep the gates.

## Step 1 — Requirements (30 minutes, do not skip)

Write down, in order:
1. **User stories** — who calls it, for what, how often.
2. **Traffic shape** — steady RPS, burst factor, payload sizes, read/write ratio, data growth/year.
3. **Data & consistency** — what's strongly consistent (money, inventory, authz) vs eventually consistent (feeds, profiles, search).
4. **Reliability** — RPO/RTO targets, SLO candidate, who is on-call for it.
5. **Security & compliance** — PII? PCI? residency? auth model (SSO/JWT/API keys)?

If you can't answer 1-5, the architecture doesn't exist yet.

## Step 2 — Architecture Sketch

Pick from existing blocks (do not invent): FastAPI or framework at the core; Postgres (managed) for the system of record; Redis for cache/locks; a queue (Celery/Arq + RabbitMQ/SQS) for anything > the HTTP budget; K8s/Docker-Compose deploy; Nginx/ingress edge; GitHub Actions CI.

Classify each candidate concept CRITICAL/HIGH/MEDIUM/NOT APPLICABLE (see SKILL.md decision table). Record in an ADR (`../templates/architecture-decision-record.md`): why this shape, what you rejected, verification plan.

## Step 3 — Contracts Before Code

- OpenAPI spec (or protobuf for gRPC) written first; breaking changes = new version (`#102`).
- Data models: tables, keys, constraints, indexes for the top 3 queries; migrations via Alembic.
- Event schemas (if any) with versioning; DLQ defined for every consumer.

## Step 4 — Skeleton (boring on purpose)

From `../examples/fastapi/`: app factory + lifespan, `/healthz` + `/readyz`, structlog with trace_id, prometheus `/metrics`, pydantic-settings config, DB engine with pool_pre_ping, session-per-request dependency, error model.

## Step 5 — The Six Non-Negotiables (gate every PR)

1. Timeouts on every outbound call · 2. Retries: bounded, jittered, only where idempotent · 3. Bounded resources (queues, pools, payloads, batch sizes) · 4. Health + readiness probes · 5. Structured redacted logs with trace_id · 6. Tests incl. one failure path.

## Step 6 — Deploy

Build once (digest tag) → CI runs gates (see `references/testing.md`) → staging → smoke → **canary 5% / bake / ramp** with auto-rollback on error-budget burn → on-call assigned (`#110`). Rollback rehearsed before go-live.

## Step 7 — Go-Live Checklist

Dashboards for latency/errors/saturation, alerts (actionable only, with runbooks), SLO + error-budget policy agreed with product, runbook links in the service catalog, postmortem template pre-filled, CHANGELOG updated, `v1.0.0` tagged.

## Sizing Guidance

- <500 RPS, single region, small team: modular monolith + Compose/VM is enough — do NOT add K8s/Kafka.
- 500-5k RPS or heavy reads: add cache + read replicas; revisit shapes at 3x growth.
- 5k+ RPS or strict multi-region: K8s, autoscaling (queue-depth), multi-AZ minimum.
