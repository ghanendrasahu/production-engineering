# Backend Engineering Reference (FastAPI / Python Request Path)

The practical operating picture for Python backend services — how a request flows through a production FastAPI app, where the 111 topics attach, and the checks that catch what review misses.

## The Production Request Path

```
client → TLS edge/CDN → reverse proxy (Nginx/Envoy)
  → gateway (authN, rate limit, quota)          # topics 1-5
  → FastAPI app:
      middleware(s)         (trace_id, timing, metrics, redaction)
      route → dependencies  (DI: db session, flags, current_user)
      Pydantic validation   (422 before touching data)
      service layer         (business logic, transactions)
      repositories          (SQLAlchemy, parameterized)
  → Postgres (pool via PgBouncer) / Redis / broker
```

Every arrow is a boundary — this is where controls live (auth, timeouts, validation, idempotency).

## FastAPI-Specific Controls (with the topic numbers to read next)

| Concern | Where it lives | Read next |
| --- | --- | --- |
| Input validation | Pydantic models on every route; `model_config = ConfigDict(extra='forbid')` on external payloads | `topics/`, `../topics/076-cors.md` |
| AuthN/Z | Dependency (`CurrentUser = Depends(require_user)`) + gateway JWT verification | `topics/069-oauth.md`, `topics/070-jwt-rotation.md`, `topics/068-iam.md` |
| Request timeouts | `asyncio.wait_for` per external call; budget table per route | `topics/011-timeouts.md` |
| DB sessions | One engine per process; `get_db` yields session, closes in `finally`; `pool_pre_ping=True` | `topics/028-connection-pooling.md` |
| Transactions | `with session.begin():` around multi-statement writes; short; no I/O inside | `topics/037-pessimistic-locking.md`, `topics/039-race-conditions.md` |
| Errors | Typed exceptions → handlers → consistent `{code, message, trace_id}`; never leak internals | `topics/059-logging.md` |
| Logs | structlog JSON: `request_id`, `trace_id`, `route`, `status`, `duration_ms` | `topics/059-logging.md` |
| Metrics | prometheus-client: `http_requests_total{route,status}`, latency histogram buckets | `topics/061-metrics.md` |
| Health | `/healthz` (process-only) + `/readyz` (DB/Redis, 1s deadline) | `topics/056-health-checks.md`, `topics/057-liveness-and-readiness-probes.md` |
| Background work | Celery/Arq/Dramatiq for anything > the HTTP budget | `topics/015-message-queues.md`, `topics/020-dead-letter-queues.md` |
| Rate limits | Redis Lua token bucket dependency or gateway rule; 429 + `Retry-After` | `topics/001-rate-limiting.md` |
| Idempotency | `Idempotency-Key` header → Postgres/Redis dedupe in the same transaction as the write | `topics/014-idempotency.md` |
| Streaming (LLM) | `StreamingResponse` + SSE; `X-Accel-Buffering: no`; heartbeat comments; cancel upstream on disconnect | `topics/024-server-sent-events.md`, `../references/ai-engineering.md` |
| Config | pydantic-settings `BaseSettings` from env; fail fast on missing required keys | `topics/067-secrets-management.md` |
| Tests | pytest + httpx AsyncClient; per-dependency overrides; Testcontainers for real Postgres/Redis | `references/testing.md` |

## Python Pitfalls That Bite in Production

- **Blocking the event loop**: sync SQLAlchemy or `time.sleep` inside `async def` stalls every request on the worker — use `run_in_executor`/sync endpoints (`def`) for blocking work, or async drivers (`asyncpg`, `asyncio` Redis).
- **Global mutable state** shared across requests/threads — confine or lock; prefer immutable DTOs (`dataclass(frozen=True)`).
- **Unbounded middleware fanout**: one request triggering N downstream calls per incoming request (N+1 outward) — batch, cache, or collapse.
- **Naive datetime**: use timezone-aware UTC everywhere; `#96 Clock Skew` will find the ones you missed.
- **`print()` debugging** left in services — switch to redacted structured logs; CI should grep for `print(` in `app/`.

## Lifespan Pattern (the right skeleton)

```python
from contextlib import asynccontextmanager
import structlog, asyncio
from fastapi import FastAPI
from prometheus_client import make_asgi_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_engine = make_engine()          # pool_pre_ping=True
    app.state.redis = make_redis()               # decode_responses=True
    app.state.llm_semaphore = asyncio.Semaphore(8)
    yield
    await app.state.redis.aclose()
    await app.state.db_engine.dispose()

app = FastAPI(lifespan=lifespan, title="service")
app.mount("/metrics", make_asgi_app())           # expose Prometheus metrics
log = structlog.get_logger()
```

## Verification Checklist (15 minutes)

1. `grep -r "print(" app/` → expect none in production paths (or allowlisted).
2. Every outbound call has both connect and read timeout (`httpx.Timeout(connect=…, read=…)`) — audit by reading client usages.
3. `/healthz` + `/readyz` exist and are excluded from auth; `/readyz` checks DB and Redis with ≤1s deadlines.
4. No bare `except:`; no `except Exception: pass`.
5. DB session dependency closes sessions in `finally`; engine `pool_size` × worker count < Postgres `max_connections`.
6. Config loads from env at startup; missing required keys → process refuses to boot.
7. Metrics endpoint serves RED series; a recent request appears in the latency histogram.
