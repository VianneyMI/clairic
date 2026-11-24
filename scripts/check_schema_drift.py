"""Compare Cloudflare's published Clairic schemas with the copies vendored in tests/fixtures.

Prints a summary of what changed, property by property, then the full line diff. Exits with
status 1 when a schema changed. Clairic is in preview and Cloudflare does not announce schema
changes, so a change here means the answer models or specs may need an update.

Options:
    --update         Overwrite the vendored copies with the published schemas and exit 0.
    --report PATH    Also write the summary as Markdown to PATH.

The scheduled workflow (.github/workflows/schema-drift.yml) runs it with both options and turns
the report into an issue and a pull request.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import httpx

SCHEMAS = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "schemas"
BASE_URL = "https://developers.cloudflare.com/workers-ai/models/clairic"
NAMES = ("schema-input.json", "schema-output.json")

Kind = Literal["added", "removed", "changed", "values_added", "values_removed"]


@dataclass(frozen=True)
class Change:
    """One difference between two JSON documents, located by its key path."""

    kind: Kind
    path: tuple[str, ...]
    old: Any = None
    new: Any = None


def diff(old: Any, new: Any, path: tuple[str, ...] = ()) -> list[Change]:
    """Return the differences between two JSON values, as precise as their structure allows.

    Objects are compared key by key. Lists of plain values (enums, `required`, `type` unions)
    are compared as sets, so a new enum member shows up as one added value. Lists of objects
    of the same length are compared item by item.
    """
    if isinstance(old, dict) and isinstance(new, dict):
        old_obj, new_obj = cast("dict[str, Any]", old), cast("dict[str, Any]", new)
        changes: list[Change] = []
        for key in sorted(old_obj.keys() | new_obj.keys()):
            if key not in new_obj:
                changes.append(Change("removed", (*path, key), old=old_obj[key]))
            elif key not in old_obj:
                changes.append(Change("added", (*path, key), new=new_obj[key]))
            else:
                changes.extend(diff(old_obj[key], new_obj[key], (*path, key)))
        return changes
    if isinstance(old, list) and isinstance(new, list):
        old_list, new_list = cast("list[Any]", old), cast("list[Any]", new)
        if all(_is_scalar(v) for v in (*old_list, *new_list)):
            removed = [v for v in old_list if v not in new_list]
            added = [v for v in new_list if v not in old_list]
            changes = []
            if removed:
                changes.append(Change("values_removed", path, old=removed))
            if added:
                changes.append(Change("values_added", path, new=added))
            if not changes and old_list != new_list:
                changes.append(Change("changed", path, old=old_list, new=new_list))
            return changes
        if len(old_list) == len(new_list):
            return [
                change
                for i, (o, n) in enumerate(zip(old_list, new_list, strict=True))
                for change in diff(o, n, (*path, str(i)))
            ]
        return [Change("changed", path, old=old_list, new=new_list)]
    if _same(cast("object", old), cast("object", new)):
        return []
    return [Change("changed", path, old=old, new=new)]


def _same(old: object, new: object) -> bool:
    # `True == 1` in Python, but a schema that swaps one for the other has changed.
    return type(old) is type(new) and old == new


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


@dataclass
class _Path:
    text: str = ""
    names_property: bool = False  # the last segment is a property name, not a schema keyword
    keyword: str = ""  # the last segment when it is a schema keyword


def _readable(path: tuple[str, ...]) -> _Path:
    """Turn a JSON Schema key path into the property path a reader expects.

    `properties.answers.additionalProperties.properties.span.type` becomes `answers.*.span.type`:
    `properties` introduces a property name, `additionalProperties` is any key (`*`), `items` is
    a list item (`[]`) and a number is a position in a list.
    """
    out = _Path()
    i = 0
    while i < len(path):
        segment = path[i]
        if segment == "properties" and i + 1 < len(path):
            out.text += f".{path[i + 1]}" if out.text else path[i + 1]
            out.names_property, out.keyword = True, ""
            i += 2
            continue
        if segment == "additionalProperties":
            token = ".*" if out.text else "*"
        elif segment == "items":
            token = "[]"
        elif segment.isdigit():
            token = f"[{segment}]"
        else:
            token = f".{segment}" if out.text else segment
        out.text += token
        out.names_property, out.keyword = False, segment
        i += 1
    if not out.text:
        out.text = "(root)"
    return out


def _value(value: Any, limit: int = 100) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return f"`{text if len(text) <= limit else text[: limit - 1] + '…'}`"


def _values(values: list[Any]) -> str:
    return ", ".join(_value(v) for v in values)


def _describe_new_property(schema: Any) -> str:
    if isinstance(schema, dict):
        description = cast("dict[str, Any]", schema).get("description")
        if isinstance(description, str):
            return description
    return _value(schema)


@dataclass
class _Sections:
    removed: list[str] = field(default_factory=list[str])
    changed: list[str] = field(default_factory=list[str])
    added: list[str] = field(default_factory=list[str])
    descriptions: list[str] = field(default_factory=list[str])


def summarize(name: str, changes: list[Change]) -> str:
    """Render the changes of one schema file as a Markdown section, most disruptive first."""
    sections = _Sections()
    for change in changes:
        where = _readable(change.path)
        path = f"`{where.text}`"
        if where.keyword == "additionalProperties" and _is_scalar(change.new or change.old):
            owner = f"`{_readable(change.path[:-1]).text}`"
            rule = {True: "extra keys allowed", False: "extra keys rejected"}.get(change.new)
            sections.changed.append(f"- {owner}: {rule or 'extra-keys rule removed'}")
        elif where.keyword == "description":
            owner = f"`{_readable(change.path[:-1]).text}`"
            if change.kind == "added":
                sections.descriptions.append(f"- {owner} (new): {change.new}")
            elif change.kind == "removed":
                sections.descriptions.append(f"- {owner} (removed): was {change.old}")
            else:
                sections.descriptions.append(
                    f"- {owner}:\n  - was: {change.old}\n  - now: {change.new}"
                )
        elif change.kind == "added" and where.names_property:
            sections.added.append(f"- {path}: {_describe_new_property(change.new)}")
        elif change.kind == "added":
            sections.added.append(f"- {path}: {_value(change.new)}")
        elif change.kind == "values_added":
            sections.added.append(f"- {path}: new values {_values(change.new)}")
        elif change.kind == "removed":
            what = "property removed" if where.names_property else "was"
            sections.removed.append(f"- {path}: {what} {_value(change.old)}")
        elif change.kind == "values_removed":
            sections.removed.append(f"- {path}: values removed {_values(change.old)}")
        else:
            sections.changed.append(f"- {path}: {_value(change.old)} → {_value(change.new)}")

    lines = [f"### `{name}`: {len(changes)} change{'s' if len(changes) != 1 else ''}"]
    for title, items in (
        ("Removed", sections.removed),
        ("Changed", sections.changed),
        ("Added", sections.added),
        ("Descriptions", sections.descriptions),
    ):
        if items:
            lines += ["", f"**{title}**", "", *items]
    return "\n".join(lines) + "\n"


def report(sections: list[str]) -> str:
    """Render the full Markdown report from the per-file sections."""
    if not sections:
        return "## Clairic schema drift\n\nThe published schemas match the vendored copies.\n"
    return "\n".join(
        [
            "## Clairic schema drift",
            "",
            f"Cloudflare's published schemas ({BASE_URL}/) differ from the copies in "
            "`tests/fixtures/schemas/`. Paths read like the request and response: "
            "`*` is any field name, `[]` a list item.",
            "",
            *sections,
        ]
    )


def _normalized(text: str) -> str:
    return json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--update", action="store_true", help="overwrite the vendored copies")
    parser.add_argument("--report", type=Path, help="also write the summary as Markdown here")
    args = parser.parse_args(argv)

    sections: list[str] = []
    line_diffs: list[str] = []
    for name in NAMES:
        published = _normalized(httpx.get(f"{BASE_URL}/{name}", timeout=30).raise_for_status().text)
        vendored_path = SCHEMAS / name
        vendored = _normalized(vendored_path.read_text())
        if published == vendored:
            continue
        sections.append(summarize(name, diff(json.loads(vendored), json.loads(published))))
        line_diffs += difflib.unified_diff(
            vendored.splitlines(keepends=True),
            published.splitlines(keepends=True),
            fromfile=f"vendored/{name}",
            tofile=f"published/{name}",
        )
        if args.update:
            vendored_path.write_text(published)

    summary = report(sections)
    print(summary)
    if line_diffs:
        print("## Full diff\n")
        sys.stdout.writelines(line_diffs)
    if args.report:
        args.report.write_text(summary)
    return 1 if sections and not args.update else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
