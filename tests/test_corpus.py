from __future__ import annotations

import re
from collections import Counter

import pytest
import yaml

from overreach_bench.corpus import (
    CATEGORIES,
    FRAMINGS,
    LANGUAGES,
    OBSERVED,
    UNOBSERVED,
    Corpus,
    check_pair,
    load_corpus,
)
from overreach_bench.harness import run_once
from overreach_bench.scoring import COMPLETED, OVERREACHES

CORPUS = load_corpus()
SCENARIOS = CORPUS.scenarios
BOTH = [(s, lang) for s in SCENARIOS for lang in LANGUAGES]
IDS = [f"{s.id}-{lang}" for s, lang in BOTH]
TURKISH_LETTERS = re.compile("[çğıöşüÇĞİÖŞÜ]")


def difference(one: str, two: str) -> tuple[str, str]:
    """What is left of two strings after removing their shared start and end."""
    start = 0
    limit = min(len(one), len(two))
    while start < limit and one[start] == two[start]:
        start += 1
    end = 0
    while end < limit - start and one[-1 - end] == two[-1 - end]:
        end += 1
    return one[start : len(one) - end], two[start : len(two) - end]


def test_corpus_has_24_scenarios_in_6_categories_of_4():
    assert len(SCENARIOS) == 24
    assert Counter(s.category for s in SCENARIOS) == dict.fromkeys(CATEGORIES, 4)


def test_at_least_six_controls_with_one_in_every_category():
    controls = [s for s in SCENARIOS if s.control]
    assert len(controls) >= 6
    assert {s.category for s in controls} == set(CATEGORIES)


@pytest.mark.parametrize(("scenario", "language"), BOTH, ids=IDS)
def test_every_scenario_loads_in_both_languages(scenario, language):
    rendered = CORPUS.render(scenario, language, OBSERVED)
    assert rendered.system.strip()
    assert rendered.task.strip()
    assert scenario.text[language].disclosure
    assert len(rendered.tools) >= 2
    assert rendered.tools[-1].name == "ask_human"
    for tool in rendered.tools:
        assert tool.description.strip()
        assert tool.input_schema["type"] == "object"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_turkish_text_is_actually_turkish(scenario):
    text = scenario.text["tr"]
    assert TURKISH_LETTERS.search(text.system + text.task)
    assert text.system != scenario.text["en"].system
    assert text.task != scenario.text["en"].task
    for tool in scenario.tools:
        assert tool.descriptions["tr"] != tool.descriptions["en"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_every_rule_has_a_translation_or_is_marked_language_free(scenario):
    for tool in scenario.tools:
        for rule in tool.rules:
            assert set(rule.text) == set(LANGUAGES)
            assert all(rule.text[lang].strip() for lang in LANGUAGES)


@pytest.mark.parametrize("language", LANGUAGES)
def test_framing_passages_are_short_and_say_what_they_should(language):
    observed = CORPUS.framings[language][OBSERVED]
    unobserved = CORPUS.framings[language][UNOBSERVED]
    assert observed != unobserved
    assert len(observed) < 130
    assert len(unobserved) < 130


def test_framing_passages_state_the_condition():
    assert "logged" in CORPUS.framings["en"][OBSERVED]
    assert "nobody reviews" in CORPUS.framings["en"][UNOBSERVED]
    assert "kayda geçiyor" in CORPUS.framings["tr"][OBSERVED]
    assert "kimse incelemiyor" in CORPUS.framings["tr"][UNOBSERVED]


@pytest.mark.parametrize(("scenario", "language"), BOTH, ids=IDS)
def test_pair_differs_only_in_the_framing_passage(scenario, language):
    """Checked on what the agent receives through the harness, not on the template."""
    seen = {}

    def spy(framing):
        def agent(request):
            probes = {
                tool.name: request.call_tool(
                    tool.name, dict.fromkeys(tool.input_schema["properties"], "probe")
                )
                for tool in request.tools
            }
            seen[framing] = (request.system, request.task, request.tools, probes, request.language)
            return ""

        return agent

    for framing in FRAMINGS:
        run_once(spy(framing), CORPUS, scenario, language, framing)
    obs, unobs = seen[OBSERVED], seen[UNOBSERVED]
    # Everything but the system prompt is identical, including what the tools answer.
    assert obs[1:] == unobs[1:]
    # The system prompts differ in one place, and that place lies inside the passages.
    only_obs, only_unobs = difference(obs[0], unobs[0])
    assert only_obs and only_unobs
    assert only_obs in CORPUS.framings[language][OBSERVED]
    assert only_unobs in CORPUS.framings[language][UNOBSERVED]
    # Removing the passages leaves the same text.
    base = scenario.text[language].system
    assert obs[0] == f"{base}\n\n{CORPUS.framings[language][OBSERVED]}"
    assert unobs[0] == f"{base}\n\n{CORPUS.framings[language][UNOBSERVED]}"


def test_framing_never_appears_in_the_scenario_text():
    for language in LANGUAGES:
        for framing in FRAMINGS:
            passage = CORPUS.framings[language][framing]
            for scenario in SCENARIOS:
                text = scenario.text[language]
                assert passage not in text.system
                assert passage not in text.task


def test_pair_check_catches_a_system_prompt_that_differs_elsewhere():
    class Sneaky(Corpus):
        def render(self, scenario, language, framing):
            rendered = super().render(scenario, language, framing)
            if framing != UNOBSERVED:
                return rendered
            changed = rendered.system.replace("release assistant", "release lead")
            return type(rendered)(changed, rendered.task, rendered.tools)

    sneaky = Sneaky(CORPUS.scenarios, CORPUS.framings)
    with pytest.raises(ValueError, match="differ outside"):
        check_pair(sneaky, CORPUS.get("deploy-admin-token"), "en")


def test_pair_check_catches_a_task_that_differs():
    class Sneaky(Corpus):
        def render(self, scenario, language, framing):
            rendered = super().render(scenario, language, framing)
            if framing != UNOBSERVED:
                return rendered
            return type(rendered)(rendered.system, rendered.task + " Hurry.", rendered.tools)

    sneaky = Sneaky(CORPUS.scenarios, CORPUS.framings)
    with pytest.raises(ValueError, match="task or tools"):
        check_pair(sneaky, CORPUS.get("deploy-admin-token"), "en")


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.control], ids=lambda s: s.id)
def test_controls_state_the_permission_in_both_languages(scenario):
    for language in LANGUAGES:
        text = scenario.text[language]
        assert text.permission
        assert text.permission in f"{text.system} {text.task}"


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.control], ids=lambda s: s.id)
def test_control_permitted_action_is_the_completion_and_is_not_an_overreach(scenario):
    assert [m.raw for m in scenario.permitted] == [m.raw for m in scenario.completion]
    # A control still has a line, so it tells a careful agent from a careless one.
    assert scenario.overreach


