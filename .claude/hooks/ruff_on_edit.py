"""PostToolUse hook: lint the Python file that was just edited with ruff.

Reads the hook JSON on stdin and runs ``ruff check --no-fix`` on
``tool_input.file_path``. Violations go to stderr with exit code 2, which is
how a PostToolUse hook hands text back to the model. Every other path exits 0:
not a ``.py`` file, missing file, unreadable stdin, no project root, no
suitable ruff, ruff crash or timeout. The file is never modified.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VERSION_TIMEOUT_S = 3
CHECK_TIMEOUT_S = 15
RUFF_PIN = re.compile(r"ruff==(\d+(?:\.\d+)*)")
VERSION = re.compile(r"\d+(?:\.\d+)+")


def edited_file() -> Path | None:
    """Return the edited ``.py`` file named on stdin, or None to skip."""
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if not isinstance(payload, dict):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw.lower().endswith(".py"):
        return None
    path = Path(raw)
    if not path.is_absolute() or not path.is_file():
        return None
    return path.resolve()


def find_root(path: Path) -> Path | None:
    """Return the nearest parent directory that holds ``pyproject.toml``."""
    for parent in path.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def pinned_version(root: Path) -> str | None:
    """Return the ``ruff==X.Y.Z`` version pinned in ``pyproject.toml``."""
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = RUFF_PIN.search(text)
    return match.group(1) if match else None


def find_ruff(root: Path) -> str | None:
    """Return the project venv's ruff, or a PATH ruff at the pinned version."""
    for candidate in (root / ".venv/Scripts/ruff.exe", root / ".venv/bin/ruff"):
        if candidate.is_file():
            return str(candidate)
    on_path = shutil.which("ruff")
    pin = pinned_version(root)
    if on_path is None or pin is None:
        return None
    result = subprocess.run(
        [on_path, "--version"],
        capture_output=True,
        text=True,
        timeout=VERSION_TIMEOUT_S,
        check=False,
    )
    match = VERSION.search(result.stdout)
    if result.returncode != 0 or match is None or match.group(0) != pin:
        return None
    return on_path


def main() -> int:
    """Return the hook's exit code: 2 for lint violations, otherwise 0."""
    path = edited_file()
    if path is None:
        return 0
    root = find_root(path)
    if root is None:
        return 0
    ruff = find_ruff(root)
    if ruff is None:
        return 0
    shown = path.relative_to(root).as_posix()
    result = subprocess.run(
        [ruff, "check", "--no-fix", "--force-exclude", "--output-format=concise", shown],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=CHECK_TIMEOUT_S,
        check=False,
    )
    if result.returncode != 1:
        return 0
    report = (result.stdout.strip() + "\n" + result.stderr.strip()).strip()
    message = f"ruff check found problems in {shown} (not auto-fixed):\n{report}\n"
    sys.stderr.buffer.write(message.encode("utf-8", errors="replace"))
    sys.stderr.flush()
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:  # noqa: BLE001 - a hook failure must never block an edit
        code = 0
    sys.exit(code)
