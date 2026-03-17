"""Generate the runnable eval JSON from the editable markdown question list."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.config import PROJECT_DIR as APP_PROJECT_DIR, to_relative_path
from app.services.eval_dataset_builder import build_eval_dataset_from_markdown


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build test_eval_set.json from the editable evaluatetest.md file."
    )
    parser.add_argument(
        "--markdown",
        default="data/raw/evaluatetest.md",
        help="Path to the markdown question file.",
    )
    parser.add_argument(
        "--output",
        default="data/evals/test_eval_set.json",
        help="Path to the generated JSON dataset file.",
    )
    parser.add_argument(
        "--source-document",
        default="data/raw/test.md",
        help="Source document path referenced by every generated eval case.",
    )
    parser.add_argument(
        "--name",
        default="test-md-eval-v1",
        help="Dataset name written into the generated JSON.",
    )
    return parser.parse_args()


def _resolve_path(value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (APP_PROJECT_DIR / candidate).resolve()


def main() -> None:
    args = _parse_args()
    output_path = build_eval_dataset_from_markdown(
        markdown_path=_resolve_path(args.markdown),
        dataset_path=_resolve_path(args.output),
        source_document=args.source_document,
        dataset_name=args.name,
    )
    print(f"dataset_json={to_relative_path(output_path)}")


if __name__ == "__main__":
    main()
