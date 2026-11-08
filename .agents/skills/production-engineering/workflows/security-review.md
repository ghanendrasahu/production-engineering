# Workflow — Security Review

Run for any new endpoint, data flow, auth change, or dependency. Two passes: boundary and internals. Output: CRITICAL/HIGH/MEDIUM/LOW findings + verdict.

## Pass 1 — The Boundary (attacker's view)

1. Enumerate entry points: HTTP routes, webhooks, queue consumers, file uploads, background jobs, SSR/markdown renderers, admin tooling, CLIs.
2. For each: **authentication?** (valid token, signature, expiry, audience) · **authorization?** (scope AND object/tenant checks server-side, not via client-provided IDs) · **input validation?** (types, sizes, ranges, allowlists at the boundary) · **output encoding?** (HTML/attr/JS/URL context-appropriate) · **rate limits?** · **audit log?**
3. Assume hostile input everywhere: try `' OR 1=1--`, `<script>…</script>`, `../../etc/passwd`, `http://169.254.169.254/`, `{"json": "depth-bomb"}` — see `topics/078-sql-injection.md`, `079-xss.md`, `080-ssrf.md`.

## Pass 2 — The Internals (insider's view)

4. **Secrets**: env/manager only; scan CI (gitleaks/detect-secrets); no secrets in logs; rotation exists; `docker history` clean.
5. **Data at rest/transit**: TLS/mTLS everywhere; storage/backups encrypted with KMS; PII minimized; logs redact tokens/passwords/SSNs (`#59`, `#67`, `#72-73`).
6. **Dependencies**: osv-scanner clean; base image current; SBOM exists; private-registry scoping (`#108`).
7. **IAM**: least privilege; humans on SSO+MFA, machines on workload identity; no shared credentials; CI uses OIDC (`#68`, `#6`).
8. **Infra**: security groups deny by default; origin locked to CDN IPs; WAF/L7 rules current; IMDSv2 (no IMDSv1); etcd/state encrypted.
9. **AI paths**: prompt-injection defenses; tenant isolation in retrieval/cache/tools; model output never eval'd; spend caps + kill switch (`../references/ai-engineering.md`).
10. **Incident readiness**: can you revoke a compromised credential in <5 minutes? Run the drill now — if not, that's your first finding.

## Verdict Rules

- CRITICAL (auth bypass, injection, secret exposure, data leak) → block the release.
- HIGH (missing authz on one path, no rotation, IMDSv1) → fix before prod or documented risk acceptance from requester + compensating control.
- MEDIUM (headers, logging, dependency hygiene) → 14-day ticket.
- Always: write findings into the PR; attach the before/after for every fix; re-test the exploit after fixing.

## One-Line Reminders

Half of this library's security topics fit on one card: **validate in, encode out, least privilege, short-lived credentials, secrets in the manager, parameters not strings, TLS everywhere, tokens with expiry, everything logged and auditable.**
