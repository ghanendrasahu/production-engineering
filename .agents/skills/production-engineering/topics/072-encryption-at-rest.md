---
topic: 72
title: Encryption at Rest
category: D
skill: production-engineering
status: stable
---

# 072 — Encryption at Rest

## 1. Topic name and metadata

- **Number:** 72 of 111
- **Title:** Encryption at Rest
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/072-encryption-at-rest.md`

## 2. What it is

Encrypting data stored on disk or in backups/snapshots so that stolen storage media or snapshot leaks yield ciphertext, decryptable only with the keys.

## 3. Why it exists

Stolen disks and leaked snapshots must yield ciphertext.

## 4. The engineering problem it solves

Physical theft, leaked backups, snapshot mishandling, and misconfigured object storage expose raw data; encryption at rest neutralizes the storage layer as an attack vector.

## 5. How it works internally

Full-disk/volume encryption (AES-256, dm-crypt/LUKS, cloud EBS/RDS encryption) vs application-level (column-level like pgcrypto, field-level in app) vs envelope encryption: data key encrypts data, KMS master key encrypts data keys; plaintext keys never persist. Key rotation: re-wrap or re-encrypt; KMS audits every decrypt. Backups must be encrypted too — an unencrypted dump defeats the disk encryption. Databases: RDS/Cloud SQL encrypt storage transparently; pgcrypto for sensitive columns (PII, tokens) with per-tenant keys for multi-tenant isolation.

## 6. Architecture and design principles

KMS + storage encryption at every layer (disk, object store, DB, backups); app layer encrypts individual fields when tenant isolation or regulatory scope demands it.

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

Always for production data and all backups.

## 8. When NOT to use it

N/a.

**Alternatives:** TDE for almost everything; field-level encryption for high-sensitivity columns; tokenization for PCI (data never stored at all).

## 9. Implementation strategies

```bash
aws rds modify-db-instance --storage-encrypted   # cannot change after creation — plan early
aws s3 cp data.gz s3://bucket --sse aws:kms --sse-kms-key-id alias/app
```

```python
# Field-level envelope encryption with KMS (concept)
plaintext_data_key = kms.generate_data_key(KeyId=KMS_KEY_ID, KeySpec="AES_256")
ciphertext = aes_gcm_encrypt(plaintext_data_key, pii)
store(ciphertext, encrypted_key=plaintext_data_key encrypted by KMS)
```

## 10. Production-grade implementation

**Scenario:** Healthcare SaaS: RDS encrypted at rest, S3 backups encrypted with per-region KMS keys, `users.ssn` column encrypted with pgcrypto keyed by tenant — lost backup yields ciphertext; quarterly key rotation; audit shows every decrypt.

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

Encrypt PII at the service boundary before persistence (e.g., `pgcrypto` `pgp_sym_encrypt`), decrypt on read with key from KMS at request time — DB remains ciphertext at rest even to DBA with disk access (defense in depth; app-level users can still see).

## 13. Distributed-system considerations

Security is global: identity, secrets, and policy must be consistent everywhere the workload runs — one unpatched region or sidecar undoes the rest.

## 14. AI/ML/LLM application examples where relevant

Not applicable — this concept operates below or beside the LLM layer; it applies to AI systems only indirectly (e.g., via the platform that runs them). Do not force AI-specific machinery here; apply the standard pattern unchanged.

## 15. Security considerations

Encrypt every byte at rest incl. backups; KMS; rotation; decrypt-audits.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

Unencrypted backups; keys in the repo/env unencrypted; single global key; no rotation plan; encryption but no access audit; encrypting useless data while leaving PII plain.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `kms_decrypt_total`, unencrypted-storage findings

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Restore backup in isolated account and attempt decrypt without key → must fail; KMS policy deny test for wrong principal; rotation drill; field-decrypt round-trip test in CI; verify snapshot encryption flags in infra-as-code review.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] Enable encryption by default on all storage and backups
- [ ] Envelope encryption with cloud KMS
- [ ] Separate keys per data class/tenant
- [ ] Rotation with overlap
- [ ] IAM-bound key policies
- [ ] Audit decrypts
- [ ] Encrypt PII at field level for defense in depth
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Key stored next to the data (defeats everything); unencrypted backup while disk encrypted (most common gap); KMS region outage blocks all decrypts (availability via multi-region keys); key rotation without re-encrypt or dual-key read window → data unreadable; snapshot shared publicly; pgcrypto password in connection string (key in app env — acceptable if env is KMS-injected); treating TDE as protection from app-layer SQL injection (it isn't).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.aws.amazon.com/kms/
- https://cheatsheetseries.owasp.org/

**Related topics in this library:** `#73 Encryption in Transit`, `#67 Secrets Management`, `#84 Backups`, `#83 Disaster Recovery`, `#72 Encryption at Rest` + `#68 IAM` for key policy.
