"""Shared setup for the training tests: the repo root is put on ``sys.path`` so that
``training.<module>`` can be imported without touching pyproject.toml (training is not installed).
"""

import importlib
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load(name: str) -> ModuleType:
    """Import ``training.<name>``."""
    return importlib.import_module(f"training.{name}")
