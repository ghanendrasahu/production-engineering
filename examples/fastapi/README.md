# Example: FastAPI Production Skeleton

Minimal-but-real FastAPI service demonstrating the controls the skill mandates: lifespan-managed resources, health/readiness, structured logs, Prometheus metrics, pydantic-settings config, idempotent mutation endpoint.

## Layout

```
fastapi/
├── README.md
├── app.py          # the service
├── requirements.txt
└── .env.example
```

## Run

```bash
cd examples/fastapi
pip install -r requirements.txt
export APP_ENV=dev            # in prod: APP_ENV=prod DATABASE_URL=postgresql+asyncpg://...
uvicorn app:app --port 8000
curl localhost:8000/healthz
curl localhost:8000/readyz
open localhost:8000/metrics   # Prometheus exposition
curl -X POST localhost:8000/echo -H 'Idempotency-Key: abc123' -H 'Content-Type: application/json' -d '{"text":"hi"}'
curl -X POST localhost:8000/echo -H 'Idempotency-Key: abc123' -H 'Content-Type: application/json' -d '{"text":"hi"}'   # same response, no side effect twice
```

Production notes: swap the in-memory idempotency store for Postgres/Redis (`topics/014-idempotency.md`); run behind Nginx with `X-Accel-Buffering: no` if streaming; add alerts on `http_requests_total{status=~"5.."}` and p99 latency (`topics/061-metrics.md`).
