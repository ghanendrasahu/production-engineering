# Security Reference

The security controls every internet-facing service needs: secrets, identity, encryption, edge protection, and the web vulnerability classes â€” ordered from preventing leaks to preventing exploits.

| # | Concept | One-line use case |
|---|---|---|
| 67 | Secrets Management | Never hardcode credentials |
| 68 | IAM | Least-privilege identity and access |
| 69 | OAuth | Delegated authorization flows |
| 70 | JWT Rotation | Short-lived tokens with refresh |
| 71 | TLS | Encrypted transport, always |
| 72 | Encryption at Rest | Data unreadable when stolen |
| 73 | Encryption in Transit | Data unreadable on the wire |
| 74 | WAF | Filter hostile HTTP at the edge |
| 75 | DDoS Protection | Survive volumetric attacks |
| 76 | CORS | Control cross-origin browser access |
| 77 | CSRF | Stop forged state-changing requests |
| 78 | SQL Injection | Parameterized queries only |
| 79 | XSS | Render untrusted input safely |
| 80 | SSRF | Stop servers attacking internal networks |

### 67. Secrets Management

**Definition:** Storage, distribution, rotation, and audit of credentials (API keys, DB passwords, certs) so they never live in source code, images, or logs.

**Problem:** A secret in Git or an image layer is public forever â€” the single most common initial access vector in real breaches; rotation without tooling is impossible in practice.

**Internal Working:** A secrets manager (Vault, AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, K8s Secrets + external-secrets operator, sealed-secrets) holds encrypted secrets, issues short-lived dynamic credentials (Vault DB dynamic secrets, AWS STS), enforces policy on access, and audits every read. Injection mechanisms: env vars at deploy time (ok, but visible to process env), files mounted from CSI drivers, or app-side fetch at startup with cache + TTL. Rotation: dual-credential overlap window â€” new secret issued, old revoked after consumers move.

**Architecture:** CI/CD retrieves secrets at deploy; app reads at startup/runtime; no secret in Docker image or repo; K8s: External Secrets Operator syncs Vault/AWS SM â†’ K8s Secret mounted as env/volume (encrypt etcd!).

**Implementation:**

```bash
vault kv put secret/prod/db password=$(openssl rand -base64 32)
vault read -field=password secret/prod/db
# k8s: externalSecret or sealedSecret YAML synced from Vault/SM
```

```python
import os
DATABASE_URL = os.environ["DATABASE_URL"]   # injected by platform, never committed
```

**FastAPI Example:** `pydantic-settings` `BaseSettings` loading `DATABASE_URL`, `STRIPE_API_KEY` from env with `.env` only in local dev (gitignored); refuse to boot if `APP_ENV=prod` and any key missing.

**Production Example:** RDS credentials rotated by Vault every 30 days with dynamic secrets per pod; a leaked key from an old commit loses access within 30 days; audit log shows which identity read which secret; zero long-lived DB passwords anywhere in configs.

