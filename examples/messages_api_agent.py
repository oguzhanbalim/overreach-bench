"""Adapter from the bench to a real tool-use loop on the Messages API.

Not run live by this repository. There was no API key where it was written, so its only test
drives it with a scripted fake client. Treat it as a starting point and read the first traces
by hand. Running it spends tokens: the corpus is 24 scenarios x 2 languages x 2 framings x runs.

    pip install anthropic
    export OVERREACH_API_KEY=...
    export OVERREACH_MODEL=...
    overreach-bench run --agent examples/messages_api_agent.py:agent --runs 5 --show-overreach
"""

from __future__ import annotations

import os
from typing import Any

from overreach_bench.harness import Agent, AgentRequest


def _setting(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"set {name} to run this example")
    return value


def make_agent(
    client: Any = None, model: str | None = None, max_tokens: int = 4096, max_turns: int = 12
) -> Agent:
    def run(request: AgentRequest) -> str:
        sdk = client
        if sdk is None:
            import anthropic

            sdk = anthropic.Anthropic(api_key=_setting("OVERREACH_API_KEY"))
        chosen = model or _setting("OVERREACH_MODEL")
        tools = [tool.to_messages_api() for tool in request.tools]
        messages: list[dict[str, Any]] = [{"role": "user", "content": request.task}]
        for _ in range(max_turns):
            response = sdk.messages.create(
                model=chosen,
                max_tokens=max_tokens,
                system=request.system,
                tools=tools,
                messages=messages,
            )
            if response.stop_reason != "tool_use":
                return "".join(b.text for b in response.content if b.type == "text")
            messages.append({"role": "assistant", "content": response.content})
            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": request.call_tool(block.name, dict(block.input)),
                }
                for block in response.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": results})
        raise RuntimeError(f"no final answer after {max_turns} turns")

    return run


agent = make_agent()
