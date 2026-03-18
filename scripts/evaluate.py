"""Run and summarize the small manual evaluation loop."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.config import PROJECT_DIR as APP_PROJECT_DIR, to_relative_path
from app.services.evaluator import latest_eval_run_path, run_evaluation, write_eval_report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a small vector/direct_read evaluation loop."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run evaluation and save a JSON result set.")
    run_parser.add_argument(
        "--dataset",
        default="data/evals/test_eval_set.json",
        help="Path to the evaluation dataset JSON file.",
    )
    run_parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="top_k passed to vector ask runs.",
    )
    run_parser.add_argument(
        "--modes",
        nargs="+",
        default=["vector", "direct_read"],
        help="Subset of modes to run. Default: vector direct_read",
    )

    report_parser = subparsers.add_parser(
        "report",
        help="Generate or refresh a markdown report from a labeled run JSON.",
    )
    report_parser.add_argument(
        "--run",
        default="latest",
        help="Path to a run.json file, or 'latest' to use the newest saved run.",
    )

    return parser.parse_args()


def _resolve_run_path(value: str) -> Path:
    if value == "latest":
        latest = latest_eval_run_path()
        if latest is None:
            raise FileNotFoundError("No saved evaluation runs were found.")
        return latest

    candidate = Path(value)
    return candidate if candidate.is_absolute() else (APP_PROJECT_DIR / candidate).resolve()


def main() -> None:
    args = _parse_args()

    if args.command == "run":
        run_path = run_evaluation(
            dataset_path=Path(args.dataset),
            top_k=args.top_k,
            modes=args.modes,
        )
        report_path = write_eval_report(run_path)
        print(f"run_json={to_relative_path(run_path)}")
        print(f"report_md={to_relative_path(report_path)}")
        print(
            "next_step=review answer_preview and evidence in run_json, fill manual_review.label/error_type, then rerun `python scripts/evaluate.py report --run latest`"
        )
        return

    run_path = _resolve_run_path(args.run)
    report_path = write_eval_report(run_path)
    print(f"report_md={to_relative_path(report_path)}")


if __name__ == "__main__":
    main()
