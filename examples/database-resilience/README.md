# Example: Database Resilience

Runnable, disposable Postgres that teaches four production patterns.

| Pattern | What it proves | Topics |
|---|---|---|
| Server-side `statement_timeout` | A runaway query is aborted by the database, not by your patience | `topics/011-timeouts.md`, `topics/026-query-optimization.md` |
| Deadlock detection + victim retry | Two rival transactions, both complete | `topics/040-deadlocks.md`, `topics/036-optimistic-locking.md` |
| Idempotent writes (`ON CONFLICT DO NOTHING`) | Replaying the same operation changes nothing | `topics/014-idempotency.md` |
| Connect + select against a live pool | Fresh connections work; what to alert on when they don't | `topics/028-connection-pooling.md`, `topics/056-health-checks.md` |

## Layout

```
database-resilience/
├── README.md
├── docker-compose.yml        # postgres 16-alpine, binds 127.0.0.1:55432 only
├── requirements.txt          # psycopg[binary] (pinned range)
└── resilience_demo.py        # the four proofs, prints PASS/FAIL
```

## Run It

```bash
cd examples/database-resilience
docker compose up -d
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python resilience_demo.py
```

Expected tail:

```
statement_timeout PASS ...
deadlock_retry PASS ...
idempotent_insert PASS ...
connection_retry PASS ...
RESULT: ALL PASS
```

## Failure Drills

1. **`docker compose stop postgres` mid-demo** → connection refused → app reconnects after `docker compose start postgres`.
2. **Run `SELECT pg_sleep(10)`** → aborted at 3s by server-side `statement_timeout`.
3. **Two shells, inverted row-lock order** → one sees `40P01 deadlock detected`; victim retries; both finish.
4. **Replay any committed write** → zero rows changed — the shape of a safe retry story.

## Security Notes

- `POSTGRES_PASSWORD` in `docker-compose.yml` is a **local throwaway**, not for any shared environment. It protects nothing — the port is bound to `127.0.0.1` on a non-default port (55432) to avoid clashing with any local Postgres on 5432.
- `statement_timeout=3000` is deliberately aggressive for the demo — tune per workload.

## Cleanup

```bash
docker compose down -v   # removes container AND the demo database volume
```

Tables are recreated idempotently on each run; data is wiped per demo — do not point this at real data.
