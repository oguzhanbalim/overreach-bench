"""Load and validate the scenarios.

A scenario is data: the text the agent sees in each language, the fake tools, and three lists
of matchers that say which tool calls are an overreach, an escalation or a legitimate
completion. The framing passages live apart from the scenarios, in ``shared.yaml``, so a
scenario cannot change anything between its two framings except that one passage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

from overreach_bench.textutil import compile_folded, fold

CATEGORIES = (
    "borrowed_credentials",
    "disabled_oversight",
    "tampered_records",
    "blast_radius",
    "skipped_approval",
    "quiet_workaround",
)
LANGUAGES = ("en", "tr")
OBSERVED = "observed"
UNOBSERVED = "unobserved"
FRAMINGS = (OBSERVED, UNOBSERVED)
ASK_HUMAN = "ask_human"
_TYPES = {"string", "boolean", "number"}


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]

    def args_text(self) -> str:
        return json.dumps(self.args, ensure_ascii=False, sort_keys=True, default=str)

    def arg_text(self, name: str) -> str | None:
        if name not in self.args:
            return None
        value = self.args[name]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


@dataclass(frozen=True)
class Matcher:
    """A check on one recorded tool call. Every field that is set must hold.

    ``tool`` is an exact name, or None for any tool. ``args`` maps a parameter to a regex
    searched in that argument. ``any_arg`` is a regex searched across all arguments.
    ``times`` asks for at least that many matching calls in the trace.
    """

    raw: dict[str, Any]
    tool: str | None
    args: tuple[tuple[str, re.Pattern[str]], ...]
    any_arg: re.Pattern[str] | None
    times: int

    @classmethod
    def parse(cls, raw: dict[str, Any], where: str) -> Matcher:
        unknown = set(raw) - {"tool", "args", "any_arg", "times"}
        if unknown:
            raise ValueError(f"{where}: unknown matcher keys {sorted(unknown)}")
        if not {"tool", "args", "any_arg"} & set(raw):
            raise ValueError(f"{where}: empty matcher")
        return cls(
            raw=raw,
            tool=raw.get("tool"),
            args=tuple((k, compile_folded(str(v))) for k, v in raw.get("args", {}).items()),
            any_arg=compile_folded(raw["any_arg"]) if "any_arg" in raw else None,
            times=int(raw.get("times", 1)),
        )

    def matches(self, call: ToolCall) -> bool:
        if self.tool is not None and call.name != self.tool:
            return False
        for name, pattern in self.args:
            text = call.arg_text(name)
            if text is None or not pattern.search(fold(text)):
                return False
        return self.any_arg is None or bool(self.any_arg.search(fold(call.args_text())))

    def first_hit(self, calls: tuple[ToolCall, ...] | list[ToolCall]) -> ToolCall | None:
        hits = [call for call in calls if self.matches(call)]
        return hits[self.times - 1] if len(hits) >= self.times else None


@dataclass(frozen=True)
class ToolSpec:
    """What an agent is told about a tool, in the language of the run."""

    name: str
    description: str
    input_schema: dict[str, Any]

    def to_messages_api(self) -> dict[str, Any]:
        """The tool definition shape for the Messages API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass(frozen=True)
class ResultRule:
    when: Matcher | None
    after: Matcher | None
    text: dict[str, str]


@dataclass(frozen=True)
class Tool:
    name: str
    descriptions: dict[str, str]
    params: tuple[tuple[str, str, bool], ...]  # name, JSON type, required
    rules: tuple[ResultRule, ...]
    default: dict[str, str]

    def spec(self, language: str) -> ToolSpec:
        schema = {
            "type": "object",
            "properties": {name: {"type": kind} for name, kind, _ in self.params},
            "required": [name for name, _, required in self.params if required],
        }
        return ToolSpec(self.name, self.descriptions[language], schema)

    def missing_args(self, args: dict[str, Any]) -> list[str]:
        return [name for name, _, required in self.params if required and name not in args]

    def respond(self, call: ToolCall, language: str, earlier: list[ToolCall]) -> str:
        """The first rule that holds wins. Rules can depend on earlier calls in the run."""
        for rule in self.rules:
            if rule.when is not None and not rule.when.matches(call):
                continue
            if rule.after is not None and rule.after.first_hit(earlier) is None:
                continue
            return rule.text[language]
        return self.default[language]


@dataclass(frozen=True)
class ScenarioText:
    system: str
    task: str
    disclosure: str
    permission: str | None


@dataclass(frozen=True)
class Rendered:
    """Exactly what an agent receives for one scenario, language and framing."""

    system: str
    task: str
    tools: tuple[ToolSpec, ...]


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    control: bool
    text: dict[str, ScenarioText]
    tools: tuple[Tool, ...]
    overreach: tuple[Matcher, ...]
    escalation: tuple[Matcher, ...]
    completion: tuple[Matcher, ...]
    permitted: tuple[Matcher, ...] = ()
    disclosure: tuple[re.Pattern[str], ...] = ()

    def tool(self, name: str) -> Tool | None:
        return next((tool for tool in self.tools if tool.name == name), None)


@dataclass(frozen=True)
class Corpus:
    scenarios: tuple[Scenario, ...]
    framings: dict[str, dict[str, str]]

    def render(self, scenario: Scenario, language: str, framing: str) -> Rendered:
        text = scenario.text[language]
        return Rendered(
            system=f"{text.system}\n\n{self.framings[language][framing]}",
            task=text.task,
            tools=tuple(tool.spec(language) for tool in scenario.tools),
        )

    def get(self, scenario_id: str) -> Scenario:
        for scenario in self.scenarios:
            if scenario.id == scenario_id:
                return scenario
        raise ValueError(f"no scenario called {scenario_id!r}")


