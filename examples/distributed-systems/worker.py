import json
import sys
import time

import pika

seen: set[str] = set()  # prod: Redis/Postgres with TTL — see topics/014-idempotency.md


def on_message(ch, method, props, body):
    try:
        msg = json.loads(body)
        job_id = msg["job_id"]
    except Exception:
        ch.basic_reject(
            method.delivery_tag, requeue=False
        )  # malformed -> DLX immediately
        print("reject malformed -> DLQ", flush=True)
        return
    if job_id in seen:
        ch.basic_ack(method.delivery_tag)
        return
    if msg.get("fail"):
        print(f"job {job_id} simulated failure; will retry (limit 5)", flush=True)
        ch.basic_nack(
            method.delivery_tag, requeue=True
        )  # delivery-limit -> DLX after 5 tries
        return
    try:
        time.sleep(0.05)  # simulate work
        seen.add(job_id)
        ch.basic_ack(method.delivery_tag)  # ack AFTER the work
        print(f"job {job_id} done", flush=True)
    except Exception:
        ch.basic_nack(method.delivery_tag, requeue=True)


def main():
    conn = None
    for attempt in range(1, 31):
        try:
            conn = pika.BlockingConnection(
                pika.ConnectionParameters(host="rabbitmq", heartbeat=30)
            )
            break
        except Exception as e:
            print(f"broker not ready (attempt {attempt}/30): {e}", flush=True)
            time.sleep(2)
    if conn is None:
        raise SystemExit("could not connect to broker after 60s")
    ch = conn.channel()
    ch.queue_declare(
        queue="jobs",
        durable=True,
        arguments={
            "x-queue-type": "quorum",  # must match declaration in producer.py
            "x-delivery-limit": 5,
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "jobs",
            "x-max-length": 100_000,
        },
    )
    ch.basic_qos(prefetch_count=10)  # bounded in-flight, no unbounded buffering
    ch.basic_consume(queue="jobs", on_message_callback=on_message, auto_ack=False)
    print("worker consuming", flush=True)
    ch.start_consuming()


if __name__ == "__main__":
    sys.exit(main())
