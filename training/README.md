# Training

Holds the Core 1 dataset generator, the noise injector, the evaluation and the QLoRA notebook
script. **Training does not run here or on CPU/integrated-graphics machines**; run
`qlora_kaggle.py` (written as `# %%` notebook cells) on a free Kaggle T4.

Rules: data comes from our own generators (templates, rules, noise injection), never from LLM API
outputs; never read `../eval/heldout/`; fp16 only (T4/P100 have no bf16); examples teach question
understanding and Cypher structure, not facts.

**Session 5b redesign:** the model receives only the linked targets, the language and the cleaned
phrase (prompt v2) and infers intent, query shape and variants from the wording; 38 canonical
queries; two shapes are held out as `test_unseen_shape`. See `../docs/training_notes.md`.

```bash
pip install -e ".[dev]"
python -m training.generate_dataset --seed 0     # training/out/*.jsonl, sample/, DATASET_CARD.md
python -m training.eval_generate --data training/out/test_synthetic.jsonl \
    --meta training/out/test_synthetic.meta.jsonl --baseline      # templates-only baseline
python -m training.eval_generate --data training/out/test_synthetic.jsonl \
    --meta training/out/test_synthetic.meta.jsonl --outputs outputs.jsonl \
    --neo4j-uri bolt://localhost:7687                            # add execution accuracy
```

| File | What |
|---|---|
| `generate_dataset.py`, `cells.py` | deterministic generator (seed argument); what each question is about |
| `phrasebook.yaml`, `phrasebook_shapes.yaml`, `phrasebook.py` | phrase templates and names; Filipino/Taglish marked NEEDS-NATIVE-REVIEW |
| `noise.py` | typos, dropped vowels, doubled letters, c/k and ph/f swaps, SMS, casing |
| `eval_generate.py` | guardrail validity, exact match, intent accuracy, execution accuracy, per family |
| `baseline.py` | templates-only baseline: the gateway's rule-based intent mapped to list templates |
| `qlora_kaggle.py` | QLoRA + merge + GGUF cells, **untested on a GPU** |
| `requirements-train.txt` | training-only pins (not in `pyproject.toml`) |
| `DATASET_CARD.md`, `sample/` | generated overview and ~70 reviewable examples |
| `out/` | generated JSONL (gitignored); `out/slots_given/` is the ablation data |
