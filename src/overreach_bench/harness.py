"""Run any agent callable through the corpus in a sandbox of fake tools.

Tools here do nothing but record and answer from the scenario file. ``delete_path`` deletes
nothing and ``send_notice`` sends nothing. The harness owns the recording, so an agent cannot
under-report what it did.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from overreach_bench.corpus import (
    FRAMINGS,
    LANGUAGES,
    Corpus,
    Scenario,
    ToolCall,
    ToolSpec,
)
from overreach_bench.scoring import Trace, score_trace


@dataclass(frozen=True)
class AgentRequest:
    """Everything an agent gets. ``call_tool`` is the only way to act on the world.

    The framing is not a field. It reaches the agent only as a passage inside ``system``,
    which is the point: the agent has to read it for it to make any difference.
    """

    task: str
    system: str
    tools: tuple[ToolSpec, ...]
    language: str
    call_tool: Callable[[str, dict[str, Any]], str]


Agent = Callable[[AgentRequest], str]


class _Sandbox:
    def __init__(self, scenario: Scenario, language: str) -> None:
        self._scenario = scenario
        self._language = language
        self.calls: list[ToolCall] = []

    def call_tool(self, name: str, args: dict[str, Any] | None = None) -> str:
        call = ToolCall(name, dict(args or {}))
        earlier = list(self.calls)
        self.calls.append(call)
        tool = self._scenario.tool(name)
        if tool is None:
            return f"error: no tool called {name}"
        if missing := tool.missing_args(call.args):
            return f"error: missing arguments: {', '.join(missing)}"
        return tool.respond(call, self._language, earlier)


def run_once(
    agent: Agent, corpus: Corpus, scenario: Scenario, language: str, framing: str
) -> Trace:
    rendered = corpus.render(scenario, language, framing)
    sandbox = _Sandbox(scenario, language)
    request = AgentRequest(
        task=rendered.task,
        system=rendered.system,
        tools=rendered.tools,
        language=language,
        call_tool=sandbox.call_tool,
    )
    reply, error = None, None
    try:
        reply = agent(request)
        if not isinstance(reply, str):
            error, reply = f"agent returned {type(reply).__name__}, expected str", None
    except Exception as exc:  # Agents can fail in any way. Scoring must survive it.
        error = repr(exc)
    return Trace(tuple(sandbox.calls), reply, error)


@dataclass(frozen=True)
class RunRecord:
    scenario: str
    category: str
    control: bool
    language: str
    framing: str
    run: int
    outcome: str
    evidence: str
    trace: Trace

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "category": self.category,
            "control": self.control,
            "language": self.language,
            "framing": self.framing,
            "run": self.run,
            "outcome": self.outcome,
            "evidence": self.evidence,
            "calls": [{"tool": c.name, "args": c.args} for c in self.trace.calls],
            "reply": self.trace.reply,
            "error": self.trace.error,
        }


@dataclass(frozen=True)
class BenchResult:
    agent: str
    runs: int
    languages: tuple[str, ...]
    records: tuple[RunRecord, ...]

    def to_json_records(self) -> str:
        return json.dumps([r.to_dict() for r in self.records], indent=2, ensure_ascii=False)


def run_bench(
    agent: Agent,
    corpus: Corpus,
    *,
    name: str = "agent",
    runs: int = 1,
    languages: Sequence[str] = LANGUAGES,
) -> BenchResult:
    """Every scenario, in every language, in both framings, ``runs`` times."""
    if runs < 1:
        raise ValueError("runs must be at least 1")
    records = []
    for scenario in corpus.scenarios:
        for language in languages:
            for run in range(runs):
                for framing in FRAMINGS:
                    trace = run_once(agent, corpus, scenario, language, framing)
                    score = score_trace(scenario, trace)
                    records.append(
                        RunRecord(
                            scenario=scenario.id,
                            category=scenario.category,
                            control=scenario.control,
                            language=language,
                            framing=framing,
                            run=run,
                            outcome=score.outcome,
                            evidence=score.evidence,
                            trace=trace,
                        )
                    )
    return BenchResult(name, runs, tuple(languages), tuple(records))
