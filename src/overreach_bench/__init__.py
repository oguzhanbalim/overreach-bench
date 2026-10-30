"""A bench for whether a tool-using agent stays inside its authority under task pressure."""

from overreach_bench.corpus import Corpus, Matcher, Scenario, ToolCall, ToolSpec, load_corpus
from overreach_bench.harness import Agent, AgentRequest, BenchResult, RunRecord, run_bench
from overreach_bench.report import AgentMetrics, RankDecision, rank_agents, summarize
from overreach_bench.scoring import Score, Trace, score_trace
from overreach_bench.stats import Rate, sign_test, wilson

__all__ = [
    "Agent",
    "AgentMetrics",
    "AgentRequest",
    "BenchResult",
    "Corpus",
    "Matcher",
    "RankDecision",
    "Rate",
    "RunRecord",
    "Scenario",
    "Score",
    "ToolCall",
    "ToolSpec",
    "Trace",
    "load_corpus",
    "rank_agents",
    "run_bench",
    "score_trace",
    "sign_test",
    "summarize",
    "wilson",
]
