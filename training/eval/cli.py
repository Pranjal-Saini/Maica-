"""Runs the eval harness against a real Ollama model and writes a JSON report.

Usage:
    uv run python -m eval.cli --model qwen3:8b --eval-set ../data/eval.jsonl
    uv run python -m eval.cli --model qwen3:8b --eval-set ../data/eval.jsonl \
        --report-out ../outputs/reports/baseline_qwen3_8b.json
"""

import argparse
import asyncio
from pathlib import Path

from maica.reasoning.ollama_client import OllamaClient

from eval.harness import load_eval_examples, run_eval

DEFAULT_REPORT_DIR = Path(__file__).parent.parent / "outputs" / "reports"


async def _main_async(args: argparse.Namespace) -> None:
    examples = load_eval_examples(args.eval_set)
    print(f"loaded {len(examples)} eval examples from {args.eval_set}")

    client = OllamaClient(base_url=args.ollama_url)
    report = await run_eval(examples, client=client, model=args.model)

    report_json = report.model_dump_json(indent=2)
    print(report_json)

    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(report_json, encoding="utf-8")
        print(f"\nwrote report -> {args.report_out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Ollama model tag, e.g. qwen3:8b")
    parser.add_argument("--eval-set", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--report-out", type=Path, default=None)
    args = parser.parse_args()

    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
