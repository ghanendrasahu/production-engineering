import hashlib
import logging
import os
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()


class Settings(BaseSettings):
    app_name: str = "notes-example"
    app_env: str = "dev"
    database_url: str = "sqlite+aiosqlite:///./example.db"
    max_inflight: int = 16


settings = Settings()
REQUESTS = Counter("http_requests_total", "requests", ["route", "status"])
LATENCY = Histogram("http_request_seconds", "latency", ["route"])

_idempotency_store: dict[
    str, dict
] = {}  # prod: Postgres/Redis with TTL — see topics/014


class EchoIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", app=settings.app_name, env=settings.app_env)
    yield
    log.info("shutdown")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


@app.middleware("http")
async def observe(request: Request, call_next):
    start = time.perf_counter()
    trace_id = (
        request.headers.get("x-request-id")
        or hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    )
    log.info(
        "request_in", trace_id=trace_id, path=request.url.path, method=request.method
    )
    response = await call_next(request)
    dur = time.perf_counter() - start
    LATENCY.labels(route=request.url.path).observe(dur)
    REQUESTS.labels(route=request.url.path, status=response.status_code).inc()
    response.headers["X-Request-Id"] = trace_id
    log.info(
        "request_out",
        trace_id=trace_id,
        status=response.status_code,
        duration_ms=round(dur * 1000, 1),
    )
    return response


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    # prod: SELECT 1 with 1s deadline + Redis PING; 503 on failure
    return {"status": "ready"}


@app.post("/echo")
async def echo(
    payload: EchoIn, idempotency_key: str = Header(..., min_length=8, max_length=200)
):
    if idempotency_key in _idempotency_store:
        return _idempotency_store[
            idempotency_key
        ]  # replay stored response; no double side effect
    result = {"echo": payload.text[::-1], "idempotency_key": idempotency_key}
    _idempotency_store[idempotency_key] = (
        result  # prod: INSERT ... ON CONFLICT in same tx as side effect
    )
    return result
