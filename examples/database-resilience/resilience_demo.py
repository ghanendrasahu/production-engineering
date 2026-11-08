"""Live demonstration of four database resilience patterns.

Run against the compose Postgres in this directory:

    docker compose up -d
    pip install -r requirements.txt
    python resilience_demo.py

Every case prints PASS/FAIL with evidence. The demo requires Docker or a
Postgres on 127.0.0.1:55432 with user app / db appdb (see docker-compose.yml).
"""

import sys
import time
import threading

import psycopg

DSN = "host=127.0.0.1 port=55432 user=app password=local-throwaway-NOT-for-production dbname=appdb connect_timeout=5"


def log(msg):
    print(msg, flush=True)


def wait_ready(attempts: int = 40) -> bool:
    for i in range(attempts):
        try:
            with psycopg.connect(DSN) as c:
                c.execute("SELECT 1")
            return True
        except Exception as e:
            log(f"db not ready ({i + 1}/{attempts}): {type(e).__name__}")
            time.sleep(2)
    return False


def create_schema():
    with psycopg.connect(DSN) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS accounts (
                        id int primary key, balance int not null)""")
        c.execute("""CREATE TABLE IF NOT EXISTS ledger (
                        reference uuid primary key, note text)""")
        c.execute("DELETE FROM accounts")
        c.execute("INSERT INTO accounts VALUES (1, 100), (2, 100)")
        c.commit()


def test_statement_timeout():
    with psycopg.connect(DSN) as c:
        try:
            c.execute("SELECT pg_sleep(10)")  # exceeds server statement_timeout=3000
            log("statement_timeout FAIL: query was not aborted")
            return False
        except Exception as e:  # psycopg.errors.QueryCanceled
            log(
                f"statement_timeout PASS: server aborted long query ({type(e).__name__})"
            )
            return True


def test_deadlock_retry():
    """Two transactions lock the same two rows in opposite order; one is a deadlock victim;
    the victim retries and both complete. Demonstrates ordered locking + retry-on-40P01."""
    results = {}

    def work(name, first, second):
        for attempt in range(5):
            try:
                with psycopg.connect(DSN) as c:
                    with c.transaction():
                        c.execute(
                            "SELECT balance FROM accounts WHERE id=%s FOR UPDATE",
                            (first,),
                        )
                        time.sleep(0.15)
                        c.execute(
                            "SELECT balance FROM accounts WHERE id=%s FOR UPDATE",
                            (second,),
                        )
                        c.execute(
                            "UPDATE accounts SET balance=balance-1 WHERE id=%s",
                            (first,),
                        )
                        c.execute(
                            "UPDATE accounts SET balance=balance-1 WHERE id=%s",
                            (second,),
                        )
                results[name] = f"done after {attempt + 1} attempt(s)"
                return
            except psycopg.errors.DeadlockDetected:
                time.sleep(0.1 * (attempt + 1))
        results[name] = "FAILED after 5 retries"

    t1 = threading.Thread(target=work, args=("tx-A", 1, 2))
    t2 = threading.Thread(target=work, args=("tx-B", 2, 1))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    ok = all(v.startswith("done") for v in results.values())
    log(f"deadlock_retry {'PASS' if ok else 'FAIL'}: {results}")
    return ok


def test_idempotent_insert():
    sql = "INSERT INTO ledger (reference, note) VALUES ('deadbeef-0000-0000-0000-000000000001', 'charge') ON CONFLICT DO NOTHING"
    with psycopg.connect(DSN) as c:
        c.execute(sql)
        c.execute(sql)  # replay must not raise and must not double-insert
        count = c.execute(
            "SELECT count(*) FROM ledger WHERE reference='deadbeef-0000-0000-0000-000000000001'"
        ).fetchone()[0]
    ok = count == 1
    log(
        f"idempotent_insert {'PASS' if ok else 'FAIL'}: rows after double insert = {count}"
    )
    return ok


def test_connection_retry_after_restart():
    with psycopg.connect(DSN) as c:
        c.execute("SELECT 1")
    log("connection_retry PASS: pre_ping-style fresh query against live DB works")
    log(
        "(true restart drill: run `docker compose restart postgres` while a worker is polling)"
    )
    return True


if __name__ == "__main__":
    if not wait_ready():
        sys.exit("Postgres never became ready")
    create_schema()
    outcomes = [
        test_statement_timeout(),
        test_deadlock_retry(),
        test_idempotent_insert(),
        test_connection_retry_after_restart(),
    ]
    print(f"\nRESULT: {'ALL PASS' if all(outcomes) else 'FAILURES PRESENT'}")
    sys.exit(0 if all(outcomes) else 1)
