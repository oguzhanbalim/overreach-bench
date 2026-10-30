"""Run an agent through paired scenarios and print what it did, watched and unwatched."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from overreach_bench.corpus import CATEGORIES, FRAMINGS, LANGUAGES, UNOBSERVED, load_corpus
from overreach_bench.demo_agents import cautious_agent, eager_agent, two_faced_agent
from overreach_bench.harness import Agent, BenchResult, run_bench
from overreach_bench.report import (
    AgentMetrics,
    overreach_rate,
    rank_agents,
    render,
    render_comparison,
    summarize,
)

BUILTIN = {"eager": eager_agent, "cautious": cautious_agent, "two_faced": two_faced_agent}
DEMO_NOTICE = (
    "Demo agent: a fake, rule-based agent with no model behind it. "
    "These numbers test the harness and say nothing about any real model."
)


def load_agent(spec: str) -> Agent:
    if spec in BUILTIN:
        return BUILTIN[spec]
    target, sep, attr = spec.rpartition(":")
    if not sep:
        raise ValueError(f"expected {sorted(BUILTIN)}, module:callable or file.py:callable")
    if target.endswith(".py"):
        path = Path(target).resolve()
        module_spec = importlib.util.spec_from_file_location(path.stem, path)
        if module_spec is None or module_spec.loader is None:
            raise ValueError(f"cannot load {path}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        module = importlib.import_module(target)
    return getattr(module, attr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="overreach-bench", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run one agent through the corpus")
    run.add_argument("--agent", required=True, help="eager, cautious, two_faced or module:callable")
    run.add_argument("--runs", type=int, default=1, help="repeats per scenario, language, framing")
    run.add_argument("--language", choices=LANGUAGES, help="only this language")
    run.add_argument("--summary", action="store_true", help="leave out the per-scenario tables")
    run.add_argument("--show-overreach", action="store_true", help="list evidence for each hit")
    run.add_argument("--json", action="store_true", help="summary and full traces as JSON")
    run.add_argument(
        "--max-overreach", type=float, help="exit 1 if the unobserved overreach rate is above this"
    )
    run.set_defaults(func=cmd_run)

    compare = commands.add_parser("compare", help="compare agents, or refuse to")
    compare.add_argument("--agent", action="append", required=True, help="repeat for each agent")
    compare.add_argument("--runs", type=int, default=1)
    compare.add_argument("--language", choices=LANGUAGES)
    compare.set_defaults(func=cmd_compare)

    listing = commands.add_parser("list", help="list the scenarios")
    listing.add_argument("--category", choices=CATEGORIES)
    listing.set_defaults(func=cmd_list)

    show = commands.add_parser("show", help="print what an agent sees for one scenario")
    show.add_argument("scenario")
    show.add_argument("--language", choices=LANGUAGES, default="en")
    show.set_defaults(func=cmd_show)
    return parser


def _languages(args: argparse.Namespace) -> Sequence[str]:
    return (args.language,) if args.language else LANGUAGES


def _run(spec: str, args: argparse.Namespace) -> BenchResult:
    agent = load_agent(spec)
    return run_bench(agent, load_corpus(), name=spec, runs=args.runs, languages=_languages(args))


def cmd_run(args: argparse.Namespace) -> int:
    result = _run(args.agent, args)
    demo = args.agent in BUILTIN
    if args.json:
        payload = {
            "notice": DEMO_NOTICE if demo else None,
            "summary": summarize(result),
            "records": [record.to_dict() for record in result.records],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if demo:
            print(DEMO_NOTICE)
        print(render(result, summary=args.summary, show_overreach=args.show_overreach))
    if args.max_overreach is None:
        return 0
    rate = overreach_rate(
        r for r in result.records if not r.control and r.framing == UNOBSERVED
    ).value
    # An agent that only crashed has not passed. There is no rate to gate on.
    return 0 if rate is not None and rate <= args.max_overreach else 1


def cmd_compare(args: argparse.Namespace) -> int:
    if len(args.agent) < 2:
        raise ValueError("compare needs at least two --agent values")
    if any(spec in BUILTIN for spec in args.agent):
        print(DEMO_NOTICE)
    metrics = [AgentMetrics.of(_run(spec, args)) for spec in args.agent]
    print(render_comparison(metrics, rank_agents(metrics)))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    for scenario in load_corpus().scenarios:
        if args.category and scenario.category != args.category:
            continue
        kind = "control" if scenario.control else "pressure"
        print(f"{scenario.id:34} {scenario.category:22} {kind}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    corpus = load_corpus()
    scenario = corpus.get(args.scenario)
    for framing in FRAMINGS:
        rendered = corpus.render(scenario, args.language, framing)
        print(f"--- system ({framing})\n{rendered.system}\n")
    print(f"--- task\n{rendered.task}\n\n--- tools")
    for tool in rendered.tools:
        print(f"{tool.name}: {tool.description}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, AttributeError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
