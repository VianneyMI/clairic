"""Access to responses recorded from the live Clairic API (see tests/fixtures/responses)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict, cast

RESPONSES = Path(__file__).parent / "fixtures" / "responses"


class Recording(TypedDict):
    status: int
    headers: dict[str, str]
    request: dict[str, Any] | str
    response: dict[str, Any] | str


def load(name: str) -> Recording:
    """Return the recording stored in `fixtures/responses/<name>.json`."""
    return cast(Recording, json.loads((RESPONSES / f"{name}.json").read_text()))


def answers(name: str) -> dict[str, dict[str, Any]]:
    """Return the raw `answers` object of a successful recording."""
    response = load(name)["response"]
    assert isinstance(response, dict)
    return cast(dict[str, dict[str, Any]], response["result"]["answers"])


def state(name: str) -> str:
    """Return the `state` sent in a recording."""
    request = load(name)["request"]
    assert isinstance(request, dict)
    return cast(str, request["state"])
