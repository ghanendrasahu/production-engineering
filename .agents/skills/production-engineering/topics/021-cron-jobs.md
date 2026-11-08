---
topic: 21
title: Cron Jobs
category: A
skill: production-engineering
status: stable
---

# 021 — Cron Jobs

## 1. Topic name and metadata

- **Number:** 21 of 111
- **Title:** Cron Jobs
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/021-cron-jobs.md`

## 2. What it is

Time-scheduled execution of jobs (a crontab entry or platform scheduler) that run periodic tasks such as reports, cleanups, reconciliations, and cache warming.

## 3. Why it exists

Recurring work must be scheduled, bounded, and observable — not manual.

## 4. The engineering problem it solves

Recurring maintenance is inevitable; done ad hoc by hand it is forgotten, duplicated across hosts, or run twice concurrently — corrupting data or double-charging.

## 5. How it works internally

Unix cron evaluates `minute hour day month weekday command` with local time and `PATH`; no leader election, no retries, no overlap protection. Platform schedulers (K8s CronJob with `concurrencyPolicy: Forbid|Replace` and `startingDeadlineSeconds`, AWS EventBridge, Celery beat, Airflow) add history, dedup, retries, and observability. Missed schedules depend on `startingDeadlineSeconds`; overlap is the most common production bug — two runs mutate the same state.

## 6. Architecture and design principles

Scheduler triggers a job container/worker that runs a short, idempotent unit; heavy work enqueued onto a queue; results/metrics reported; alerts on failures or missed runs (heartbeat).

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Periodic batch/maintenance/maintenance tasks, reconciliation, cleanup, report generation.

## 8. When NOT to use it

Work must react to events (use `#15 Message Queues`/`#16 Pub/Sub`); sub-minute precision needed (use a streaming loop); single user-triggered actions (use an endpoint).

**Alternatives:** message triggers, workflow engines (Airflow/Temporal), event-driven handlers.

<!--END-->

## 9. Implementation strategies

```yaml
# Kubernetes CronJob
apiVersion: batch/v1
kind: CronJob
metadata: {name: nightly-close}
spec:
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid          # never overlap
  startingDeadlineSeconds: 600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      template: {spec: {restartPolicy: Never, containers: [{name: run, image: registry/app:1.2.3, command: ["python","-m","jobs.close"]}]}}
```

For app-embedded loops use Celery beat or APScheduler with a Redis lock (`SET lock:job:nightly-close NX`) to guarantee single execution.

## 10. Production-grade implementation

**Scenario:** Nightly invoice reconciliation (02:00, ~8 min): K8s CronJob Forbid-concurrency, job acquires Redis leader lock, writes results to `recon_runs` table with status; heartbeat dead-man's switch pings healthchecks.io; failure → alert to on-call with the run ID; reruns are idempotent by `(date, run_id)` upsert keys.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

```python
import redis
r = redis.Redis()
lock = r.set("lock:job:nightly-close", "1", nx=True, ex=3600)
if lock:
    try:
        reconcile_daily_billing()
    finally:
        r.delete("lock:job:nightly-close")
else:
    sys.exit(0)  # another instance is running; do not overlap
```

## 12. FastAPI integration where relevant

Rarely inside the API process — instead an endpoint `POST /jobs/nightly-close` that is not publicly routable (internal listener only) and that enqueues work; admins can trigger via authenticated call. Better: exit API entirely, use K8s CronJob.

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Nightly eval runs, index rebuilds, and cost rollups: K8s CronJob with Forbid concurrency + dead-man's-switch alerting (healthchecks.io style).

## 15. Security considerations

Cron credentials are broad — least-privilege roles; audit job actions.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

`cron` on a single VM that gets decommissioned; job doing heavy work inline in a 30-second loop every minute; no monitoring ("it ran yesterday"); partial failures committed without a transaction; wall-clock-naive scripts; shared mutable state with no lock.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `job_last_success_timestamp`, `job_duration_seconds`, overdue-jobs gauge

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest the job function directly with a fixed logical clock; dry-run flag against a staging DB; assert Forbid/lock behavior by triggering twice concurrently; dead-man's-switch test by disabling the job; verify `recon_runs` uniqueness after rerun.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Idempotent, re-runnable jobs keyed by logical date
- [ ] Single execution via Forbid or distributed lock
- [ ] Dead-man's-switch monitoring (alert on silence, not only errors)
- [ ] Structured logs + duration metrics
- [ ] Jobs enqueue rather than compute inline
- [ ] Uniqueness keys derived from schedule date
- [ ] Document what a manual rerun means for data.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Job runs twice on two replicas (no lock/forbid) → double charges; job silently fails for 3 weeks (no monitoring) → stale data; job held by a hung process for hours while next schedule fires anyway (Forbid absent) → overlap deadlock; job duration > interval → perpetual lag; timezone confusion (server local vs UTC) → reports at wrong hour; missing deadline → missed run never executes (startingDeadlineSeconds too small).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/

**Related topics in this library:** `#14 Idempotency`, `#38 Distributed Locks`, `#56 Health Checks`, `#62 Alerts`, `#21 Cron Jobs` pairs with `#15 Message Queues` for fan-out, and with `#84 Backups`.
