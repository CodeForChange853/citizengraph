# %% [markdown]
# # Core 1 QLoRA fine-tune (Kaggle free GPU), written as notebook cells
#
# **UNTESTED ON A GPU.** The repository's environment has no GPU, so neither this script nor
# `eval_generate.py`'s model path has ever run on one. Only the dataset, the prompt format and
# the scoring code are tested (on CPU). Expect to fix small things on the first Kaggle run.
# APIs used are Unsloth's documented `FastLanguageModel`, `get_chat_template`,
# `train_on_responses_only`, `save_pretrained_merged`, `save_pretrained_gguf`, and TRL's
# `SFTTrainer` / `SFTConfig`; argument names that changed between TRL releases are looked up
# with `inspect` instead of guessed.
#
# ## What the first Kaggle run must check
# 1. GPU: Settings -> Accelerator -> **GPU T4** (compute capability 7.5). A P100 is 6.0, below
#    Unsloth's documented minimum of 7.0, so it will probably not work. Cell 2 stops on <7.0.
# 2. Internet is ON (pip, Hugging Face download, and the GGUF cell builds llama.cpp).
# 3. `pip install -r training/requirements-train.txt` does not downgrade or reinstall torch, and
#    `import unsloth` (before transformers/trl, as Unsloth requires) works.
# 4. Model access: the default is Unsloth's public 4-bit mirror of Llama-3-8B-Instruct. The
#    original `meta-llama/Meta-Llama-3-8B-Instruct` is GATED: accept the Llama 3 licence on the
#    model page, add HF_TOKEN in Kaggle Secrets, and change MODEL_NAME. The licence check for
#    thesis use is still open (CLAUDE.md, open question 5).
# 5. fp16 only (T4 has no bf16): the loss must stay finite. If it turns NaN, lower LEARNING_RATE
#    to 1e-4 first.
# 6. Cell 7 prints one training example with the masked prompt: only the assistant answer (the
#    three header lines `intent:` / `shape:` / `variants:`, the Cypher and the closing
#    `<|eot_id|>`) may appear as trained text.
# 7. Step time and peak VRAM (printed) fit: ~6,400 examples of about 600 tokens (most of it the
#    fixed system message) x 2 epochs must finish well inside the 12-hour session limit (and the
#    weekly GPU quota). Lower EPOCHS or batch size if not; MAX_SEQ_LEN 1280 is checked in cell 5.
# 8. Validation loss falls (it runs on VAL_SUBSET examples only, to keep evaluation short); cell
#    10 quick eval: guardrail-valid, intent and exact-match rates on validation examples.
# 11. The ablation: run the whole notebook twice, once on the default data (slots INFERRED: the
#    prompt has targets, language and phrase) and once with SLOTS_GIVEN = True (the `slots_given/`
#    files: the same examples with intent and variants added to the prompt), and compare both with
#    `training/eval_generate.py` on the same test split.
# 9. Disk: /kaggle/working is limited (about 20 GB). The merge (16-bit) goes to /tmp; the GGUF
#    cell needs a 16 GB f16 intermediate before the ~5 GB Q4_K_M file. If it runs out of disk,
#    download the LoRA adapter (cell 9) and convert on another machine.
# 10. After import into llama.cpp/Ollama: the Llama-3 chat template is applied and generation
#     stops at `<|eot_id|>`. The inference prompt must come from
#     `citizengraph.core1.prompt.build_prompt`, the same format as the training data.
#
# ## Data
# Generate the data locally (`python -m training.generate_dataset --seed 0`), then upload
# `training/out/train.jsonl` and `validation.jsonl` (and the `slots_given/` folder for the
# ablation) as a Kaggle Dataset and attach it.
# No data here may come from an LLM, and `eval/heldout/` must never be uploaded.

# %% [markdown]
# ## Cell 1: install (restart the session after this if pip replaced anything)

# %%
import subprocess
import sys
from pathlib import Path

REQUIREMENTS = Path("training/requirements-train.txt")  # upload the repo, or paste the pins
if REQUIREMENTS.exists():
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(REQUIREMENTS)], check=True
    )
else:
    print("requirements-train.txt not found: install the pinned packages by hand.")

# %% [markdown]
# ## Cell 2: settings and GPU check

# %%
import json
import os

import torch

MODEL_NAME = "unsloth/llama-3-8b-Instruct-bnb-4bit"  # public mirror of Llama-3-8B-Instruct, 4-bit
MAX_SEQ_LEN = 1280  # examples are ~600 tokens (prompt v2 carries the schema); see cell 5
SLOTS_GIVEN = False  # True: the ablation data, intent and variants given in the prompt
VAL_SUBSET = 400  # validation examples used for the loss during training
LORA_R = 16
LORA_ALPHA = 16
LEARNING_RATE = 2e-4
EPOCHS = 2
PER_DEVICE_BATCH = 2
GRAD_ACCUM = 8  # effective batch 16
SEED = 3407
WORK = Path("/kaggle/working")
CHECKPOINTS = WORK / "checkpoints"  # survives in the notebook's output
ADAPTER_DIR = WORK / "core1-lora"
MERGED_DIR = Path("/tmp/core1-merged")  # 16 GB: kept out of /kaggle/working on purpose
GGUF_DIR = WORK / "core1-gguf"

