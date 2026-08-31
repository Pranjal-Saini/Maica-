# MAICA training tooling

Dev-only tooling for improving the local narrator LLM (`maica/reasoning/llm.py`
+ `maica/reasoning/ollama_client.py`). **Never shipped** — the Dockerfile only
copies `maica/`, `migrations/`, `alembic.ini` into the production image, and
this directory has its own `pyproject.toml` so its dependencies never touch
the app's lockfile.

## What's here (Phase 1)

- `synthetic/` — generates synthetic `DiagnosisResult` inputs and matching
  schema-correct target explanations, for training data and for evaluation.
- `eval/` — runs the real `maica.reasoning.llm.explain_factors()` against a
  synthetic eval set and reports schema-validity / factor-coverage /
  citation-safety rates, broken out by batch size.

Phase 2+ (actual QLoRA fine-tuning) is not built yet — see the project's plan
history for what that would add.

## Setup

```
uv sync
```

This installs `maica` itself in editable mode (see `[tool.uv.sources]` in
`pyproject.toml`) so the eval harness always exercises the real production
reasoning code, not a reimplementation.

## Commands

- Generate the datasets: `uv run python -m synthetic.build_dataset`
- Run the baseline eval: `uv run python -m eval.cli --model qwen3:8b --eval-set data/eval.jsonl`
- Test: `uv run pytest`
