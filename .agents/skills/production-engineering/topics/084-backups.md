---
topic: 84
title: Backups
category: F
skill: production-engineering
status: stable
---

# 084 — Backups

## 1. Topic name and metadata

- **Number:** 84 of 111
- **Title:** Backups
- **Category:** F — Disaster Recovery and Reliability
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [reliability-recovery.md](../references/reliability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/084-backups.md`

## 2. What it is

Time-stamped, recoverable copies of data at multiple points, protected from the same failures that threaten the primary, with verified restore capability.

## 3. Why it exists

Durable state needs recoverable, independent copies.

## 4. The engineering problem it solves

Disk failure, ransomware, fat-fingered DELETE, and bad migrations — all unrecoverable without backups that are (a) independent, (b) recent, (c) tested.

## 5. How it works internally

RPO vs cost curve. Types: full/incremental/differential (incremental chains need all links), continuous WAL archiving for Postgres (PITR to any second), VSS/snapshots coordinated with app quiescence (flush buffers; pg_start_backup). 3-2-1 rule: 3 copies, 2 media, 1 offsite. Immutability: object-lock/WORM storage against ransomware deletion; backups encrypted (`#72`); retention policy (daily 30d, monthly 12mo) and deletion hygiene (GDPR right-to-erasure applies to backups too — plan). Restore drills are the only proof.

## 6. Architecture and design principles

Primary -> WAL/snapshot stream -> immutable object storage (3-2-1) in a separate account/region; lifecycle tiers hot->cold; restore-tested into an isolated account; backups are first-class IaC-managed resources.

**Design principles for this category:** Assume failure; test recovery, not just uptime; the cheapest reliability is the one rehearsed before it is needed.

## 7. When to use it

Always for any state.

## 8. When NOT to use it

N/a.

**Alternatives:** none — replication is availability, not a backup substitute.

## 9. Implementation strategies

```bash
pg_basebackup -U replicator -D backup_dir -Ft -z -P
pg_dump --format=custom -f app.dump mydb        # logical, portable
# WAL archiving: archive_command = 'aws s3 cp %p s3://wal/%f'
restic backup /data --repo s3:s3.amazonaws.com/bucket --exclude-caches
```

Managed: RDS automated backups (7-35d) + cross-region snapshots.

## 10. Production-grade implementation

**Scenario:** Postgres fleet: nightly `pg_dump` to S3 + continuous WAL to separate region; object-lock 30 days; monthly restore into an isolated account; the 2026 bad-migration incident: PITR restored to 4 minutes before the bad deploy; 20 minutes of lost writes replayed from the outbox; zero customer-visible corruption.

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

DR is inherently distributed: replication links, region failover, and cross-region consistency decide whether your 'HA' survives the disaster or just survives the drill.

## 14. AI/ML/LLM application examples where relevant

Model weights, indexes, and fine-tune datasets are the AI disaster assets — 3-2-1, encrypted, restore-tested.

## 15. Security considerations

3-2-1 + immutability (object lock) — ransomware cannot delete what it cannot modify.

## 16. Performance considerations

Failover/DR add replication RTT (sync) or a lag window (async) — choose per data class, not globally.

## 17. Common mistakes

Untested restores; backup on same array/provider/account; `pg_dump` from cron nobody monitors; retention forever (cost + privacy); backup of app but not config/secrets/IaC; treating snapshots as backups (snapshots are not logical-corruption protection).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `backup_last_success_age_seconds`, `restore_drill_success`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Monthly automated restore; checksum verification; PITR to random recent minute on staging; deletion-restoration test; backup-failure alert fire-drill.

## 21. Deployment considerations

DR/failover changes must be rehearsed: quarterly game days with measured RTO/RPO; record results; update the runbook after every rehearsal.

## 22. Production-readiness checklist

- [ ] 3-2-1-1
- [ ] Encrypted offsite immutable storage
- [ ] Age-of-latest-backup alert
- [ ] Monthly restore test
- [ ] WAL/PITR for transactional DBs
- [ ] Backup credentials different from prod credentials
- [ ] Test restore into isolated account
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Backup runs but restore impossible (encryption key unavailable, format mismatch); backups 3 days old (retention misconfigured); production and backups in same account (ransomware deletes both); logical dumps during heavy write (inconsistent without snapshot); backup job silently failing (no alert on last-successful-age); unencrypted dumps on laptop; GDPR erasure meaningless because backup retains PII forever.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/backup.html
- https://docs.aws.amazon.com/aws-backup/

**Related topics in this library:** `#83 Disaster Recovery`, `#72 Encryption at Rest`, `#55 Rollbacks`, `#32 Replication` (replication ≠ backup), `#81 Database Migrations` (backup before DDL).
