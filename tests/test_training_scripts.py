"""The GPU scripts cannot run here, but their shape and pins can be checked on CPU."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from test_training_common import ROOT

TRAINING = ROOT / "training"


def test_qlora_script_parses_and_is_written_as_notebook_cells():
    text = (TRAINING / "qlora_kaggle.py").read_text(encoding="utf-8")
    ast.parse(text)
    assert text.count("\n# %%\n") >= 10  # code cells
    assert text.startswith("# %% [markdown]")


def test_qlora_script_says_it_is_untested_and_lists_the_first_run_checks():
    head = (TRAINING / "qlora_kaggle.py").read_text(encoding="utf-8").split("# %%\n")[0]
    assert "UNTESTED ON A GPU" in head
    assert "What the first Kaggle run must check" in head
    assert "gated" in head.lower() and "GATED" in head
    assert "P100" in head and "T4" in head
    eval_head = (TRAINING / "eval_generate.py").read_text(encoding="utf-8").split('"""')[1]
    assert "NOT been run against a real model" in eval_head


def test_qlora_script_uses_the_required_settings():
    text = (TRAINING / "qlora_kaggle.py").read_text(encoding="utf-8")
    assert "LORA_R = 16" in text
    for module in ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"):
        assert f'"{module}"' in text
    assert "FP16, BF16 = True, False" in text
    assert '"fp16": FP16' in text and '"bf16": BF16' in text
    assert "load_in_4bit=True" in text
    assert "Llama-3-8b-Instruct".lower() in text.lower()
    assert "train_on_responses_only" in text
    assert "/kaggle/working" in text and "eval_steps" in text and "save_steps" in text
    assert "save_pretrained_merged" in text
    assert "save_pretrained_gguf" in text and "q4_k_m" in text
    # merge and GGUF export are separate cells
    cells = text.split("\n# %%\n")
    merge = [c for c in cells if "save_pretrained_merged(" in c]
    gguf = [c for c in cells if "save_pretrained_gguf(" in c]
    assert len(merge) == 1 and len(gguf) == 1 and merge[0] is not gguf[0]
    # never bf16=True anywhere, and no held-out folder
    assert not re.search(r"bf16\s*=\s*True", text)
    assert "heldout" not in text.replace("eval/heldout/` must never be uploaded", "")


def test_training_requirements_are_pinned_and_stay_out_of_pyproject():
    lines = [
        ln.strip()
        for ln in (TRAINING / "requirements-train.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    pinned = {ln.split("==")[0] for ln in lines if "==" in ln}
    assert {"unsloth", "trl", "transformers", "peft", "datasets", "accelerate", "bitsandbytes"} <= (
        pinned
    )
    assert not [ln for ln in lines if re.match(r"(torch|torchvision|xformers|triton)\b", ln)]
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for name in ("unsloth", "trl", "peft", "bitsandbytes"):
        assert name not in pyproject


def test_gitignore_keeps_generated_data_and_weights_out():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "training/out/" in ignore
    assert "*.gguf" in ignore and "*.safetensors" in ignore


def test_training_package_does_not_import_the_graph_loader_or_a_writer():
    for path in Path(TRAINING).glob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "execute_write" not in src and "graph.load" not in src.replace("graph.loader", "")