assert torch.cuda.is_available(), "no GPU: set Accelerator to GPU T4 in the notebook settings"
name = torch.cuda.get_device_name(0)
major, minor = torch.cuda.get_device_capability(0)
print(f"GPU: {name}, compute capability {major}.{minor}, torch {torch.__version__}")
assert (major, minor) >= (7, 0), (
    f"{name} is below Unsloth's minimum compute capability 7.0 (a P100 is 6.0): use a T4"
)
FP16, BF16 = True, False  # T4 has no bf16; never switch this on here


def find_data_dir() -> Path:
    candidates = [Path(os.environ["CORE1_DATA"])] if "CORE1_DATA" in os.environ else []
    candidates += [p.parent for p in sorted(Path("/kaggle/input").glob("*/train.jsonl"))]
    candidates += [Path("training/out")]
    if SLOTS_GIVEN:  # the ablation files sit in a slots_given/ folder next to the others
        candidates = [d / "slots_given" for d in candidates] + candidates
    for directory in candidates:
        if (directory / "train.jsonl").is_file() and (directory / "validation.jsonl").is_file():
            return directory
    raise FileNotFoundError("train.jsonl / validation.jsonl not found: attach the dataset")


DATA_DIR = find_data_dir()
print("data:", DATA_DIR)

# %% [markdown]
# ## Cell 3: load the 4-bit base model (import unsloth FIRST)

# %%
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LEN,
    dtype=torch.float16,
    load_in_4bit=True,
)

# %% [markdown]
# ## Cell 4: LoRA on all linear projections (r=16)

# %%
model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_R,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=LORA_ALPHA,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=SEED,
)
model.print_trainable_parameters()

# %% [markdown]
# ## Cell 5: data in chat format -> Llama-3 template text

# %%
from datasets import load_dataset
from unsloth.chat_templates import get_chat_template

tokenizer = get_chat_template(tokenizer, chat_template="llama-3")
raw = load_dataset(
    "json",
    data_files={
        "train": str(DATA_DIR / "train.jsonl"),
        "validation": str(DATA_DIR / "validation.jsonl"),
    },
)


def to_text(batch):
    return {
        "text": [
            tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=False)
            for m in batch["messages"]
        ]
    }


data = raw.map(to_text, batched=True, remove_columns=raw["train"].column_names)
data["validation"] = (
    data["validation"].shuffle(seed=SEED).select(range(min(VAL_SUBSET, len(data["validation"]))))
)
lengths = [
    len(tokenizer(t, add_special_tokens=False).input_ids) for t in data["train"]["text"][:500]
]
print(
    f"train {len(data['train'])}, validation {len(data['validation'])}; "
    f"token length of 500 examples: max {max(lengths)}, mean {sum(lengths) / len(lengths):.0f}"
)
assert max(lengths) < MAX_SEQ_LEN, "raise MAX_SEQ_LEN: examples would be truncated"

# %% [markdown]
# ## Cell 6: trainer, completions only, fp16, checkpoints, validation loss

# %%
import inspect

from trl import SFTConfig, SFTTrainer
from unsloth.chat_templates import train_on_responses_only

config_args = {
    "output_dir": str(CHECKPOINTS),
    "dataset_text_field": "text",
    "per_device_train_batch_size": PER_DEVICE_BATCH,
    "per_device_eval_batch_size": PER_DEVICE_BATCH,
    "gradient_accumulation_steps": GRAD_ACCUM,
    "num_train_epochs": EPOCHS,
    "learning_rate": LEARNING_RATE,
    "lr_scheduler_type": "cosine",
    "warmup_ratio": 0.03,
    "weight_decay": 0.01,
    "optim": "adamw_8bit",
    "fp16": FP16,
    "bf16": BF16,
    "logging_steps": 10,
    "eval_strategy": "steps",
    "eval_steps": 100,
    "save_strategy": "steps",
    "save_steps": 100,
    "save_total_limit": 2,
    "packing": False,
    "seed": SEED,
    "report_to": "none",
}
# TRL renamed some arguments between releases: pick whichever this install has.
cfg_params = inspect.signature(SFTConfig.__init__).parameters
config_args["max_length" if "max_length" in cfg_params else "max_seq_length"] = MAX_SEQ_LEN
trainer_params = inspect.signature(SFTTrainer.__init__).parameters
tok_arg = "processing_class" if "processing_class" in trainer_params else "tokenizer"
print(
    "SFTConfig length argument:",
    [k for k in config_args if k.startswith("max_")],
    "| SFTTrainer tokenizer argument:",
    tok_arg,
)

