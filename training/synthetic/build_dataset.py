"""Generates train.jsonl / eval.jsonl for the narrator LLM.

Usage:
    uv run python -m synthetic.build_dataset
    uv run python -m synthetic.build_dataset --train-size 1000 --eval-size 200
"""

import argparse
import json
import random
import uuid
from pathlib import Path
from typing import Any

# Imported directly from the app (not hand-copied) so a prompt edit in
# maica/reasoning/llm.py can never silently desync from what these datasets
# were generated against.
from maica.reasoning import llm as maica_llm

from synthetic.generator import SyntheticFactorSpec, generate_diagnosis

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"


def _target_json(targets: list[maica_llm.FactorExplanation]) -> str:
    return json.dumps([t.model_dump() for t in targets])


def _num_factors_distribution(rng: random.Random, *, size: int, eval_mode: bool) -> list[int]:
    """Roughly uniform over 1-10, with extra weight at exactly-2 and 7-10 for
    eval (the reported failure point and the extrapolation edge)."""
    if not eval_mode:
        return [rng.randint(1, 10) for _ in range(size)]

    weighted_pool = [2, 2, 2] + list(range(7, 11)) * 2 + list(range(1, 11))
    return [rng.choice(weighted_pool) for _ in range(size)]


def build_split(*, size: int, seed: int, eval_mode: bool) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for num_factors in _num_factors_distribution(rng, size=size, eval_mode=eval_mode):
        diagnosis, targets, specs = generate_diagnosis(
            rng, num_factors=num_factors, eval_mode=eval_mode
        )
        rows.append(
            {
                "example_id": str(uuid.uuid4()),
                "system": maica_llm._SYSTEM_PROMPT,
                "user": maica_llm.factors_to_user_content(diagnosis.factors),
                "assistant": _target_json(targets),
                "meta": _row_meta(specs, eval_mode=eval_mode),
            }
        )
    return rows


def _row_meta(specs: list[SyntheticFactorSpec], *, eval_mode: bool) -> dict[str, Any]:
    return {
        "num_factors": len(specs),
        "kinds": [s.kind.value for s in specs],
        "labels": [s.label.value for s in specs],
        "split": "eval" if eval_mode else "train",
    }


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-size", type=int, default=1000)
    parser.add_argument("--eval-size", type=int, default=200)
    parser.add_argument("--train-seed", type=int, default=1337)
    parser.add_argument("--eval-seed", type=int, default=2024)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    train_rows = build_split(size=args.train_size, seed=args.train_seed, eval_mode=False)
    eval_rows = build_split(size=args.eval_size, seed=args.eval_seed, eval_mode=True)

    write_jsonl(train_rows, args.out_dir / "train.jsonl")
    write_jsonl(eval_rows, args.out_dir / "eval.jsonl")

    print(f"wrote {len(train_rows)} train examples -> {args.out_dir / 'train.jsonl'}")
    print(f"wrote {len(eval_rows)} eval examples -> {args.out_dir / 'eval.jsonl'}")


if __name__ == "__main__":
    main()