**Failure Scenarios:** Secret committed â†’ must rotate immediately (prevention beats cleanup; git history rewritening doesn't unpublish); env var logged by a debug middleware ("dumping config") â†’ log scrubber + denylist; secret rotation without overlap â†’ prod 500s; K8s Secret base64 is not encryption â€” etcd unencrypted at rest; secrets baked into Docker layers visible via `docker history`; CI logs echoing env during debug builds.

**Best Practices:** Manager, never files; dynamic short-lived credentials where possible; rotation automation; least-privilege per secret; audit on access; scrub secrets from logs; `.gitignore` + pre-commit `detect-secrets`; never in frontend; KMS-encrypted etcd/state; break-glass account heavily monitored.

**Anti-Patterns:** `.env` in repo; secrets in Dockerfile/base images; one shared secret for all services (blast radius = everything); rotation "when convenient"; secrets in frontend env vars (`NEXT_PUBLIC_*`); logging request headers wholesale.

**Trade-offs:** Performance (fetch latency, cache TTL); complexity (proper lifecycle tooling); cost (manager fees, usually small); consistency (rotation window coordination); maintainability (huge win â€” no more rotation archaeology).

**Testing:** Scan CI with detect-secrets/gitleaks; rotate a staging secret and verify zero-downtime; verify app refuses boot without keys; assert no env key appears in logs on error paths; periodic access-audit review.

**Related Concepts:** `#68 IAM`, `#72 Encryption at Rest`, `#71 TLS`, `#6 CI/CD` (secrets in pipelines), `#67 Secrets Management` pairs with `#73 Encryption in Transit`.

**Decision Criteria:** Use when: always â€” no exceptions for production. Do not use when: n/a. Alternatives: platform-native (K8s CSI + cloud KMS-backed stores), dynamic credentials (Vault), workload identity (IRSA/Workload Identity â€” no secret at all).

### 68. IAM

**Definition:** Identity and access management â€” the system of users, roles, policies, and least-privilege permissions that decides who can do what against which resource.

**Problem:** One compromised over-privileged credential = total compromise; unreviewed IAM is how breaches go from "phished dev laptop" to "all data exfiltrated".

**Internal Working:** Principals (users, service accounts, workload roles) + policy documents (allow/deny on actions on resources with conditions). Least privilege: start with nothing, add only what's used. Short-lived credentials via STS/assume-role beat static keys. Resource-based policies vs identity-based policies; permission boundaries; condition keys (IP, time, MFA, tag). Breakglass access with heavy logging; separate human from machine identities.

**Architecture:** Cloud IAM + app-level RBAC/ABAC; OIDC federation from CI (GitHub OIDC â†’ AWS role, no static keys in CI).

**Implementation:**

```json
{ "Version": "2012-10-17", "Statement": [{ "Effect": "Allow",
  "Action": ["s3:GetObject"], "Resource": "arn:aws:s3:::reports/*",
  "Condition": {"StringIpAddress": {"aws:SourceIp": "203.0.113.0/24"}} }] }
```

App-level: roles (`admin`, `editor`, `viewer`) in DB, middleware enforces per-route; policy-as-code (Cedar/OPA) for complex rules; K8s RBAC for cluster access.

**Production Example:** CI deploys via GitHub OIDC â†’ role `deploy-prod` allowed `eks:UpdateCluster` only on prod cluster, expires 15min, no keys anywhere; app pods use IRSA role limited to the buckets/tables they read; access audit quarterly â€” 30% of policies found unused and trimmed.

**Failure Scenarios:** `*:*` policies; shared `admin` account; IAM user with console access instead of federated SSO; policy allows `s3:*` on `*`; detaching a restriction during an incident and never restoring; service accounts with human-level rights; audit disabled to save cost.

**Best Practices:** Least privilege (start deny, add minimal); SSO + MFA for humans; workload identity over static keys; permission boundaries; condition on IP/MFA/VPC; rotate/review quarterly; audit logs (CloudTrail) enabled and alerted; separate prod from staging accounts; break-glass with expiry.

**Anti-Patterns:** Wildcard actions/resources; one shared key per service; IAM policy "temporary full access" for a migration left in place; console-only users; no conditions on sensitive actions.

**Trade-offs:** Performance (STS token exchange adds ~50-200ms first call, cached after); complexity (policy sprawl â€” use ABAC tags); cost (free-ish); consistency (policy lag when permissions replicate); maintainability (policy-as-code + review required).

**Testing:** Policy simulation (AWS IAM Simulator / access-analyzer); negative tests: token from staging rejected for prod; quarterly access-log review automation alerting on unused grants; CI fails PRs adding wildcard actions.

**Related Concepts:** `#67 Secrets Management`, `#69 OAuth`, `#70 JWT Rotation`, `#73 Encryption in Transit`, `#111 Postmortems` (IAM gaps common).

**Decision Criteria:** Use when: always â€” foundational control. Do not use when: n/a. Alternatives: ABAC for scale, OPA/Cedar for fine-grained app authz, service mesh mTLS identity.

### 69. OAuth

**Definition:** An authorization framework (OAuth 2.0/2.1) in which a user grants a third-party application limited access to their resources on another service, without sharing their password.

**Problem:** The pre-OAuth world of password-sharing and stored credentials; applications needed access to user data without ever seeing the password, and users needed revocable, scoped grants.

**Internal Working:** Roles: resource owner, client, authorization server, resource server. Flows: authorization code + PKCE (the only safe flow for public/web apps â€” issues a code exchanged for tokens; PKCE prevents code interception), client credentials (machine-to-machine), refresh token grant (long-lived refresh + short-lived access). ID tokens (OpenID Connect) add identity to OAuth. Scopes bound access (`read:orders`). Tokens are bearer â€” transport security is mandatory (TLS). Revocation endpoint + introspection for opaque tokens; JWT access tokens validated locally via JWKS.

**Architecture:** Browser/app â†’ provider (Google/Auth0/Keycloak) â†’ redirect with code â†’ backend exchanges code for tokens â†’ validates JWT via JWKS â†’ session/cookie for the app.

**Implementation:**

```python
import requests
# authorization code + PKCE exchange
token = requests.post("https://idp/token", data={
    "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
    "client_id": CLIENT_ID, "code_verifier": verifier}).json()
```

JWKS verify: `jwt.decode(access_token, key=jwks_client.get_signing_key_from_jwt(token).key, algorithms=["RS256"], audience="my-api", issuer="https://idp")`.

**FastAPI Example:** `OAuth2PasswordBearer` or Authlib middleware; dependency validates JWT on every route; scopes checked per route via `Security(scopes_required)`; refresh tokens stored hashed, rotation on use.

**Production Example:** Customer portal "Sign in with Google": Authlib, PKCE enforced, access token 15min, refresh 30d rotating, scopes `openid email profile read:orders`; a leaked token expires in 15min; Google revoked-credential events processed via webhook to clear app sessions.

**Failure Scenarios:** Missing PKCE (code interception); `state` parameter missing â†’ CSRF on login; tokens in localStorage (XSS-stealable â€” prefer HttpOnly Secure SameSite cookie); refresh tokens never rotated/reused forever; redirect_uri wildcard (`https://*.app.com`) â†’ token leak to attacker subdomain; accepting any `alg` in JWT verify (alg=none attack); no aud/iss check â†’ token replay across services.

**Best Practices:** Authorization code + PKCE only; state param; exact redirect URIs; short-lived access tokens; rotating refresh tokens with reuse detection (invalidate the family); validate aud/iss/exp/alg; store tokens HttpOnly; least-privilege scopes; introspect opaque tokens; log all grant/revoke events.

**Anti-Patterns:** Implicit flow (deprecated); password grant; custom "OAuth-like" homegrown; tokens in localStorage/XSS-exposed; scopes never reviewed ("read:all"); no revocation path.

**Trade-offs:** Performance (JWKS cached; introspection adds latency if opaque); complexity (flows are subtle â€” use Authlib/Keycloak, not DIY); cost (IdP licensing at scale); consistency (token revocation lag); maintainability (battle-tested libraries).

**Testing:** Full integration against Keycloak in Docker-compose; tampered token â†’ 401; expired token â†’ refresh path; wrong-audience token â†’ 401; refresh reuse â†’ family invalidated; state mismatch â†’ rejection.

**Related Concepts:** `#70 JWT Rotation`, `#68 IAM`, `#71 TLS`, `#76 CORS`, `#77 CSRF`, `#69 OAuth` uses `#73 Encryption in Transit`.

**Decision Criteria:** Use when: user-facing login, third-party integrations, SSO. Do not use when: pure machine-to-machine (client credentials subset), internal service mesh (mTLS + SPIFFE better). Alternatives: session cookies after SSO, API keys for server-to-server (`#67`), mTLS, SAML (enterprise legacy).

### 70. JWT Rotation

**Definition:** The practice of issuing short-lived access tokens paired with long-lived but revocable refresh tokens, where refresh tokens rotate on each use so token theft has a bounded window and reuse is detectable.

**Problem:** A leaked access token is a bearer credential valid until expiry; without rotation and reuse detection, an attacker maintains access indefinitely and you cannot tell the tokens apart.

**Internal Working:** Access token (JWT, 5-15min, stateless â€” verified via JWKS locally, no DB lookup). Refresh token (opaque or JWT, 7-30d, stored in DB/Redis). On refresh: verify â†’ atomically revoke old + issue new refresh token in the same key family; if an already-used refresh token appears again, revoke the **entire family** (theft signal) â†’ forced re-login. Revocation list checked on access-token validation only if truly stateless revocation is needed (use short expiry instead). Logout = family revoke.

**Architecture:** IdP or app-issued tokens; Redis family store; refresh endpoint with single-transaction rotation; device/session listing for users.

**Implementation:**

```python
def refresh(refresh_token: str):
    fam = r.get(f"rt:{hash(refresh_token)}")
    if fam is None:
        r.delete(f"family:{family_of(refresh_token)}")  # reuse detected â†’ nuke family
        raise HTTPException(401, "refresh token reuse detected")
    new_refresh = issue(); r.set(f"rt:{hash(new_refresh)}", fam, ex=30*86400); r.delete(f"rt:{hash(refresh_token)}")
    return access_token(sub=fam.user), new_refresh
```

**FastAPI Example:** `POST /auth/refresh` performs rotation; `POST /auth/logout` deletes family keys; dependency validates access token signature/exp/aud/iss; `/me/sessions` lists active families for the user to revoke.

**Production Example:** Mobile banking app: access 10min, refresh rotating 14d; a user pastes tokens into a malicious tool; first refresh by attacker succeeds (family moves), user's next refresh fails â†’ family revoked â†’ all sessions killed; push notification "suspicious sign-in"; incident closed without support call.

**Failure Scenarios:** Reuse detection implemented but families not linked â†’ theft undetected; refresh rotation not atomic (old token valid twice) â†’ race creates two live tokens; long access-token lifetimes (24h+) defeat rotation; revocation store checked on every access request (defeats statelessness â€” just shorten expiry); refresh token in localStorage; family IDs guessable.

**Best Practices:** Short access expiry (5-15min); rotating refresh with family-wide reuse kill; opaque or hashed-at-rest refresh tokens; per-device families; session listing + remote revoke; leeway in exp checks (clock skew, `#96`); audit refresh events; force re-auth for sensitive actions (step-up).

**Anti-Patterns:** 7-day access tokens; no reuse detection; refresh without rotation; JWT always valid once issued ("stateless forever" fantasy); refresh tokens unhashed in DB; logout that only clears client storage.

**Trade-offs:** Performance (rotation adds one write per refresh; JWKS cached reads are cheap); complexity (family bookkeeping); cost (Redis ops); consistency (revocation within seconds via families); maintainability (auth library does the heavy lifting).

**Testing:** Refresh twice with same old token â†’ family revoked â†’ 401 on both; logout â†’ subsequent refresh 401; access token with wrong aud â†’ 401; expiry boundary test with leeway; concurrent refresh from two tabs â†’ only one wins.

**Related Concepts:** `#69 OAuth`, `#67 Secrets Management`, `#96 Clock Skew`, `#68 IAM`, `#71 TLS`.

**Decision Criteria:** Use when: stateless auth at scale with revocation needs â€” basically always. Do not use when: simple server-rendered app with session cookies (server-side sessions simpler). Alternatives: opaque tokens + introspection (revocable instantly, more DB load), server-side sessions with idle timeout, mTLS for machines.

### 71. TLS

**Definition:** Transport Layer Security â€” the protocol providing encryption, integrity, and server authentication on the wire, using certificates issued by a chain rooted at a trusted CA.

**Problem:** Plaintext HTTP (and unauthenticated TLS) exposes credentials and data to anyone on-path (WiFi, ISPs, compromised routers) â€” TLS is table stakes, and its absence is visible in browsers ("Not Secure").

**Internal Working:** Handshake: client hello (versions/ciphers) â†’ server sends cert chain â†’ key exchange (ECDHE) â†’ shared session keys via HKDF â†’ encrypted records (AEAD: AES-GCM/ChaCha20). Certificates: X.509, SAN matching hostname, expiry, chain to root. Session resumption (tickets/IDs) to cut handshake cost. TLS 1.3: 1-RTT (0-RTT with replay risk), forward secrecy mandatory. Modern config: TLSâ‰¥1.2, strong ciphers, HSTS, OCSP stapling, automated certs via ACME (Let's Encrypt certbot) or cloud-managed (ACM).

**Architecture:** Terminate at LB/reverse proxy or cloud CDN; optionally re-encrypt to backends (TLS everywhere, including internal mTLS with SPIFFE/mesh).

**Implementation:**

```bash
certbot --nginx -d app.example.com --agree-tos -m ops@example.com
# renewal automated via systemd timer / cron
nginx: listen 443 ssl http2; ssl_protocols TLSv1.2 TLSv1.3; ssl_stapling on;
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
```

```python
# Python: requests/httpx verify by default â€” NEVER verify=False
import ssl, httpx
httpx.get("https://api.example.com", verify=True, timeout=5.0)
```

**Production Example:** Cloudflare-proxied app: full TLS (edge cert + origin cert), HSTS preload, auto-renewed every 60 days, OCSP stapling; cert expiry monitor pages at 14 days; an expired cert once took the site down â€” now impossible unnoticed.

**Failure Scenarios:** Expired cert â†’ total outage (most common TLS incident); mixed content (http assets on https page); self-signed/unknown CA on internal service without pinning â†’ "worked in dev, fails in prod"; TLS 1.0 on old clients; TLS termination at LB but plaintext internally and the LB is in the same trust zone as the app (accepted but document it); cert valid but hostname mismatch (SAN missing); certbot renewal cron silently broken; 0-RTT replay on state-changing endpoints.

**Best Practices:** TLS 1.2/1.3 only; automated ACME issuance + renewal with monitoring; HSTS + preload; OCSP stapling; redirect 80â†’443; managed certs; internal mTLS for sensitive east-west traffic; monitor expiry and chain validity weekly; test with `testssl.sh`; never `verify=False`; certificate transparency monitoring for your domains.

**Anti-Patterns:** HTTP behind LB; certs as secrets stored by hand; manual renewal; wildcard cert shared everywhere (blast radius); HSTS without understanding it's sticky (browsers pin you); disabling verification "temporarily"; RC4/3DES legacy ciphers left enabled "for old clients".

**Trade-offs:** Performance (handshake ~1-2 RTT; resumption mitigates; CPU for AES-GCM â€” negligible on modern CPUs); complexity (low with managed certs); cost (certs free via ACME; managed ~$); consistency (n/a); maintainability (automation is the whole game).

**Testing:** `testssl.sh`/`ssllabs` scan; renewal drill (force-renew staging); expiry alert test; curl verification in smoke tests; verify HSTS header; chaos test: deploy an expired cert in staging and confirm monitor pages.

**Related Concepts:** `#72 Encryption at Rest`, `#73 Encryption in Transit`, `#4 Reverse Proxies`, `#97 DNS`, `#67 Secrets Management`, `#80 SSRF` (TLS to internal).

**Decision Criteria:** Use when: always. Do not use when: n/a (even internal links deserve mTLS in zero-trust). Alternatives: n/a; for service-to-service, prefer mTLS via mesh.

### 72. Encryption at Rest

**Definition:** Encrypting data stored on disk or in backups/snapshots so that stolen storage media or snapshot leaks yield ciphertext, decryptable only with the keys.

**Problem:** Physical theft, leaked backups, snapshot mishandling, and misconfigured object storage expose raw data; encryption at rest neutralizes the storage layer as an attack vector.

**Internal Working:** Full-disk/volume encryption (AES-256, dm-crypt/LUKS, cloud EBS/RDS encryption) vs application-level (column-level like pgcrypto, field-level in app) vs envelope encryption: data key encrypts data, KMS master key encrypts data keys; plaintext keys never persist. Key rotation: re-wrap or re-encrypt; KMS audits every decrypt. Backups must be encrypted too â€” an unencrypted dump defeats the disk encryption. Databases: RDS/Cloud SQL encrypt storage transparently; pgcrypto for sensitive columns (PII, tokens) with per-tenant keys for multi-tenant isolation.

**Architecture:** KMS + storage encryption at every layer (disk, object store, DB, backups); app layer encrypts individual fields when tenant isolation or regulatory scope demands it.

**Implementation:**

```bash
aws rds modify-db-instance --storage-encrypted   # cannot change after creation â€” plan early
aws s3 cp data.gz s3://bucket --sse aws:kms --sse-kms-key-id alias/app
```

```python
# Field-level envelope encryption with KMS (concept)
plaintext_data_key = kms.generate_data_key(KeyId=KMS_KEY_ID, KeySpec="AES_256")
ciphertext = aes_gcm_encrypt(plaintext_data_key, pii)
store(ciphertext, encrypted_key=plaintext_data_key encrypted by KMS)
```

**FastAPI Example:** Encrypt PII at the service boundary before persistence (e.g., `pgcrypto` `pgp_sym_encrypt`), decrypt on read with key from KMS at request time â€” DB remains ciphertext at rest even to DBA with disk access (defense in depth; app-level users can still see).

**Production Example:** Healthcare SaaS: RDS encrypted at rest, S3 backups encrypted with per-region KMS keys, `users.ssn` column encrypted with pgcrypto keyed by tenant â€” lost backup yields ciphertext; quarterly key rotation; audit shows every decrypt.

**Failure Scenarios:** Key stored next to the data (defeats everything); unencrypted backup while disk encrypted (most common gap); KMS region outage blocks all decrypts (availability via multi-region keys); key rotation without re-encrypt or dual-key read window â†’ data unreadable; snapshot shared publicly; pgcrypto password in connection string (key in app env â€” acceptable if env is KMS-injected); treating TDE as protection from app-layer SQL injection (it isn't).

**Best Practices:** Enable encryption by default on all storage and backups; envelope encryption with cloud KMS; separate keys per data class/tenant; rotation with overlap; IAM-bound key policies; audit decrypts; encrypt PII at field level for defense in depth; document key custody and DR plan.

**Anti-Patterns:** Unencrypted backups; keys in the repo/env unencrypted; single global key; no rotation plan; encryption but no access audit; encrypting useless data while leaving PII plain.

**Trade-offs:** Performance (transparent disk encryption â‰ˆ free; field-level adds KMS calls â€” cache data keys); complexity (key lifecycle); cost (KMS per-request charges); consistency (key identity across envs); maintainability (automated rotation essential).

**Testing:** Restore backup in isolated account and attempt decrypt without key â†’ must fail; KMS policy deny test for wrong principal; rotation drill; field-decrypt round-trip test in CI; verify snapshot encryption flags in infra-as-code review.

**Related Concepts:** `#73 Encryption in Transit`, `#67 Secrets Management`, `#84 Backups`, `#83 Disaster Recovery`, `#72 Encryption at Rest` + `#68 IAM` for key policy.

**Decision Criteria:** Use when: always for production data and all backups. Do not use when: n/a. Alternatives: TDE for almost everything; field-level encryption for high-sensitivity columns; tokenization for PCI (data never stored at all).

### 73. Encryption in Transit

**Definition:** Encrypting data while it moves between systems (TLS, SSH, VPN, mTLS) so network observers and on-path attackers see ciphertext.

**Problem:** Unencrypted east-west traffic inside a "trusted" network is readable by anyone who gains a foothold or misconfigured route â€” internal networks are compromised constantly; zero-trust demands encryption everywhere.

**Internal Working:** TLS (`#71`) between clients, LB, and origins; mTLS (both parties present certs â€” SPIFFE/SPIRE, service mesh Envoy/Istio) inside the cluster; SSH tunnels for admin; WireGuard/VPN between sites; private links (AWS PrivateLink) to keep traffic off the public internet; cert-manager issues/rotates internal certs. Encryption â‰  authorization â€” still authenticate each peer.

**Architecture:** External TLS at edge; internal mTLS via mesh or per-service cert-manager; DB connections with `sslmode=verify-full`; never trust VPC = safe.

**Implementation:**

```ini
# Postgres: require TLS from all clients
require_secure_transport = on   # or pg_hba.conf: hostssl all all 0.0.0.0/0 scram-sha-256
```

```python
ssl_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile="ca.pem")
ssl_ctx.check_hostname = True; ssl_ctx.verify_mode = ssl.CERT_REQUIRED
async with httpx.AsyncClient(verify=ssl_ctx, timeout=5.0) as c: ...
```

Istio PeerAuthentication STRICT â†’ plaintext refused cluster-wide.

**Production Example:** Payment service mesh: ingress â†’ API (edge TLS); all service-to-service calls mTLS; DB with `sslmode=verify-full`; cert-manager auto-rotates every 30 days; an internal sniffing test captures only ciphertext.

**Failure Scenarios:** Internal plaintext "because VPC"; `sslmode=require` without CA verification (MITM possible); cert rotation breaks a service not reloaded; mesh in PERMISSIVE mode (half-unencrypted forever); internal CA compromised â€” rotate all; app bug logging full URLs with tokens to stdout captured by log shippers.

**Best Practices:** TLS 1.2+ everywhere; mTLS east-west; `verify-full` for DBs; rotate internal certs automatically; mesh strict mode; encrypt backups too; monitor cert expiry internally; treat VPC as hostile scope; test with a sniffer on staging.

**Anti-Patterns:** Plaintext internal DB links; verify-none in clients; long-lived internal certs; optional encryption ("PERMISSIVE") everywhere; secrets in URLs over "internal" HTTP.

**Trade-offs:** Performance (mTLS adds handshake; mesh amortizes via connection reuse); complexity (mesh/cert rotation ops); cost (mesh infra); consistency (strict mode rollout needs ordering); maintainability (cert-manager/mesh pays off at >10 services).

**Testing:** Sniffer test in staging; sslmode verification test to DB (attempt without CA â†’ refuse); cert-expiry alerts internal; mesh strict-mode rollout canary; plaintext port probe (nc) fails.

**Related Concepts:** `#71 TLS`, `#72 Encryption at Rest`, `#69 OAuth`, `#74 WAF`, `#67 Secrets Management`.

**Decision Criteria:** Use when: always â€” including inside the cluster. Do not use when: n/a. Alternatives: n/a (this is the transport baseline); for special cases, HPKE for end-to-end payload encryption beyond TLS hops.

### 74. WAF

**Definition:** A web application firewall â€” a filtering layer at the HTTP edge (or in the app) that inspects requests against rules for injection, bots, and known-bad patterns, and blocks/challenge/log them before the origin sees them.

**Problem:** Origins shouldn't have to distinguish malicious from legitimate traffic alone; many attacks (SQLi probes, log4shell) are cheap to filter cheaply at the edge.

**Internal Working:** Rule engines: signature matching (OWASP Core Rule Set â€” CRS), rate/anomaly scoring (ModSecurity score â‰¥ threshold â†’ block), regexp for payloads; deployment modes (block/detect); managed vs custom rules; virtual patching when a CVE has no patch yet; API/schema-aware WAFs (AWS WAF with schema validation, API Gateway) block payloads violating OpenAPI. CDN-integrated (Cloudflare, AWS WAFv2, Akamai, F5, ModSecurity/Nginx).

**Architecture:** Client â†’ CDN/WAF â†’ origin. Logs stream to SIEM; false-positive review process required (block pages with captcha).

**Implementation:**

```hcl
# AWS WAFv2 (concept): managed rule group + rate-based rule
resource "aws_wafv2_web_acl" "api" {
  default_action { allow {} }
  rule { name = "core" ; priority = 1
    override_action { none {} }
    statement { managed_rule_group_statement { name="AWSManagedRulesCommonRuleSet" vendor_name="AWS" } }
    visibility_config { sampled_requests_enabled=true metric_name="core" cloudwatch_metrics_enabled=true } } }
```

**Production Example:** Public GraphQL API: Cloudflare WAF with OWASP CRS + custom rule blocking `/admin` from non-corp IPs; virtual patched a log4j probe wave within 10 minutes of CVE disclosure â€” origin never saw the traffic; 4,000 blocks/hour, 2 false positives/month via an exceptions list.

**Failure Scenarios:** CRS too aggressive on legitimate params (false positives â†’ support load); detect-only mode forever (logs but no protection); rules stale (CVE unhandled); WAF at CDN but origin directly reachable (bypass) â€” lock security groups to CDN IPs; rule explosion slowing origin (WAF adds 1-10ms); bypass via encoding tricks missed by regex.

**Best Practices:** CDN-integrated WAF; start detect â†’ tune â†’ block; exceptions process; virtual patching for n-day CVEs; lock origin to WAF IPs; API schema validation as WAF rule; alert on block-rate spikes; exclude health checks; log everything to SIEM.

**Anti-Patterns:** WAF as the only control (no parameterized queries!); block mode untuned on day one; origin reachable directly; ignoring WAF logs ("alerting disabled to reduce noise"); regex payloads instead of schema validation.

**Trade-offs:** Performance (1-10ms added); complexity (tuning false positives); cost (managed rule + request volume pricing); consistency (rules across edge locations); maintainability (managed CRS >> hand-rolled).

**Testing:** Canary probes (sqlmap against staging WAF â†’ blocked 403); false-positive regression suite from prod traffic samples; origin-bypass test (direct IP); block-rate dashboards; virtual-patch drill.

**Related Concepts:** `#75 DDoS Protection`, `#48 CDN`, `#78 SQL Injection`, `#79 XSS`, `#4 Reverse Proxies`, `#75 DDoS Protection`.

**Decision Criteria:** Use when: any internet-facing app â€” baseline. Do not use when: internal-only service behind VPN/IAM (mTLS sufficient). Alternatives: API gateway schema validation, app-level input validation (still required â€” WAF is defense in depth, never the only control).

### 75. DDoS Protection

**Definition:** Defenses against denial-of-service attacks â€” volumetric (flood bandwidth), protocol (SYN floods), and application-layer (expensive query floods) â€” absorbing or filtering hostile traffic before it exhausts capacity.

**Problem:** A saturated origin serves zero legitimate users; bandwidth exhaustion costs money and reputation; app-layer floods can take down expensive endpoints (search, LLM) cheaply.

**Internal Working:** CDN anycast absorption (huge network capacity, spread globally), L3/L4 scrubbing (SYN cookies, rate limiting by source ASN), L7 WAF rules (per-IP rate, bot detection, challenge pages/CAPTCHA), SYN cookies mitigate SYN floods (stateless handshake), connection limits, caching absorbs hot endpoints, origin shielded by CDN (only CDN IPs allowed in security group). Cost of the attack to the attacker raised (anycast = flood hits globally distributed points) â€” this is why cloud CDNs dominate DDoS mitigation.

**Architecture:** CDN â†’ WAF â†’ LB â†’ origin (deny direct origin access); scrubbing centers; provider on-call with runbooks.

**Implementation:**

```nginx
# last-mile defense at Nginx (in addition to CDN)
limit_req_zone $binary_remote_addr zone=one:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=addr:10m;
limit_req zone=one burst=20 nodelay; limit_conn addr 20;
```

AWS Shield Standard (free, L3/L4) + Shield Advanced (DDoS response team + cost protection); Cloudflare Magic Transit for L3.

**Production Example:** 50 Gbps UDP flood + app-layer 30k req/s to `/search?q=random`; anycast absorbed UDP invisibly; L7 rule challenged with JS bot detection; origin load unchanged; cost spike only in WAF request fees; 2 hours, no downtime.

**Failure Scenarios:** Direct-IP origin reachable (bypass of entire CDN defense â€” the #1 DDoS failure); WAF rules per-IP useless vs botnets (10k IPs) without ASN/fingerprint signals; cache stampede because TTL expired during attack; TLS negotiation floods (compute at edge? CDN does crypto offloading); failover site unsecured (DDoS follows to disaster site); alerting drowned by attack noise (tune thresholds).

**Best Practices:** CDN in front always; origin SG locked to CDN IPs; cache expensive public endpoints; challenge/CAPTCHA for bot patterns; anycast provider with proven capacity; runbook + provider hotline; cost guardrails; layered (L3 volumetric + L7 WAF); test with synthetic probes, not actual attacks.

**Anti-Patterns:** nginx limit_req as the only "DDoS protection" (per-IP useless vs botnet); no caching for public hot content; origin IP exposed in DNS history; scaling up to absorb (pay attacker's bill); blocking by country as general policy (collateral damage).

**Trade-offs:** Performance (CDN caching accelerates legit users too â€” win-win); complexity (CDN config discipline); cost (CDN/WAF fees; attack traffic can add origin bandwidth charges if misrouted); consistency (edge caching staleness); maintainability (provider-managed beats DIY).

**Testing:** Origin-bypass scan (nmap direct IP â€” must not serve); cache hit-rate assertions on expensive routes; WAF challenge synthetic test; monthly provider status review; runbook tabletop exercise.

**Related Concepts:** `#74 WAF`, `#48 CDN`, `#4 Reverse Proxies`, `#1 Rate Limiting`, `#49 Edge Caching`, `#75 DDoS Protection` layers on `#3 Load Balancing`.

**Decision Criteria:** Use when: always behind a CDN with L3/L4 protection â€” baseline. Do not use when: n/a (it comes with the CDN). Alternatives: provider-managed (Cloudflare/Akamai/AWS Shield) â€” never hand-rolled for volumetric.

### 76. CORS

**Definition:** Cross-Origin Resource Sharing â€” the browser-enforced mechanism controlling which origins may read responses from a server; preflight (OPTIONS) checks for non-simple requests.

**Problem:** Browsers block cross-origin reads (same-origin policy); developers thus misconfigure CORS "to make errors go away", often by reflecting any Origin with credentials â€” which reopens the exact hole SOP closes.

**Internal Working:** Preflight: browser sends `OPTIONS` with `Origin` + `Access-Control-Request-Method/Headers`; server responds with allowed origin/methods/headers and `Access-Control-Max-Age` (cache preflight). Simple requests skip preflight. With credentials (cookies), `Access-Control-Allow-Origin: *` is invalid â€” must echo the specific origin and `Allow-Credentials: true`. Response without proper header â†’ browser blocks JS from reading it (server still processed the request â€” CORS is not an access control for non-browser clients). Vary: Origin must be set when echoing dynamic origins (cache correctness).

**Architecture:** Edge/proxy or app middleware; preflight caching at CDN.

**Implementation:**

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"],
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"],
                   allow_credentials=True, max_age=600)
```

Explicit allowlist beats regex (`.*\.example\.com` accidentally matches `badexample.com.evil.com`).

**Production Example:** SPA on `app.example.com` + API on `api.example.com`: middleware allowlist both, `allow_credentials=true` for cookie session, preflight cached `max_age=600`, `Vary: Origin` set â€” zero CORS errors, no wildcard anywhere.

**Failure Scenarios:** `allow_origins=["*"]` + `allow_credentials=true` â†’ browsers reject, apps "work" via disabling checks; arbitrary-origin reflection â†’ CSRF-ish data theft; missing `Vary: Origin` â†’ CDN serves cached response with wrong origin header to another origin; preflight not cached â†’ latency added per call; allowing `*` methods/headers "temporarily"; CORS configured but cookies still SameSite=None without Secure (modern browsers block).

**Best Practices:** Explicit origin allowlist; credentials only with specific origins; `Vary: Origin`; cache preflights; minimal methods/headers; keep cookies SameSite=Lax/Strict; remember CORS doesn't protect server actions â€” CSRF/auth do; same-site subdomain strategy (`api.example.com` for SPA cookies under `example.com`).

**Anti-Patterns:** Reflect any Origin; `*` with credentials; wildcards in regex; disabling browser checks; CORS as a security control; forgetting preflight cache â†’ every POST costs two round trips.

**Trade-offs:** Performance (preflight per non-simple call â€” mitigated by max-age); complexity (config drift between environments); cost (free); consistency (CDN Vary handling); maintainability (one middleware, one list).

**Testing:** curl OPTIONS with Origin header â†’ assert allowlist honored; verify 401/403 without preflight success; E2E browser test from the real SPA; assert `Vary: Origin` in responses; scan for `*` in config.

**Related Concepts:** `#77 CSRF`, `#69 OAuth`, `#76 CORS` pairs with `#4 Reverse Proxies`, `#79 XSS` (why credentials in headers matters).

**Decision Criteria:** Use when: browser SPA + separate API origin â€” yes. Do not use when: same-origin deployment (no CORS needed at all â€” simplest); non-browser clients (curl/mobile unaffected â€” use auth, not CORS). Alternatives: same-origin proxy (BFF pattern â€” avoids CORS entirely), cookie-based same-site subdomains, postMessage for iframes.

### 77. CSRF

**Definition:** Cross-Site Request Forgery â€” an attack in which a victim's browser, already authenticated via cookies, is tricked into submitting a forged state-changing request the attacker controls.

**Problem:** Sessions-in-cookies are sent automatically; without CSRF defenses, a malicious page can transfer money/change email as the user (though not read responses).

**Internal Working:** Defenses: (1) **SameSite cookies** (`Lax` by default in modern browsers â€” blocks cross-site cookies on non-top-level POSTs; `Strict` blocks even on links; `None` requires Secure). (2) **Synchronizer token**: server issues a per-session random token embedded in forms/headers; server validates on mutation (double-submit cookie or server-side session token). (3) **Custom header check**: require a non-"simple" header (e.g., `X-CSRF-Token`) that triggers preflight â€” cross-origin forms can't set it. (4) Fetch metadata headers (`Sec-Fetch-Site: cross-site` â†’ reject) increasingly supported.

**Architecture:** App middleware + cookie attributes; enforced only on cookie-authenticated mutating endpoints; API-token endpoints are immune (token not ambient).

**Implementation:**

```python
# FastAPI: DoubleSubmitCookie / SameSite=Lax + Origin check
@app.middleware("http")
async def csrf_guard(request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.cookies.get("session"):
        if request.headers.get("sec-fetch-site") == "cross-site": return JSONResponse(403, ...)
        if request.headers.get("x-csrf-token") != request.cookies.get("csrf"): return JSONResponse(403, ...)
```

**FastAPI Example:** Set session cookie `SameSite=Lax, HttpOnly, Secure`; CSRF token cookie + `X-CSRF-Token` header on mutations; SPA reads csrf cookie and echoes in header.

**Production Example:** Banking portal switched to `SameSite=Lax` cookies + `X-CSRF-Token` echo; a reported forged-transfer PoC now fails with 403; annual pentest clean.

**Failure Scenarios:** SameSite=None + Secure but no token â†’ CSRF open (some browsers still allow top-level POST nav); CSRF middleware exempts `/webhooks` but not checking signatures (unauthenticated but forged-ish â€” verify HMAC); token in URL (leaks via referer); GET endpoint mutating state (CSRF-anything, also a cache-poisoning hazard); relying on Referer checks alone; webhook cookies inherited from parent domain (`Domain=.example.com`) across apps.

**Best Practices:** SameSite=Lax default; cookies HttpOnly+Secure; double-submit token for SPAs; custom header + preflight; Sec-Fetch-Site checks where available; never mutate on GET; don't rely on one layer (defense in depth); verify webhook signatures instead of cookies.

**Anti-Patterns:** Cookie session without any CSRF protection; CSRF token static per user; token in form URL/logs; exempting "trusted" endpoints; CORS `*` with credentials (`#76`) re-opening it.

**Trade-offs:** Performance (token check ~Âµs); complexity (minor; SameSite covers most); cost (free); consistency (token issued per session); maintainability (framework support, one middleware).

**Testing:** Forged cross-site POST with victim cookies â†’ 403; missing header â†’ 403; SameSite behavior in Playwright E2E from a different origin; Sec-Fetch-Site injection test; webhook signature test.

**Related Concepts:** `#76 CORS`, `#69 OAuth`, `#79 XSS` (XSS defeats CSRF defenses â€” token read by script), `#71 TLS`.

**Decision Criteria:** Use when: any cookie-authenticated mutation endpoint. Do not use when: stateless bearer-token APIs (no ambient authority) â€” still verify CSRF not applicable. Alternatives: SameSite=Strict for high-security apps; BFF pattern; request-signing for non-browser clients.

### 78. SQL Injection

**Definition:** An attack in which untrusted input is concatenated into a SQL string and alters the query's structure â€” reading, corrupting, or deleting data and sometimes escalating to OS commands.

**Problem:** `' OR '1'='1` and worse are still among the most exploited web vulnerabilities; one tainted parameter can dump the whole database and bypass auth.

**Internal Working:** SQL is a language; when data becomes part of the syntax, the parser treats it as instructions. Parameterized queries (prepared statements) send text and data through **separate channels** â€” the server compiles the plan with literal binding, so input can never become syntax. ORMs using bound parameters are safe by construction; string interpolation (`f"SELECT ... WHERE id = {uid}"`), `.execute(text(f"...{x}..."))` with f-strings, and hand-built raw SQL are the classic offenders. Second-order injection: stored value (profile name) later interpolated into another query â€” same rule, harder to spot.

**Architecture:** Data access layer â€” everywhere SQL is built. Defenses: parameters, least-privilege DB role (app role has no DDL), errors not leaking schema, WAF as backstop only.

**Implementation:**

```python
# UNSAFE
session.execute(text(f"SELECT * FROM users WHERE email = '{email}'"))
# SAFE â€” bound parameter
session.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email})
stmt = select(User).where(User.email == email)          # ORM binds params
```

DB role: `GRANT SELECT, INSERT, UPDATE ON ...` only â€” no DROP/TRUNCATE; separate migration role.

**FastAPI Example:** Pydantic coerces `user_id: int` before the query â€” most injection is input-typing plus parameter binding; raw SQL must use bind params; `escape()` is **not** a substitute for parameters.

**Production Example:** Legacy search endpoint concatenated `q` into LIKE; attacker read `pg_stat_activity` and dumped `users` via `UNION SELECT`; fixed in 4 hours with bind params + statement logging alert; role trimmed to SELECT/INSERT only.

**Failure Scenarios:** Partial parameterization (one raw fragment among bound ones); `IN (:list)` with expansion mistakes reintroducing raw SQL; ORDER BY/column name unparameterizable (validate against allowlist); dynamic table names (allowlist + quoting if unavoidable); stored-procedure string exec (`sp_executesql` with concatenated SQL); leaking raw DB errors (stack traces with query text) to users.

**Best Practices:** Bind parameters for every value; allowlist identifiers; ORM-first; least-privilege DB role (no DDL, no superuser); error sanitization; code review grep for f-strings near SQL; sqlmap in CI; WAF CRS as backstop; audit dynamic SQL with a registry.

**Anti-Patterns:** String-built queries anywhere; `LIKE` escaping confusion ("I escaped quotes, so it's fine"); trusting ints from path params without typing; app role = postgres superuser; raw error pages; believing ORM = immune (raw fragments remain possible).

**Trade-offs:** Performance (prepared statements often faster â€” plan reuse); complexity (bind discipline); cost (free); consistency (n/a); maintainability (ORM makes it structural).

**Testing:** sqlmap against staging endpoints; fuzz path params with `' OR 1=1--`, `\x00`, `UNION SELECT`; CI pre-commit grep for f-string SQL patterns; integration test asserting errors don't leak query text; least-privilege role verification test.

**Related Concepts:** `#74 WAF` (backstop only), `#26 Query Optimization` (EXPLAIN safe? no â€” injection â‰  performance), `#79 XSS` (same input-trust class), `#68 IAM` (DB role least privilege).

**Decision Criteria:** Use when: always â€” parameterization is the only acceptable pattern. Do not use when: n/a. Alternatives: ORM suffices for most; for reporting, read-only replica + parameterized SQL; for structure changes, allowlists.

### 79. XSS

**Definition:** Cross-Site Scripting â€” injecting attacker-controlled script into pages other users render; stored (persisted in DB, hits everyone), reflected (echoed in the response), or DOM-based (client-side templates write untrusted data into innerHTML).

**Problem:** A single stored XSS payload in a comment steals every viewer's session, keystrokes, and CSRF tokens; token theft happens *as* the victim, so all their permissions are the attacker's.

**Internal Working:** Browser parses HTML; any script in the page executes with the page's origin privileges. Defenses: **context-aware output encoding** (HTML entity, attribute, JS, URL, CSS contexts â€” different escaping for each), templating engines with autoescaping on by default (Jinja2, React, Vue), **Content Security Policy** (`script-src 'self'` without `unsafe-inline` â€” kills inline XSS even if injection lands), Trusted Types, disabling inline events, sanitization only for rich HTML (DOMPurify or server-side bleach â€” never hand-rolled regex), `HttpOnly` cookies so JS can't read the session even on successful injection.

**Architecture:** Rendering layer (templates/SPA) + response headers + cookie flags. CSP report-only first, then enforce.

**Implementation:**

```python
# Jinja2: {{ user_comment }} auto-escapes; |safe disables it â€” audit every use
from bleach.sanitizer import Cleaner
cleaner = Cleaner(tags=["p","b","i","a"], attributes={"a": ["href"]}, protocols=["https"])
safe_html = cleaner.clean(user_html)
```

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; report-uri /csp-report" always;
```

**FastAPI Example:** Templates with autoescape (default for .html); JSON APIs are mostly XSS-immune for the API itself, but SPA consuming them must use `textContent`/`innerText` never `innerHTML`; markdown rendered with `bleach`/`markdown` + sanitizer; `HttpOnly, Secure, SameSite` cookies.

**Production Example:** Community feature shipped comment render with `|safe` + unsanitized HTML â†’ stored XSS stole sessions of 12k users; remediated: autoescape restored, DOMPurify on client, CSP enforced (inline blocked), tokens rotated; 3 days incident + notification.

**Failure Scenarios:** Autoescape disabled "for convenience"; CSP with `unsafe-inline` (no protection); sanitizing for HTML but rendering into JS context (`const x = "{{ value }}"`) without JS-escaping; DOM XSS via `innerHTML` in a dashboard widget; JSON response consumed with `eval`/`innerHTML` (rare but real); CSP report-only forgotten; markdown parser allowing raw HTML passthrough.

**Best Practices:** Autoescape everywhere; audit every `|safe`; CSP without unsafe-inline; sanitize rich HTML with DOMPurify/bleach; HttpOnly cookies; Trusted Types; security headers scan in CI; encode per-context; avoid `eval`; markdown with `escape_html`/allowlist tags.

**Anti-Patterns:** Regex "sanitizer"; innerHTML with user data; CSP as "we have one, it's report-only"; putting raw user input in `<script>` blocks; trusting markdown as safe by default.

**Trade-offs:** Performance (near-zero; CSP parsing cost trivial); complexity (CSP tuning for legacy apps); cost (free); consistency (headers at edge); maintainability (framework defaults do 90%).

**Testing:** OWASP ZAP/DAST scan; XSS payload corpus through comment/markdown fields; CSP evaluator (Google CSP Evaluator); Playwright test asserting injected script does not execute; audit `|safe`/innerHTML in code review; stored-XSS E2E on staging.

**Related Concepts:** `#77 CSRF` (XSS steals CSRF tokens â€” no HTTPOnly for those), `#78 SQL Injection`, `#76 CORS`, `#81` no. Also `#74 WAF` (backstop), `#72 Encryption at Rest` (token store hashing).

**Decision Criteria:** Use when: always â€” output encoding is universal. Do not use when: n/a. Alternatives: n/a (no single control is sufficient â€” encoding + CSP + HttpOnly is the standard bundle).

### 80. SSRF

**Definition:** Server-Side Request Forgery â€” tricking the server into making HTTP requests to destinations of the attacker's choosing: cloud metadata endpoints (169.254.169.254), internal services, or arbitrary external hosts.

**Problem:** The server is on the trusted side of the firewall; SSRF turns your app into an open proxy into your private network â€” the Capital One breach (~$190M reported) was SSRF â†’ metadata credentials â†’ S3 exfiltration.

**Internal Working:** Any feature fetching a URL from user input: webhooks, image proxies, link previews, PDF renderers, "import from URL". Attacker supplies `http://169.254.169.254/latest/meta-data/iam/security-credentials/` or `http://localhost:6379/` or `gopher://â€¦` to hit Redis. Defenses: **allowlist** of scheme (https) and host patterns; resolve DNS and check the resolved IP is routable public (not RFC1918/loopback/link-local) â€” including after redirects; block metadata IPs explicitly (cloud IRSa disables IMDSv1; use IMDSv2); network egress rules (app cannot reach 169.254.169.254); disable redirects or re-validate each hop; response size/time limits; don't return body contents to the attacker.

**Architecture:** App layer + egress proxy (allowlist enforced) + IMDSv2 + private DNS zoning. Webhook senders sit behind an egress allowlist.

**Implementation:**

```python
ALLOWED_SCHEMES = {"https"}
def safe_fetch(url: str):
    p = urlparse(url)
    assert p.scheme in ALLOWED_SCHEMES
    ips = getaddrinfo(p.hostname, None)   # resolve and check every IP
    for fam, _, _, _, (ip, *_) in ips:
        assert not ipaddress.ip_address(ip).is_private and ip != "169.254.169.254"
    return httpx.get(url, follow_redirects=False, timeout=5.0)  # validate each redirect too
```

Cloud: IMDSv2 required (token-based, defeats SSRF â†’ metadata); security group on app tier denying egress to metadata ranges; egress via proxy with domain allowlist for webhooks.

**FastAPI Example:** Webhook sender resolves + validates IP before POST, forbids redirects (or validates each hop), caps response read to 64KB, logs target host; "fetch preview" feature uses a headless browser in a locked-down sandbox with no network beyond allowlist.

**Production Example:** Link-preview microservice: egress proxy with allowlist of http(s) to non-private ranges + IMDSv2 on EC2 + response-body cap 128KB; a researcher's `169.254.169.254` test fails at the proxy and at name resolution; disclosed privately, bounty paid, zero data exposure.

**Failure Scenarios:** Validating the URL string before DNS resolution (DNS rebinding TOCTOU â€” attacker DNS returns public IP first, private on re-resolve); following redirects without re-validation; IPv6 `::1`/`::ffff:127.0.0.1` bypass; `0.0.0.0` and `2130706433` (decimal encoding of 127.0.0.1) bypass; blocking list but not allowlist (unknown encodings slip); returning internal error pages/bodies to users; webhook to `file://`/`gopher://`; open redirect in target used as single-hop SSRF.

**Best Practices:** Allowlist scheme+host; resolve and verify IP at connect time (not just validation time); block link-local/loopback/RFC1918/metadata IPs always; no user-controlled raw URLs without proxy; IMDSv2; egress proxy for webhooks; cap response size/time; never echo fetched bodies verbatim to the client; disable redirects or repeat validation; test with collaborator.

**Anti-Patterns:** Blacklist of bad hosts; validating hostname strings only; following redirects blindly; returning internal fetch errors/bodies to attacker; allowing any protocol (`file://`, `gopher://`, `dict://`); cloud instances with IMDSv1.

**Trade-offs:** Performance (extra DNS resolution + egress hop â€” small); complexity (defense in depth across app+network); cost (proxy infra); consistency (egress config drift across envs); maintainability (proxy allowlist as config).

**Testing:** Point SSRF test suite at app: `http://169.254.169.254/`, `http://127.0.0.1:22`, `http://[::1]/`, decimal/hex IP encodings, DNS-rebinding service (rebind.network) in staging; assert 400/403; webhook redrive drill; egress firewall rule tests in CI.

**Related Concepts:** `#71 TLS`, `#67 Secrets Management` (metadata creds are the prize), `#68 IAM` (role scoping limits blast radius), `#74 WAF`, `#80 SSRF` motivates `#5 API Gateways` egress controls.

**Decision Criteria:** Use when: any server-side URL fetch from user input â€” always apply. Do not use when: no user-controlled URLs exist (don't over-engineer). Alternatives: fully client-side fetching (browser does it, server never sees URL), dedicated isolated fetch service with locked egress, HEAD-only pre-validation.

<!--END-->

