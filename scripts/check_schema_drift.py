"""Compare Cloudflare's published Clairic schemas with the copies vendored in tests/fixtures.

Exits with status 1 and prints a diff when a schema changed. Clairic is in preview, so a change
means the answer models or specs may need an update; refresh the vendored copy with `--update`
once the SDK matches it.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

import httpx

SCHEMAS = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "schemas"
BASE_URL = "https://developers.cloudflare.com/workers-ai/models/clairic"


def _normalized(text: str) -> str:
    return json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def main(update: bool) -> int:
    changed = False
    for name in ("schema-input.json", "schema-output.json"):
        published = _normalized(httpx.get(f"{BASE_URL}/{name}", timeout=30).raise_for_status().text)
        vendored_path = SCHEMAS / name
        vendored = _normalized(vendored_path.read_text())
        if published == vendored:
            print(f"{name}: unchanged")
            continue
        changed = True
        print(f"{name}: changed")
        sys.stdout.writelines(
            difflib.unified_diff(
                vendored.splitlines(keepends=True),
                published.splitlines(keepends=True),
                fromfile=f"vendored/{name}",
                tofile=f"published/{name}",
            )
        )
        if update:
            vendored_path.write_text(published)
    return 1 if changed and not update else 0


if __name__ == "__main__":
    sys.exit(main(update="--update" in sys.argv[1:]))