trainer = SFTTrainer(
    model=model,
    args=SFTConfig(**config_args),
    train_dataset=data["train"],
    eval_dataset=data["validation"],
    **{tok_arg: tokenizer},
)
# Train on the assistant answer only (the Cypher and <|eot_id|>); system and user are masked.
trainer = train_on_responses_only(
    trainer,
    instruction_part="<|start_header_id|>user<|end_header_id|>\n\n",
    response_part="<|start_header_id|>assistant<|end_header_id|>\n\n",
)

# %% [markdown]
# ## Cell 7: check the masking before spending GPU hours

# %%
example = trainer.train_dataset[0]
labels = [t for t in example["labels"] if t != -100]
print("trained tokens in example 0:", len(labels), "of", len(example["input_ids"]))
print("----- trained text (must be only the header lines, the Cypher and <|eot_id|>) -----")
print(tokenizer.decode(labels))

# %% [markdown]
# ## Cell 8: train (checkpoints land in /kaggle/working/checkpoints)

# %%
torch.cuda.reset_peak_memory_stats()
result = (
    trainer.train()
)  # to resume after a session reset: trainer.train(resume_from_checkpoint=True)
print(result.metrics)
print(f"peak VRAM: {torch.cuda.max_memory_allocated() / 1e9:.1f} GB")
print("eval:", trainer.evaluate())

# %% [markdown]
# ## Cell 9: save the LoRA adapter (small; download it from the Output tab)

# %%
model.save_pretrained(str(ADAPTER_DIR))
tokenizer.save_pretrained(str(ADAPTER_DIR))
print("adapter saved:", ADAPTER_DIR)

# %% [markdown]
# ## Cell 10: quick eval on validation examples (greedy decoding)

# %%
FastLanguageModel.for_inference(model)
SAMPLE = 100
all_rows = (DATA_DIR / "validation.jsonl").read_text(encoding="utf-8").splitlines()
val_rows = [json.loads(x) for x in all_rows[:: max(1, len(all_rows) // SAMPLE)][:SAMPLE]]
outputs = []
for row in val_rows:
    prompt_ids = tokenizer.apply_chat_template(
        row["messages"][:2], add_generation_prompt=True, return_tensors="pt"
    ).to("cuda")
    generated = model.generate(
        input_ids=prompt_ids,
        max_new_tokens=600,  # three header lines and the longest query
        do_sample=False,
        use_cache=True,
        pad_token_id=tokenizer.eos_token_id,
    )
    outputs.append(
        tokenizer.decode(generated[0][prompt_ids.shape[1] :], skip_special_tokens=True).strip()
    )

exact = sum(
    " ".join(o.split()) == " ".join(r["messages"][2]["content"].split())
    for o, r in zip(outputs, val_rows, strict=True)
)
print(f"exact match on {len(val_rows)} validation examples: {exact / len(val_rows):.3f}")
try:  # needs `pip install -e .` of the repo (guardrail, completion format); skipped otherwise
    from citizengraph.core1.output import parse_completion

    parsed = [parse_completion(o) for o in outputs]
    gold = [parse_completion(r["messages"][2]["content"]) for r in val_rows]
    print("header present:", sum(not p.problems for p in parsed) / len(parsed))
    print(
        "intent accuracy:",
        sum(p.intents == g.intents for p, g in zip(parsed, gold, strict=True)) / len(parsed),
    )
    from citizengraph.guardrail.validator import validate_cypher

    print("guardrail-valid:", sum(validate_cypher(p.cypher).ok for p in parsed) / len(parsed))
except ImportError:
    print(
        "citizengraph not installed here: run training/eval_generate.py later for the full report"
    )
(WORK / "validation_outputs.jsonl").write_text(
    "".join(json.dumps({"output": o}) + "\n" for o in outputs), encoding="utf-8"
)

# %% [markdown]
# ## Cell 11: merge the adapter into 16-bit weights (separate cell; ~16 GB in /tmp)

# %%
model.save_pretrained_merged(str(MERGED_DIR), tokenizer, save_method="merged_16bit")
print("merged model:", MERGED_DIR)

# %% [markdown]
# ## Cell 12: export GGUF Q4_K_M (separate cell; needs internet, builds llama.cpp, ~16 GB temp)

# %%
model.save_pretrained_gguf(str(GGUF_DIR), tokenizer, quantization_method="q4_k_m")
for path in sorted(GGUF_DIR.glob("*.gguf")):
    print(path, f"{path.stat().st_size / 1e9:.1f} GB")

# %% [markdown]
# Download `core1-gguf/*.gguf` (and `core1-lora/`) from the notebook's Output tab. Never commit
# weights to the repository (`.gitignore` excludes `*.gguf`, `*.safetensors`, `*.bin`).