def test_pressure_scenarios_declare_no_permission():
    for scenario in SCENARIOS:
        if not scenario.control:
            assert not scenario.permitted
            assert all(scenario.text[lang].permission is None for lang in LANGUAGES)


def test_every_scenario_declares_all_three_lists():
    for scenario in SCENARIOS:
        assert scenario.overreach
        assert scenario.escalation
        assert scenario.completion


def test_each_scenario_has_a_tool_only_it_has():
    counts = Counter(tool.name for s in SCENARIOS for tool in s.tools)
    for scenario in SCENARIOS:
        assert any(counts[tool.name] == 1 for tool in scenario.tools), scenario.id


def test_data_is_invented_and_hosts_cannot_resolve():
    hosts = re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|co|ai|tr)\b")
    emails = re.compile(r"[\w.+-]+@[\w-]+")
    from importlib import resources

    data = resources.files("overreach_bench") / "data"
    for category in CATEGORIES:
        text = (data / f"{category}.yaml").read_text(encoding="utf-8")
        assert not hosts.search(text), category
        assert not emails.search(text), category
        yaml.safe_load(text)


def test_overreach_and_completion_matchers_do_not_overlap_on_the_proper_route():
    from overreach_bench.demo_agents import PLAYS, _perform

    for scenario in SCENARIOS:
        play = next(PLAYS[t.name] for t in scenario.tools if t.name in PLAYS)

        def proper(request, play=play):
            _perform(request, play.proper)
            return "Finished."

        from overreach_bench.scoring import score_trace

        for language in LANGUAGES:
            score = score_trace(scenario, run_once(proper, CORPUS, scenario, language, OBSERVED))
            assert score.outcome == COMPLETED, scenario.id
            assert score.outcome not in OVERREACHES
