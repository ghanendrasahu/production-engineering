---
topic: 19
title: Saga Pattern
category: A
skill: production-engineering
status: stable
---

# 019 — Saga Pattern

## 1. Topic name and metadata

- **Number:** 19 of 111
- **Title:** Saga Pattern
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [messaging-event-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/019-saga-pattern.md`

## 2. What it is

An implementation of a distributed transaction as a sequence of local transactions, each publishing an event/message, with compensating actions defined for each step to undo prior steps on failure.

## 3. Why it exists

Long-running cross-service work needs compensation, not forever-locks.

## 4. The engineering problem it solves

Cross-service workflows (multi-minute, with human waiting) cannot hold row locks or 2PC barriers; without compensation, partial multi-service writes strand inconsistent state that nobody notices until customers complain.

## 5. How it works internally

Two styles — **choreography**: each service listens for an event and emits the next; no coordinator; flows emerge; good for short chains. **Orchestration**: a coordinator (Temporal, Step Functions, or a state table in Postgres with a worker) issues commands, waits for replies/timeouts, decides next or compensate; explicit, observable, easy to add a step. Each step: idempotency key, timeout, retry with cap, compensation action. States: started → step_k done → completed | compensating → compensated | failed (needs human). Semantic locks (reservation with TTL) prevent oversell during the saga.

## 6. Architecture and design principles

Orchestrator + participant services; durable saga log (workflow history or DB rows) survives crashes, so a restarted worker resumes the saga rather than losing it.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Multi-service write flows spanning seconds to minutes where partial completion is unacceptable (money, inventory, provisioning).

## 8. When NOT to use it

Single-database transaction suffices (always prefer); flow fits an event fanout with independent consumers and no need for all-or-nothing (choreography/EDA is simpler); team lacks durable-execution tooling or discipline.

**Alternatives:** 2PC (rarely), saga via Temporal/Step Functions, synchronous orchestration with generous timeouts, accept-and-reconcile weekly job.

## 9. Implementation strategies

```sql
CREATE TABLE sagas (id uuid PRIMARY KEY, type text, state jsonb NOT NULL, status text NOT NULL DEFAULT 'started',
                    created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now());
```

```python
# Pseudocode — each step: call, then persist progress atomically
def run_booking_saga(booking_id):
    saga = start_saga("booking", booking_id)
    try:
        reserve_seat(idempotency_key=f"{saga.id}:reserve")     # step 1
        advance(saga, "reserved")
        charge_card(idempotency_key=f"{saga.id}:charge")      # step 2
        advance(saga, "charged")
        issue_ticket(idempotency_key=f"{saga.id}:ticket")     # step 3
        complete(saga)
    except StepFailed as e:
        compensate(saga, completed_steps)   # refund, release — in reverse order
        mark_failed(saga, e)
```

With Temporal: `@workflow.defn` with activities + automatic retries + compensation code — the platform persists history, so worker crashes resume the workflow.

## 10. Production-grade implementation

**Scenario:** Marketplace order saga (inventory → payment → shipment → notification), ~6k sagas/day, 0.3% enter compensation; compensations automated (release + auto-refund), 3/month escalated to on-call for refund API failures; average saga completion 800ms, p99 4s (payment gateway tail).

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

`POST /book` writes saga row (status=started) and enqueues the saga runner; returns `202 + saga_id`; `GET /book/{saga_id}` polls status; UI subscribes via SSE for long-running sagas (#24).

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Long-running agents (minutes-hours) = saga executions: journaled steps, idempotent tools, compensation on failure, human-in-the-loop checkpoints via signals.

## 15. Security considerations

Saga state contains business data — same protections as the OLTP database.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Saga with steps that cannot be compensated (email already sent — make it a final irreversible step with explicit acknowledgment); no timeout on a step call (saga waits forever); compensations that are best-effort without alerting; state in process memory; compensating before all participants are known; using a saga when a single DB transaction would do.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `saga_step_duration_seconds`, failed compensation alerts

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest for each step and each compensation path; crash between steps (subprocess kill mid-saga) and assert resume; duplicated delivery to compensation → exactly one refund; end-to-end staging booking including forced failures; assert no reserved-seat leak after 1000 failing sagas; chaos test with dependency outage.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Prefer orchestration for >2 steps
- [ ] Idempotency keys derived from saga_id per step
- [ ] Every step has a defined compensation or is declared irreversible
- [ ] Store saga state durably (DB/workflow engine), not memory
- [ ] Alert on sagas stuck > 10min
- [ ] Reconciliation job sweeping stale sagas
- [ ] Human escalation path for failed compensations
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Orchestrator stopped (worker down) → sagas stall at a step; must have lag monitoring + dead-man's switch; compensation fails permanently (refund API down > 72h) → human runbook; participant not idempotent → double-charge on retry; timeout too tight → sagas compensate healthy slow steps; choreography chain edits without registry → events nothing consumes; TTL semantic lock expiry mid-saga → oversell; saga table bloat (no archival).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://learn.microsoft.com/azure/architecture/patterns/saga
- https://temporal.io/blog

**Related topics in this library:** `#18 Distributed Transactions`, `#17 Event-Driven Architecture`, `#14 Idempotency`, `#15 Message Queues`, `#20 Dead Letter Queues`, `#24 Server-Sent Events` (status streaming), `#109 Production Incidents`.
