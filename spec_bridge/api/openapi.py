"""Write the API contract for the review UI (W5-4, D-061): web/openapi.json.

    uv run python -m spec_bridge.api.openapi

No server is started. The UI generates its TypeScript types from this file
(`npm --prefix web run gen:api`), so a changed response model breaks `tsc`, not the screen.
"""

import json
import sys
from pathlib import Path

from spec_bridge.api.app import app
from spec_bridge.normalize.dictionary import ROOT

OUTPUT = ROOT / "web/openapi.json"


def export(path: Path = OUTPUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return path


if __name__ == "__main__":
    print(export(Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT))
