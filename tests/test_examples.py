"""Example verification — static + in-process execution checks.

Live network/broker tests are intentionally absent from CI (no broker on the runner);
they were run manually and documented in the README release notes. These tests keep
examples honest on every push: they compile, declare the right topology, avoid
unsafe configs, and execute the FastAPI app in-process.
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EX = REPO / "examples"

# ---------- FastAPI example: in-process execution ----------

fastapi = pytest.importorskip("fastapi", reason="example requirements not installed")
from fastapi.testclient import TestClient

sys.path.insert(0, str(EX / "fastapi"))

from app import app as fastapi_app  # noqa: E402

client = TestClient(fastapi_app)


def test_healthz_readyz_ok():
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["status"] == "ready"


def test_metrics_exported():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text


def test_echo_validation_and_idempotency():
    # missing Idempotency-Key
    r = client.post("/echo", json={"text": "hi"})
    assert r.status_code == 422
    # empty text
    r = client.post(
        "/echo", json={"text": ""}, headers={"Idempotency-Key": "audit-check-1"}
    )
    assert r.status_code == 422
    # oversized text
    r = client.post(
        "/echo", json={"text": "a" * 4001}, headers={"Idempotency-Key": "audit-check-2"}
    )
    assert r.status_code == 422
    # replay yields identical body without double side effect
    r1 = client.post(
        "/echo", json={"text": "audit"}, headers={"Idempotency-Key": "audit-check-3"}
    )
    r2 = client.post(
        "/echo", json={"text": "audit"}, headers={"Idempotency-Key": "audit-check-3"}
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert "X-Request-Id" in r1.headers


# ---------- Agent orchestrator: stub-LLM harness ----------

AGENT = EX / "ai-agent-systems"
sys.path.insert(0, str(AGENT))
import agent as A  # noqa: E402
import asyncio


class StubLLM(A.LLMClient):
    def __init__(self, scripted):
        self.scripted = scripted

    async def decide(self, state):
        action = self.scripted[state.steps]
        if isinstance(action, tuple):
            return action
        return action, 10, 0.001


def test_agent_happy_path_and_budget_limit():
    async def run_case():
        tools = {"search": lambda **k: {"hits": 1}}
        ex = A.ToolExecutor(tools)
        llm = StubLLM(
            [
                (A.AgentAction(kind="tool", tool="search", args={"q": "x"}), 10, 0.001),
                A.AgentAction(kind="finish", final_answer="done"),
            ]
        )
        s = await A.run("task", llm, ex)
        assert s.done and s.steps == 2
        # infinite planner must hit the step budget
        llm = StubLLM([A.AgentAction(kind="tool", tool="search", args={})] * 50)
        with pytest.raises(A.BudgetExceeded):
            await A.run(
                "loop",
                llm,
                ex,
                A.Budget(
                    max_steps=3, max_wall_time_s=60, max_tokens=10**9, max_cost_usd=10
                ),
            )

    asyncio.run(run_case())


def test_agent_kill_switch_and_approval_gate(monkeypatch):
    async def run_case():
        A.KILL_SWITCH["halted"] = True
        llm = StubLLM([A.AgentAction(kind="finish", final_answer="never")])
        with pytest.raises(A.KilledBySwitch):
            await A.run("blocked", llm, A.ToolExecutor({}))
        A.KILL_SWITCH["halted"] = False
        llm = StubLLM([A.AgentAction(kind="tool", tool="send_email", args={"to": "x"})])
        with pytest.raises(A.KilledBySwitch):
            await A.run(
                "approve", llm, A.ToolExecutor({"send_email": lambda **k: "sent"})
            )

    asyncio.run(run_case())


# ---------- RabbitMQ example: static topology and safety checks ----------


def test_producer_declares_quorum_and_dlx():
    src = (EX / "distributed-systems" / "producer.py").read_text(encoding="utf-8")
    assert "x-queue-type" in src and "quorum" in src
    assert "x-delivery-limit" in src
    assert "x-dead-letter-exchange" in src


def test_worker_acks_after_work_and_bounds_prefetch():
    src = (EX / "distributed-systems" / "worker.py").read_text(encoding="utf-8")
    assert "basic_ack" in src
    assert "basic_qos" in src
    assert "auto_ack=False" in src


def test_compose_binds_localhost_only_and_no_host_amqp():
    src = (EX / "distributed-systems" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "127.0.0.1:8000" in src
    assert "127.0.0.1:15672" in src
    assert "5672:5672" not in src  # broker never published to the host


def test_dockerfile_runs_non_root():
    src = (EX / "distributed-systems" / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"(?im)^USER ", src)
    assert "root" not in re.search(r"(?im)^USER .*", src).group(0).lower()


def test_python_files_compile():
    for p in EX.rglob("*.py"):
        subprocess.run([sys.executable, "-m", "py_compile", str(p)], check=True)
