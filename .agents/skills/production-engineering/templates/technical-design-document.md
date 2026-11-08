---
name: technical-design-document
title: Technical Design Document
---

# TDD: <system or change>

**Author(s):** · **Status:** draft | in-review | approved | implemented · **Date:** YYYY-MM-DD · **Related ADR(s):**

## 1. Problem & Goals

What problem, for whom. Functional goals (numbered). Explicit **non-goals**.

## 2. Requirements

**Functional:** list. **Non-functional (numbers!):** traffic (steady/peak RPS), payload sizes, read/write ratio, latency targets (p50/p95/p99), availability (RPO/RTO), consistency model per entity, data growth/year, retention/compliance, cost ceiling.

## 3. High-Level Design

Diagram (ASCII or link). Components and their responsibilities. Request path AND failure path (dependency down/slow/lying). Sync vs async boundaries; ownership of each interface.

## 4. Data Model & Migrations

Tables/collections, keys, constraints, indexes (top queries), migration plan (expand/contract steps, backfill strategy, rollback). Data lifecycle: retention, erasure, archival.

## 5. API Contracts

Endpoints/methods/schemas with example payloads; error shapes; versioning strategy (`#102`); idempotency for mutations (`#14`); pagination (keyset).

## 6. Consistency, Concurrency & Idempotency

Per-entity consistency model; locking strategy (optimistic vs pessimistic vs atomic SQL); single-writer paths; idempotency keys; duplicate-safe consumers.

## 7. Reliability & Failure Design

Timeouts table (per hop), retries+backoff policy, circuit breakers + fallbacks, degraded modes, queue overflow policy, DLQs, DR/failover relationship.

## 8. Scalability & Capacity

Saturation analysis per stage; queue depth/conn budgets; autoscaling (on what metric); 3x and 10x headroom actions pre-agreed; bottlenecks and their pre-bought fixes.

## 9. Security & Privacy

Trust boundaries; authN/Z model; secrets handling; data classification; PII handling; injection/SSRF surfaces; rate limits; audit logging; compliance notes.

## 10. Observability

SLIs per journey, SLO, error-budget policy; metrics list; logs (trace_id), traces; dashboards to build; alerts (actionable, with runbooks); deploy annotation on dashboards.

## 11. Rollout Plan

Canary/blue-green/flags; migration order; backward compat window; smoke tests; rollback steps < 5 minutes; monitoring during ramp; go/no-go criteria.

## 12. Cost Estimate

Infra at current and 10x: $ / month (LLM token spend if any, separately). Biggest lever identified.

## 13. Risks & Open Questions

Numbered risks with severity + mitigation; open questions with owners and dates.

## 14. Verification

How we prove it works: test plan, load test targets, chaos/failure drills, SLO sign-off at 30 days, rollback drill.

## Review

Reviewers: ___ · Verdict: APPROVE / CONDITIONS (list) · Date: ___
