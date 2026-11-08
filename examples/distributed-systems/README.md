# Example: Distributed System with RabbitMQ

Demonstrates the asynchronous backbone patterns from the skill: a producer API, a durable queue with dead-letter exchange, an idempotent worker, and replay.

## Run

```bash
cd examples/distributed-systems
docker compose up --build
```

Then:

```bash
# enqueue 20 jobs (all should be processed within seconds)
curl -X POST localhost:8000/enqueue -H 'Content-Type: application/json' -d '{"n": 20}'

# watch the worker consume them
docker compose logs -f worker

# verify the queue drained
docker compose exec rabbitmq rabbitmqctl list_queues name messages

# simulate a failing job: publishes {"fail": true}; after 5 redeliveries it lands in jobs-dlq
curl -X POST localhost:8000/fail -H 'Content-Type: application/json'
docker compose exec rabbitmq rabbitmqctl list_queues name messages

# malformed message: goes straight to the DLQ
docker compose exec rabbitmq rabbitmqadmin publish routing_key=jobs payload='{bad json'
docker compose exec rabbitmq rabbitmqctl list_queues name messages
```

## What to note (maps to topics)

- Durable queue + persistent messages + DLX wired at declare time (`topics/015`, `topics/020`)
- `acks_late`-style ack-after-work in the consumer (ack only after the side effect committed)
- Worker is idempotent on `job_id` — redelivery is safe (`topics/014`)
- Prefetch bounded (`topics/044`) — the consumer can never buffer unboundedly
- No Redis PUBLISH for work that must not be lost — durable queue only

## Files

`docker-compose.yml` · `producer.py` · `worker.py`
