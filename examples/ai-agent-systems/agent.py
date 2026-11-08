"""Reference agent orchestrator skeleton.

Provider-agnostic: implement `LLMClient.decide` for your gateway (OpenAI, Anthropic,
vLLM, Bedrock...). Everything else — budgets, idempotency, approvals, kill switch — is real.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel


class AgentAction(BaseModel):
    kind: Literal["tool", "finish"]
    tool: str | None = None
    args: dict[str, Any] | None = None
    final_answer: str | None = None


class BudgetExceeded(Exception):
    pass


class KilledBySwitch(Exception):
    pass


@dataclass
class RunState:
    run_id: str
    task: str
    steps: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    started: float = field(default_factory=time.time)
    journal: list[dict] = field(default_factory=list)
    done: bool = False


KILL_SWITCH = {
    "halted": False
}  # prod: feature flag store; flip = halt new runs + cancel in-flight


def is_killed() -> bool:
    return KILL_SWITCH.get("halted", False)


class Budget:
    def __init__(
        self,
        max_steps: int = 25,
        max_wall_time_s: float = 300,
        max_tokens: int = 200_000,
        max_cost_usd: float = 0.50,
    ):
        self.max_steps, self.max_wall_time_s = max_steps, max_wall_time_s
        self.max_tokens, self.max_cost_usd = max_tokens, max_cost_usd

    def check(self, s: RunState) -> None:
        if s.steps >= self.max_steps:
            raise BudgetExceeded("max_steps")
        if time.time() - s.started > self.max_wall_time_s:
            raise BudgetExceeded("wall_time")
        if s.tokens_used >= self.max_tokens:
            raise BudgetExceeded("tokens")
        if s.cost_usd >= self.max_cost_usd:
            raise BudgetExceeded("cost")


APPROVAL_TOOLS = {"send_email", "charge_card", "delete_records", "deploy"}


def policy_gate(action: AgentAction, state: RunState) -> None:
    if action.kind == "tool" and action.tool in APPROVAL_TOOLS:
        approved = human_approve(
            action, state
        )  # prod: UI + queue signal; timeout = auto-abort
        if not approved:
            raise KilledBySwitch(f"approval rejected for {action.tool}")


def human_approve(action: AgentAction, state: RunState) -> bool:
    # reference impl for demo — always routes to a human in real deployments
    print(
        f"[APPROVAL REQUIRED] run={state.run_id} tool={action.tool} args={action.args}"
    )
    return os.environ.get("AGENT_AUTO_APPROVE") == "1"


class LLMClient:
    async def decide(self, state: RunState) -> tuple[AgentAction, int, float]:
        raise NotImplementedError  # return (action, tokens_used, cost_usd)


class ToolExecutor:
    def __init__(self, tools: dict[str, Callable[..., Any]]):
        self.tools = tools
        self._seen: set[str] = set()  # prod: Redis SET NX PX idempotency keys

    async def execute(self, action: AgentAction, state: RunState) -> Any:
        key = hashlib.sha256(
            f"{state.run_id}:{state.steps}:{action.tool}:{json.dumps(action.args, sort_keys=True)}".encode()
        ).hexdigest()
        if key in self._seen:
            return {"status": "duplicate_suppressed"}
        result = await asyncio.to_thread(self.tools[action.tool], **(action.args or {}))
        self._seen.add(key)
        return result


async def run(
    task: str, llm: LLMClient, executor: ToolExecutor, budget: Budget | None = None
) -> RunState:
    budget = budget or Budget()
    state = RunState(run_id=hashlib.sha256(os.urandom(16)).hexdigest()[:16], task=task)
    while not state.done:
        if is_killed():
            raise KilledBySwitch("kill switch active")
        budget.check(state)
        action, tokens, cost = await asyncio.wait_for(llm.decide(state), timeout=120)
        state.tokens_used += tokens
        state.cost_usd += cost
        state.steps += 1
        policy_gate(action, state)
        if action.kind == "finish":
            state.journal.append({"step": state.steps, "final": action.final_answer})
            state.done = True
            break
        result = await executor.execute(action, state)
        state.journal.append(
            {"step": state.steps, "action": action.model_dump(), "result": result}
        )
    return state
