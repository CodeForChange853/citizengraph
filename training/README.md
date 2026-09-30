# Training

Holds the Core 1 dataset generator, the noise injector and the QLoRA notebook script.
**Training does not run here or on CPU/integrated-graphics machines**; run
`qlora_kaggle.py` (written as `# %%` notebook cells) on a free Kaggle T4.

Rules: data comes from our own generators (templates, rules, noise injection), never from
LLM API outputs; never read `../eval/heldout/`; fp16 only (T4/P100 have no bf16); examples
teach Cypher structure, not facts.

```bash
pip install -e ".[dev]"
python -m training.generate_dataset --seed 0     # training/out/*.jsonl, sample/, DATASET_CARD.md
python -m training.eval_generate --data training/out/test_synthetic.jsonl \
    --meta training/out/test_synthetic.meta.jsonl --outputs outputs.jsonl
```

| File | What |
|---|---|
| `generate_dataset.py` | deterministic generator (seed argument) |
| `phrasebook.yaml` | phrase templates; Filipino/Taglish marked NEEDS-NATIVE-REVIEW |
| `noise.py` | typos, dropped vowels, doubled letters, c/k and ph/f swaps, SMS, casing |
| `qlora_kaggle.py` | QLoRA + merge + GGUF cells, **untested on a GPU** |
| `eval_generate.py` | guardrail-valid rate and exact match against gold |
| `requirements-train.txt` | training-only pins (not in `pyproject.toml`) |
| `DATASET_CARD.md`, `sample/` | generated overview and ~60 reviewable examples |
| `out/` | generated JSONL (gitignored) |

Design, parameter contract, splits, limits and Kaggle steps: `../docs/training_notes.md`.
