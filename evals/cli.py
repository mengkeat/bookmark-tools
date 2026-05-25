from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

SUITES = ["search", "ablation"]


def _cmd_list_suites(_args: argparse.Namespace) -> int:
    print("Available suites:")
    for name in SUITES:
        print(f"  {name}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if args.suite == "search":
        from evals.runners.search import run_search

        raw_modes = args.mode.split(",")
        modes = ["bm25", "semantic", "hybrid"] if raw_modes == ["all"] else raw_modes
        return run_search(
            dataset=args.dataset,
            modes=modes,
            k_values=[5, 10],
            limit=args.limit,
            query_limit=args.query_limit,
        )
    if args.suite == "ablation":
        from evals.runners.embedding_ablation import run_ablation

        raw_modes = args.mode.split(",")
        modes = ["bm25", "semantic", "hybrid"] if raw_modes == ["all"] else raw_modes
        models = [m.strip() for m in args.models.split(",") if m.strip()]
        dimensions = [int(d.strip()) for d in args.dimensions.split(",") if d.strip()]
        return run_ablation(
            dataset=args.dataset,
            models=models,
            dimensions=dimensions,
            modes=modes,
            k_values=[5, 10],
            limit=args.limit,
            query_limit=args.query_limit,
        )
    print(f"Unknown suite: {args.suite!r}", file=sys.stderr)
    return 1


def _cmd_diff(args: argparse.Namespace) -> int:
    from evals.reporter import diff_snapshots

    diff_snapshots(Path(args.baseline), Path(args.current))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bookmark-eval",
        description="Bookmark retrieval benchmark suite",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-suites", help="List available eval suites")

    run_p = sub.add_parser("run", help="Run an eval suite")
    run_p.add_argument("suite", choices=SUITES, help="Suite to run")
    run_p.add_argument(
        "--dataset",
        default="beir:nfcorpus",
        help="Dataset: beir:nfcorpus, beir:scifact, or personal (default: beir:nfcorpus)",
    )
    run_p.add_argument(
        "--mode",
        default="all",
        help="bm25 | semantic | hybrid | all, or comma-separated list (default: all)",
    )
    run_p.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max results per query for ranking (default: 100)",
    )
    run_p.add_argument(
        "--query-limit",
        type=int,
        default=None,
        dest="query_limit",
        help="Evaluate only the first N queries (useful for quick smoke-tests)",
    )
    run_p.add_argument(
        "--models",
        default="text-embedding-3-small",
        help="Comma-separated embedding models for ablation (default: text-embedding-3-small)",
    )
    run_p.add_argument(
        "--dimensions",
        default="256,512",
        help="Comma-separated dimension counts for ablation (default: 256,512)",
    )

    diff_p = sub.add_parser("diff", help="Compare two snapshot JSON files")
    diff_p.add_argument("baseline", help="Path to baseline snapshot JSON")
    diff_p.add_argument("current", help="Path to current snapshot JSON")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "list-suites":
        return _cmd_list_suites(args)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "diff":
        return _cmd_diff(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
