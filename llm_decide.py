"""OpenAI-backed decide() for the ReAct loop (Responses API: function tools + reasoning), plus a small CLI.

The API key is read only through config.get_openai_api_key() (env var or the gitignored .env) and handed
straight to the OpenAI client. It is never stored on a Step/LoopResult, printed or logged.

  python llm_decide.py "Hello, may I ask for my lease renewal? Is there any discount available"
"""
from __future__ import annotations

import json
import os
import warnings

from react_loop import Decide, Step
from user_query_proto import UserQuery

DEFAULT_MODEL = "gpt-6-luna"  # override with OPENAI_MODEL in the environment or .env
DEFAULT_EFFORT = "low"        # reasoning effort; override with OPENAI_REASONING_EFFORT (none/low/medium/high)
DEFAULT_FALLBACKS = "gpt-5.6-luna"  # tried in order if a model is retired; override with OPENAI_FALLBACK_MODELS
SYSTEM_PROMPT = (
    "You are a property-management assistant answering apartment residents. Use the tools when you need facts. "
    "Never invent prices, dates, names or policies: if you do not have the information, say so and offer to "
    "connect the resident with the leasing office. Answer briefly and politely.")


def build_input(query: UserQuery, history: list[Step], past_turns: list = ()) -> list:
    """Responses API input: this user's recent turns (conversation memory), the classified query, then each
    earlier tool call (replaying the model's own reasoning + function_call items) and its output."""
    known = {k: getattr(query, k) for k in ("incident_type", "intent", "urgency", "property_id", "unit_id")}
    facts = ", ".join(f"{k}={getattr(v, 'value', v)}" for k, v in known.items() if v)
    items = [{"role": t.role, "content": t.text} for t in past_turns]
    items.append({"role": "user", "content": f"[{facts}]\n{query.text}"})
    for i, step in enumerate(history):
        context = step.context or [{"type": "function_call", "call_id": f"call_{i}", "name": step.action,
                                    "arguments": json.dumps(step.action_input)}]
        call = context[-1]
        call_id = call["call_id"] if isinstance(call, dict) else call.call_id
        items += context + [{"type": "function_call_output", "call_id": call_id, "output": step.observation or ""}]
    return items


def create_with_fallbacks(client, models: list[str], request: dict):
    """Call client.responses.create, adapting to compatibility errors instead of failing the conversation:
    - reasoning not supported by this model/endpoint -> retry the same model without `reasoning`
    - model unknown, retired or unusable here        -> try the next model in `models`
    Any other error (auth, bad request, outage after the SDK's own retries) is raised unchanged."""
    last_error = None
    for model in models:
        attempt = dict(request, model=model)
        for _ in range(2):  # at most: as requested, then without reasoning
            try:
                return client.responses.create(**attempt)
            except Exception as exc:
                status, param = getattr(exc, "status_code", None), getattr(exc, "param", None) or ""
                message, last_error = str(exc).lower(), exc
                if "reasoning" in attempt and (param.startswith("reasoning") or "reasoning" in message):
                    warnings.warn(f"{model}: reasoning not supported here; retrying without it")
                    attempt.pop("reasoning")
                elif status == 404 or param == "model" or "model" in message and status == 400:
                    warnings.warn(f"{model} unavailable ({status}); trying the next fallback model")
                    break
                else:
                    raise
    raise last_error


def make_openai_decide(tool_specs: list[dict] | None = None, model: str | None = None, client=None,
                       memory=None, effort: str | None = None) -> Decide:
    """Return a decide() that asks OpenAI (Responses API) for the next Step: one tool call or the final answer.
    Tools work together with reasoning (`effort`). With a ConversationMemory, the input includes the query's
    tenant's turns from the memory window."""
    if client is None:
        from openai import OpenAI  # imported lazily so tests run without the package or a key
        from config import get_openai_api_key, load_env_file
        client, env = OpenAI(api_key=get_openai_api_key()), {**load_env_file(), **os.environ}
        model, effort = model or env.get("OPENAI_MODEL"), effort or env.get("OPENAI_REASONING_EFFORT")
        fallbacks = env.get("OPENAI_FALLBACK_MODELS", DEFAULT_FALLBACKS)
    else:
        fallbacks = ""
    if not hasattr(client, "responses"):
        raise RuntimeError("This openai package has no Responses API; run: pip install -U 'openai>=1.66'")
    models = [model or DEFAULT_MODEL] + [m.strip() for m in fallbacks.split(",") if m.strip()]
    effort = effort or DEFAULT_EFFORT

    def decide(query: UserQuery, history: list[Step]) -> Step:
        kwargs = {"tools": tool_specs} if tool_specs else {}
        past = memory.recent(query.tenant_id) if memory is not None and query.tenant_id else []
        request = dict(instructions=SYSTEM_PROMPT, reasoning={"effort": effort},
                       input=build_input(query, history, past), **kwargs)
        response = create_with_fallbacks(client, models, request)
        tokens = response.usage.total_tokens
        calls = [item for item in response.output if item.type == "function_call"]
        if calls:  # one tool call per step; keep the reasoning items so the next request can replay them
            call = calls[0]
            context = [item for item in response.output if item.type != "function_call" or item is call]
            return Step(action=call.name, action_input=json.loads(call.arguments or "{}"), tokens_used=tokens,
                        context=context)
        return Step(final_answer=response.output_text or "", tokens_used=tokens)

    return decide


if __name__ == "__main__":
    import sys

    from query_conversion import convert_message
    from react_loop import run_react_loop

    result = run_react_loop(convert_message(" ".join(sys.argv[1:])), make_openai_decide(), tools={})
    print(f"[{result.stop_reason.value}, {result.tokens_used} tokens, {result.elapsed_s:.1f}s]")
    print(result.answer or "(no answer - hand off to the leasing office)")
