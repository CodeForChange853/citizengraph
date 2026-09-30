# Training

Holds the dataset generator and the QLoRA notebook. **Training does not run here or on
CPU/integrated-graphics machines**; run the notebook on a free GPU (Kaggle/Colab).

Rules: data comes from our own generators (templates, rules, noise injection), never from
LLM API outputs; never read `../eval/heldout/`; use fp16 (P100/T4 have no bf16).
Planned: `generate_dataset.py`, `noise.py`, `qlora_train.ipynb`, `export_gguf.md`.
