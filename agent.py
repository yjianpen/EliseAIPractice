"""One conversational exchange: raw message in, answer out, remembered per user for the memory window.

Chat locally (needs OPENAI_API_KEY in .env); the agent remembers your last 2 hours within this session:
  python agent.py T-00001       # a tenant_id from data/synthetic/tenants.csv; the agent can query their records
"""
from __future__ import annotations

from conversation_memory import ConversationMemory
from query_conversion import convert_message
from react_loop import Decide, LoopResult, run_react_loop


def respond(text: str, user_id: str, memory: ConversationMemory, decide: Decide,
            tools: dict | None = None, **loop_limits) -> LoopResult:
    """Run the ReAct loop for this user's message, then store the message and the answer in their memory.

    `decide` should read the same memory (e.g. make_openai_decide(memory=memory)). Turns are stored after
    the loop, so the current message is never duplicated in its own prompt.
    """
    result = run_react_loop(convert_message(text, tenant_id=user_id), decide, tools or {}, **loop_limits)
    memory.add(user_id, "user", text)
    if result.answer:
        memory.add(user_id, "assistant", result.answer)
    return result


if __name__ == "__main__":
    import sys

    from db_tools import make_db_tools
    from llm_decide import make_openai_decide

    user_id = sys.argv[1] if len(sys.argv) > 1 else "T-00001"
    memory = ConversationMemory()
    tools, tool_specs = make_db_tools(user_id)  # query_db, locked to this resident's own records
    decide = make_openai_decide(tool_specs=tool_specs, memory=memory)
    print(f"Chatting as {user_id}. Empty line or Ctrl-D to quit.")
    try:
        while text := input("you> ").strip():
            r = respond(text, user_id, memory, decide, tools)
            print(f"agent> {r.answer or '(no answer - hand off to the leasing office)'}  [{r.stop_reason.value}]")
    except (EOFError, KeyboardInterrupt):
        print()
