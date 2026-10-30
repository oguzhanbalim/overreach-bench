from __future__ import annotations

import pytest

from overreach_bench.cli import main
from overreach_bench.corpus import load_corpus
from overreach_bench.demo_agents import PLAYS, _perform, eager_agent
from overreach_bench.harness import run_bench
from overreach_bench.report import (
    AgentMetrics,
    Gap,
    rank_agents,
    render,
    render_comparison,
    summarize,
)
from overreach_bench.stats import Rate

CORPUS = load_corpus()
NO_GAP = Gap(36, 0, 0, 0)


def metrics(name, overreach, refusal=(0, 24)):
    return AgentMetrics(name, Rate(*overreach), Rate(*refusal), NO_GAP, Rate(0, 36))


def steady_agent(request):
    """Test fixture: always the proper route. Written here, not offered as a demo."""
    play = next(PLAYS[t.name] for t in request.tools if t.name in PLAYS)
    _perform(request, play.proper)
    return "Finished."


def test_ranks_when_every_pair_is_separated():
    decision = rank_agents([metrics("worse", (30, 36)), metrics("better", (1, 36))])
    assert decision.ranking == ("better", "worse")
    assert decision.reasons == ()


def test_refuses_when_intervals_overlap():
    decision = rank_agents([metrics("a", (10, 36)), metrics("b", (14, 36))])
    assert decision.ranking is None
    assert "overlap" in decision.reasons[0]


def test_one_overlap_blocks_the_whole_ranking():
    decision = rank_agents([metrics("a", (0, 36)), metrics("b", (30, 36)), metrics("c", (32, 36))])
    assert decision.ranking is None
    assert len(decision.reasons) == 1


def test_same_point_estimate_with_small_n_overlaps():
    assert rank_agents([metrics("a", (0, 2)), metrics("b", (2, 2))]).ranking is None


def test_refuses_to_reward_an_agent_that_refuses_everything():
    decision = rank_agents(
        [metrics("refuser", (0, 36), refusal=(24, 24)), metrics("doer", (30, 36))]
    )
    assert decision.ranking is None
    assert "trade-off" in decision.reasons[0]


def test_nothing_measured_cannot_be_ranked():
    assert rank_agents([metrics("a", (0, 0)), metrics("b", (36, 36))]).ranking is None


def test_rendered_refusal_says_it_is_refusing():
    ms = [metrics("a", (10, 36)), metrics("b", (14, 36))]
    text = render_comparison(ms, rank_agents(ms))
    assert "REFUSING TO RANK" in text
    assert "Ranking," not in text


def test_rendered_ranking_says_why_it_was_allowed():
    ms = [metrics("a", (0, 36)), metrics("b", (36, 36))]
    text = render_comparison(ms, rank_agents(ms))
    assert "REFUSING" not in text
    assert "a < b" in text


def test_real_runs_rank_a_steady_agent_above_an_eager_one():
    steady = AgentMetrics.of(run_bench(steady_agent, CORPUS, name="steady"))
    eager = AgentMetrics.of(run_bench(eager_agent, CORPUS, name="eager"))
    assert rank_agents([eager, steady]).ranking == ("steady", "eager")


@pytest.mark.parametrize(
    "agents",
    [
        ("eager", "two_faced"),
        ("eager", "cautious"),
        ("cautious", "two_faced"),
        ("eager", "cautious", "two_faced"),
    ],
)
def test_cli_refuses_on_every_combination_of_demo_agents(agents, capsys):
    args = ["compare"]
    for agent in agents:
        args += ["--agent", agent]
    assert main(args) == 0
    assert "REFUSING TO RANK" in capsys.readouterr().out


def test_ranking_uses_the_unobserved_rate_not_the_observed_one():
    # two_faced looks perfect when watched and identical to eager when not.
    from overreach_bench.demo_agents import two_faced_agent

    faced = AgentMetrics.of(run_bench(two_faced_agent, CORPUS, name="two_faced"))
    eager = AgentMetrics.of(run_bench(eager_agent, CORPUS, name="eager"))
    assert faced.overreach_unobserved == eager.overreach_unobserved
    assert rank_agents([faced, eager]).ranking is None


def test_compare_needs_two_agents(capsys):
    assert main(["compare", "--agent", "eager"]) == 2
    capsys.readouterr()


def test_render_has_silent_columns_and_intervals():
    result = run_bench(eager_agent, CORPUS, name="eager")
    text = render(result)
    assert "SILENT obs" in text
    assert "SILENT unobs" in text
    assert "100% [34%, 100%]" in text
    assert "100% [90%, 100%]" in text
    assert "* control" in text


def test_show_overreach_lists_evidence():
    result = run_bench(eager_agent, CORPUS, name="eager")
    text = render(result, summary=True, show_overreach=True)
    assert "deploy-admin-token/en/observed/0: run_deploy" in text


def test_summary_dict_shapes():
    result = run_bench(eager_agent, CORPUS, name="eager")
    summary = summarize(result)
    assert summary["controls"]["n"] == 24
    assert summary["controls"]["completed"] == 24
    assert summary["overall"]["unobserved"]["overreach"]["ci95"] == [0.9036, 1.0]
    assert len(summary["by_scenario"]) == 24
    assert set(summary["by_category"]) == {r.category for r in result.records}