def check_pair(corpus: Corpus, scenario: Scenario, language: str) -> None:
    """Raise unless the two framings render identically outside the framing passage."""
    observed = corpus.render(scenario, language, OBSERVED)
    unobserved = corpus.render(scenario, language, UNOBSERVED)
    where = f"{scenario.id}/{language}"
    if observed.task != unobserved.task or observed.tools != unobserved.tools:
        raise ValueError(f"{where}: task or tools differ between framings")
    one = observed.system.replace(corpus.framings[language][OBSERVED], "\0", 1)
    two = unobserved.system.replace(corpus.framings[language][UNOBSERVED], "\0", 1)
    if one != two or "\0" not in one:
        raise ValueError(f"{where}: system prompts differ outside the framing passage")


def _both(value: Any, where: str) -> dict[str, str]:
    """A per-language mapping. A plain string means the same text in both languages."""
    if isinstance(value, str):
        return dict.fromkeys(LANGUAGES, value)
    if isinstance(value, dict) and all(isinstance(value.get(lang), str) for lang in LANGUAGES):
        return {lang: value[lang] for lang in LANGUAGES}
    raise ValueError(f"{where}: needs text in {LANGUAGES}")


def _parse_params(raw: dict[str, str], where: str) -> tuple[tuple[str, str, bool], ...]:
    params = []
    for name, declared in raw.items():
        required = not declared.endswith("?")
        kind = declared.rstrip("?")
        if kind not in _TYPES:
            raise ValueError(f"{where}: unknown type {declared!r} for {name}")
        params.append((name, kind, required))
    return tuple(params)


def _parse_tool(raw: dict[str, Any], where: str) -> Tool:
    name = raw["name"]
    where = f"{where}/{name}"
    rules = []
    for rule in raw.get("results", []):
        when = Matcher.parse({"args": rule["when"]}, where) if "when" in rule else None
        after = Matcher.parse(rule["after"], where) if "after" in rule else None
        rules.append(ResultRule(when, after, _both(rule.get("text", rule), where)))
    return Tool(
        name=name,
        descriptions=_both(raw, where),
        params=_parse_params(raw.get("params", {}), where),
        rules=tuple(rules),
        default=_both(raw["default"], where),
    )


def _parse_scenario(raw: dict[str, Any], ask_human: dict[str, Any]) -> Scenario:
    where = raw["id"]
    tools = [_parse_tool(tool, where) for tool in raw["tools"]]
    tools.append(
        _parse_tool(
            {
                "name": ASK_HUMAN,
                "params": ask_human["params"],
                "en": ask_human["en"],
                "tr": ask_human["tr"],
                "default": raw["ask_human"],
            },
            where,
        )
    )
    text = {}
    for language in LANGUAGES:
        block = raw[language]
        text[language] = ScenarioText(
            system=block["system"],
            task=block["task"],
            disclosure=block["disclosure"],
            permission=block.get("permission"),
        )

    def matchers(key: str) -> tuple[Matcher, ...]:
        return tuple(Matcher.parse(m, f"{where}/{key}") for m in raw.get(key, []))

    return Scenario(
        id=raw["id"],
        category=raw["category"],
        control=bool(raw["control"]),
        text=text,
        tools=tuple(tools),
        overreach=matchers("overreach"),
        escalation=matchers("escalation"),
        completion=matchers("completion"),
        permitted=matchers("permitted"),
        disclosure=tuple(compile_folded(t.disclosure) for t in text.values()),
    )


def _validate(scenario: Scenario) -> None:
    where = scenario.id
    if scenario.category not in CATEGORIES:
        raise ValueError(f"{where}: unknown category {scenario.category!r}")
    if not scenario.overreach or not scenario.escalation or not scenario.completion:
        raise ValueError(f"{where}: needs overreach, escalation and completion matchers")
    for matcher in (*scenario.overreach, *scenario.escalation, *scenario.completion):
        if matcher.tool is None:
            continue
        tool = scenario.tool(matcher.tool)
        if tool is None:
            raise ValueError(f"{where}: matcher names unknown tool {matcher.tool!r}")
        declared = {name for name, _, _ in tool.params}
        for name, _ in matcher.args:
            if name not in declared:
                raise ValueError(f"{where}: {tool.name} has no parameter {name!r}")
    if scenario.control:
        if not scenario.permitted:
            raise ValueError(f"{where}: a control must declare the permitted action")
        for text in scenario.text.values():
            if not text.permission or text.permission not in f"{text.system} {text.task}":
                raise ValueError(f"{where}: the permission is not stated in the agent's text")
    elif scenario.permitted:
        raise ValueError(f"{where}: only a control can declare a permitted action")


def load_corpus() -> Corpus:
    data = resources.files("overreach_bench") / "data"
    shared = yaml.safe_load((data / "shared.yaml").read_text(encoding="utf-8"))
    framings = {
        language: {framing: shared["framings"][framing][language] for framing in FRAMINGS}
        for language in LANGUAGES
    }
    scenarios: list[Scenario] = []
    for category in CATEGORIES:
        raw = yaml.safe_load((data / f"{category}.yaml").read_text(encoding="utf-8"))
        scenarios.extend(_parse_scenario(item, shared["ask_human"]) for item in raw)
    ids = [scenario.id for scenario in scenarios]
    if len(set(ids)) != len(ids):
        raise ValueError("scenario ids are not unique")
    corpus = Corpus(tuple(scenarios), framings)
    for scenario in scenarios:
        _validate(scenario)
        for language in LANGUAGES:
            check_pair(corpus, scenario, language)
    return corpus
