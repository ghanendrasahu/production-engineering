import json
import uuid

import pika
from fastapi import FastAPI
from pydantic import BaseModel, Field

RABBIT = "rabbitmq"


def channel():
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=RABBIT, heartbeat=30))
    ch = conn.channel()
    ch.exchange_declare(exchange="dlx", exchange_type="direct", durable=True)
    ch.queue_declare(queue="jobs-dlq", durable=True)
    ch.queue_bind(queue="jobs-dlq", exchange="dlx", routing_key="jobs")
    ch.queue_declare(
        queue="jobs",
        durable=True,
        arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "jobs",
            "x-max-length": 100_000,
        },
    )
    return conn, ch


app = FastAPI(title="jobs-producer")
_conn, _ch = channel()


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


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
