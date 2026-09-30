"""Write frontend/src/api/fixtures.json from the FastAPI mock (the single source of mock data).

Run from the repo root:  python frontend/scripts/export_fixtures.py
"""

import json
from pathlib import Path

from citizengraph.api.main import mock_fixtures

OUT = Path(__file__).resolve().parents[1] / "src" / "api" / "fixtures.json"


def render() -> str:
    return json.dumps(mock_fixtures(), ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
