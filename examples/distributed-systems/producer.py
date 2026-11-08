import json
import uuid

import pika
from fastapi import FastAPI
from pydantic import BaseModel, Field

RABBIT = "rabbitmq"


def connect(host: str = RABBIT, attempts: int = 30, delay_s: float = 2.0):
    import time

    for attempt in range(1, attempts + 1):
        try:
            return pika.BlockingConnection(
                pika.ConnectionParameters(host=host, heartbeat=30)
            )
        except Exception as e:
            if attempt == attempts:
                raise
            print(f"broker not ready (attempt {attempt}/{attempts}): {e}", flush=True)
            time.sleep(delay_s)
    raise RuntimeError("unreachable")


def channel():
    conn = connect()
    ch = conn.channel()
    ch.exchange_declare(exchange="dlx", exchange_type="direct", durable=True)
    ch.queue_declare(queue="jobs-dlq", durable=True)
    ch.queue_bind(queue="jobs-dlq", exchange="dlx", routing_key="jobs")
    ch.queue_declare(
        queue="jobs",
        durable=True,
        arguments={
            "x-queue-type": "quorum",  # quorum queues support x-delivery-limit
            "x-delivery-limit": 5,  # after 5 redeliveries the message is dead-lettered
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "jobs",
            "x-max-length": 100_000,
        },
    )
    return conn, ch


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    global _conn, _ch
    _conn, _ch = channel()  # connect on startup with retry, not at import
    yield
    try:
        _conn.close()
    except Exception:
        pass


app = FastAPI(title="jobs-producer", lifespan=lifespan)
_conn, _ch = None, None


class Job(BaseModel):
    n: int = Field(ge=1, le=10_000)


@app.post("/enqueue", status_code=202)
def enqueue(job: Job):
    for _ in range(job.n):
        _ch.basic_publish(
            exchange="",
            routing_key="jobs",
            body=json.dumps({"job_id": uuid.uuid4().hex}).encode(),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
    return {"enqueued": job.n}


@app.post("/fail", status_code=202)
def fail():
    _ch.basic_publish(
        exchange="",
        routing_key="jobs",
        body=json.dumps({"job_id": uuid.uuid4().hex, "fail": True}).encode(),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    return {"enqueued": 1, "kind": "failing"}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
