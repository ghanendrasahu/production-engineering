import json
import time

import pika

seen: set[str] = set()  # prod: Redis/Postgres with TTL — see topics/014-idempotency.md
r = None


def on_message(ch, method, props, body):
    try:
        msg = json.loads(body)
        job_id = msg["job_id"]
    except Exception:
        ch.basic_reject(
            method.delivery_tag, requeue=False
        )  # poison -> DLX after delivery limit
        return
    if job_id in seen:
        ch.basic_ack(method.delivery_tag)
        return
    try:
        time.sleep(0.05)  # simulate work
        seen.add(job_id)  # side effect (pretend) completed
        ch.basic_ack(method.delivery_tag)  # ack AFTER the work
    except Exception:
        ch.basic_nack(
            method.delivery_tag, requeue=True
        )  # broker redelivers; dies into DLQ after limit


def main():
    conn = pika.BlockingConnection(
        pika.ConnectionParameters(host="rabbitmq", heartbeat=30)
    )
    ch = conn.channel()
    ch.queue_declare(
        queue="jobs",
        durable=True,
        arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "jobs",
            "x-max-length": 100_000,
        },
    )
    ch.basic_qos(prefetch_count=10)  # bounded in-flight, no unbounded buffering
    ch.basic_consume(queue="jobs", on_message_callback=on_message, auto_ack=False)
    ch.start_consuming()


if __name__ == "__main__":
    main()
