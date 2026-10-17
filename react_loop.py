"""ReAct loop: the agent alternates Thought -> Action -> Observation until it answers or runs out of budget.

The loop is model-agnostic. Each turn it calls `decide(query, history)`, which returns a Step that is
either a tool call (`action` + `action_input`) or a final answer. Stops when:
  ANSWERED      decide() returned a final answer
  TOKEN_BUDGET  cumulative tokens reported by decide() reached max_tokens
  TIMEOUT       wall-clock time reached timeout_s (checked between steps)
  MAX_ATTEMPTS  decide() was called max_attempts times without an answer
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from user_query_proto import UserQuery


class StopReason(str, Enum):
    ANSWERED = "answered"
    TOKEN_BUDGET = "token_budget"
    TIMEOUT = "timeout"
    MAX_ATTEMPTS = "max_attempts"


@dataclass
class Step:
    thought: str = ""
    action: str | None = None           # tool name; None when final_answer is set
    action_input: dict = field(default_factory=dict)
    final_answer: str | None = None
    tokens_used: int = 0                # tokens this decide() call consumed
    observation: str | None = None      # filled in by the loop after running the tool
    context: list = field(default_factory=list)  # model items to replay next turn (e.g. reasoning + tool call)


@dataclass
class LoopResult:
    answer: str | None                  # None unless stop_reason is ANSWERED
    stop_reason: StopReason
    steps: list[Step]
    tokens_used: int
    elapsed_s: float


Decide = Callable[[UserQuery, list[Step]], Step]


def run_tool(step: Step, tools: dict[str, Callable[..., str]]) -> str:
    """Run the requested tool and return its observation. Errors become observations, never exceptions."""
    if step.action not in tools:
        return f"Error: unknown tool '{step.action}'. Available tools: {', '.join(sorted(tools))}"
    try:
        return str(tools[step.action](**step.action_input))
    except Exception as exc:  # the agent should see the failure and try something else
        return f"Error: {step.action} failed: {exc}"


def run_react_loop(query: UserQuery, decide: Decide, tools: dict[str, Callable[..., str]],
                   max_attempts: int = 8, max_tokens: int = 20_000, timeout_s: float = 60.0,
                   clock: Callable[[], float] = time.monotonic) -> LoopResult:
    """Explore with tools until the agent answers or a budget (attempts, tokens, time) is exhausted."""
    start, steps, tokens = clock(), [], 0

    def result(reason: StopReason, answer: str | None = None) -> LoopResult:
        return LoopResult(answer, reason, steps, tokens, clock() - start)

    while True:
        if len(steps) >= max_attempts:
            return result(StopReason.MAX_ATTEMPTS)
        if tokens >= max_tokens:
            return result(StopReason.TOKEN_BUDGET)
        if clock() - start >= timeout_s:
            return result(StopReason.TIMEOUT)
        step = decide(query, steps)
        tokens += step.tokens_used
        steps.append(step)
        if step.final_answer is not None:
            return result(StopReason.ANSWERED, step.final_answer)
        if step.observation is None:  # decide() pre-fills an error (e.g. unparseable arguments): don't run the tool
            step.observation = run_tool(step, tools)
