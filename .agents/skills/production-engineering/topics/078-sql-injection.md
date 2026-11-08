---
topic: 78
title: SQL Injection
category: D
skill: production-engineering
status: stable
---

# 078 — SQL Injection

## 1. Topic name and metadata

- **Number:** 78 of 111
- **Title:** SQL Injection
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/078-sql-injection.md`

## 2. What it is

An attack in which untrusted input is concatenated into a SQL string and alters the query's structure — reading, corrupting, or deleting data and sometimes escalating to OS commands.

## 3. Why it exists

SQL built from input is instructions, not data.

## 4. The engineering problem it solves

`' OR '1'='1` and worse are still among the most exploited web vulnerabilities; one tainted parameter can dump the whole database and bypass auth.

## 5. How it works internally

SQL is a language; when data becomes part of the syntax, the parser treats it as instructions. Parameterized queries (prepared statements) send text and data through **separate channels** — the server compiles the plan with literal binding, so input can never become syntax. ORMs using bound parameters are safe by construction; string interpolation (`f"SELECT ... WHERE id = {uid}"`), `.execute(text(f"...{x}..."))` with f-strings, and hand-built raw SQL are the classic offenders. Second-order injection: stored value (profile name) later interpolated into another query — same rule, harder to spot.

## 6. Architecture and design principles

Data access layer — everywhere SQL is built. Defenses: parameters, least-privilege DB role (app role has no DDL), errors not leaking schema, WAF as backstop only.

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

Always — parameterization is the only acceptable pattern.

## 8. When NOT to use it

N/a.

**Alternatives:** ORM suffices for most; for reporting, read-only replica + parameterized SQL; for structure changes, allowlists.

## 9. Implementation strategies

```python
# UNSAFE
session.execute(text(f"SELECT * FROM users WHERE email = '{email}'"))
# SAFE — bound parameter
session.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email})
stmt = select(User).where(User.email == email)          # ORM binds params
```

DB role: `GRANT SELECT, INSERT, UPDATE ON ...` only — no DROP/TRUNCATE; separate migration role.

## 10. Production-grade implementation

**Scenario:** Legacy search endpoint concatenated `q` into LIKE; attacker read `pg_stat_activity` and dumped `users` via `UNION SELECT`; fixed in 4 hours with bind params + statement logging alert; role trimmed to SELECT/INSERT only.

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

Pydantic coerces `user_id: int` before the query — most injection is input-typing plus parameter binding; raw SQL must use bind params; `escape()` is **not** a substitute for parameters.

## 13. Distributed-system considerations

Security is global: identity, secrets, and policy must be consistent everywhere the workload runs — one unpatched region or sidecar undoes the rest.

## 14. AI/ML/LLM application examples where relevant

Text-to-SQL features MUST run against read-only roles with row limits — never as the DB superuser.

## 15. Security considerations

Bind parameters; `IN` allowlists; least-privilege role; `statement_timeout`.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

String-built queries anywhere; `LIKE` escaping confusion ("I escaped quotes, so it's fine"); trusting ints from path params without typing; app role = postgres superuser; raw error pages; believing ORM = immune (raw fragments remain possible).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `sqli_attempts_total` (WAF), parameterized-query coverage in SAST

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

sqlmap against staging endpoints; fuzz path params with `' OR 1=1--`, `\x00`, `UNION SELECT`; CI pre-commit grep for f-string SQL patterns; integration test asserting errors don't leak query text; least-privilege role verification test.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] Bind parameters for every value
- [ ] Allowlist identifiers
- [ ] ORM-first
- [ ] Least-privilege DB role (no DDL, no superuser)
- [ ] Error sanitization
- [ ] Code review grep for f-strings near SQL
- [ ] Sqlmap in CI
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Partial parameterization (one raw fragment among bound ones); `IN (:list)` with expansion mistakes reintroducing raw SQL; ORDER BY/column name unparameterizable (validate against allowlist); dynamic table names (allowlist + quoting if unavoidable); stored-procedure string exec (`sp_executesql` with concatenated SQL); leaking raw DB errors (stack traces with query text) to users.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://owasp.org/www-community/attacks/SQL_Injection
- https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html

**Related topics in this library:** `#74 WAF` (backstop only), `#26 Query Optimization` (EXPLAIN safe? no — injection ≠ performance), `#79 XSS` (same input-trust class), `#68 IAM` (DB role least privilege).
