"""OpenAI-backed decide() for the ReAct loop, plus a small CLI.

The API key is read only through config.get_openai_api_key() (env var or the gitignored .env) and handed
straight to the OpenAI client. It is never stored on a Step/LoopResult, printed or logged.

  python llm_decide.py "Hello, may I ask for my lease renewal? Is there any discount available"
"""
from __future__ import annotations

import json
import os

from react_loop import Decide, Step
from user_query_proto import UserQuery

DEFAULT_MODEL = "gpt-6-luna"  # override with OPENAI_MODEL in the environment or .env
SYSTEM_PROMPT = (
    "You are a property-management assistant answering apartment residents. Use the tools when you need facts. "
    "Never invent prices, dates, names or policies: if you do not have the information, say so and offer to "
    "connect the resident with the leasing office. Answer briefly and politely.")


def build_messages(query: UserQuery, history: list[Step]) -> list[dict]:
    """Chat messages: system prompt, the classified query, then each earlier tool call and its observation."""
    known = {k: getattr(query, k) for k in ("incident_type", "intent", "urgency", "property_id", "unit_id")}
    facts = ", ".join(f"{k}={getattr(v, 'value', v)}" for k, v in known.items() if v)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"[{facts}]\n{query.text}"}]
    for i, step in enumerate(history):
        call_id = f"call_{i}"
        messages.append({"role": "assistant", "content": step.thought or None, "tool_calls": [
            {"id": call_id, "type": "function",
             "function": {"name": step.action, "arguments": json.dumps(step.action_input)}}]})
        messages.append({"role": "tool", "tool_call_id": call_id, "content": step.observation or ""})
    return messages


def make_openai_decide(tool_specs: list[dict] | None = None, model: str | None = None, client=None) -> Decide:
    """Return a decide() that asks OpenAI for the next Step: one tool call, or the final answer."""
    if client is None:
        from openai import OpenAI  # imported lazily so tests run without the package or a key
        from config import get_openai_api_key, load_env_file
        client = OpenAI(api_key=get_openai_api_key())
        model = model or os.environ.get("OPENAI_MODEL") or load_env_file().get("OPENAI_MODEL")
    model = model or DEFAULT_MODEL

    def decide(query: UserQuery, history: list[Step]) -> Step:
        kwargs = {"tools": tool_specs} if tool_specs else {}
        response = client.chat.completions.create(model=model, messages=build_messages(query, history), **kwargs)
        message, tokens = response.choices[0].message, response.usage.total_tokens
        if message.tool_calls:  # take one tool call per step; the loop runs it and calls us again
            call = message.tool_calls[0]
            return Step(thought=message.content or "", action=call.function.name,
                        action_input=json.loads(call.function.arguments or "{}"), tokens_used=tokens)
        return Step(final_answer=message.content or "", tokens_used=tokens)

    return decide


if __name__ == "__main__":
    import sys

    from query_conversion import convert_message
    from react_loop import run_react_loop

    result = run_react_loop(convert_message(" ".join(sys.argv[1:])), make_openai_decide(), tools={})
    print(f"[{result.stop_reason.value}, {result.tokens_used} tokens, {result.elapsed_s:.1f}s]")
    print(result.answer or "(no answer - hand off to the leasing office)")
