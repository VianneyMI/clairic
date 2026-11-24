from typing import Any

from check_schema_drift import Change, diff, report, summarize


def _field_schema(field: dict[str, Any]) -> dict[str, Any]:
    return {"properties": {"fields": {"additionalProperties": {"properties": field}}}}


def test_identical_documents_have_no_changes() -> None:
    schema = _field_schema({"decimals": {"type": "integer"}})
    assert diff(schema, schema) == []


def test_added_and_removed_keys() -> None:
    old = {"a": 1, "b": 2}
    new = {"b": 2, "c": 3}
    assert diff(old, new) == [
        Change("removed", ("a",), old=1),
        Change("added", ("c",), new=3),
    ]


def test_enum_members_are_compared_as_values() -> None:
    old = {"enum": ["text", "number"]}
    new = {"enum": ["text", "compute", "boolean"]}
    assert diff(old, new) == [
        Change("values_removed", ("enum",), old=["number"]),
        Change("values_added", ("enum",), new=["compute", "boolean"]),
    ]


def test_reordered_values_are_a_change() -> None:
    assert diff(["a", "b"], ["b", "a"]) == [Change("changed", (), old=["a", "b"], new=["b", "a"])]


def test_type_widened_to_a_union_is_a_change() -> None:
    assert diff({"type": "array"}, {"type": ["array", "null"]}) == [
        Change("changed", ("type",), old="array", new=["array", "null"])
    ]


def test_lists_of_objects_are_compared_item_by_item() -> None:
    old = {"anyOf": [{"type": "string"}, {"type": "object"}]}
    new = {"anyOf": [{"type": "string"}, {"type": "object", "title": "Object"}]}
    assert diff(old, new) == [Change("added", ("anyOf", "1", "title"), new="Object")]


def test_bool_and_int_are_not_equal() -> None:
    assert diff({"x": True}, {"x": 1}) == [Change("changed", ("x",), old=True, new=1)]


def test_summary_uses_request_paths_and_sections() -> None:
    old = _field_schema(
        {
            "type": {"enum": ["text", "number"]},
            "scale": {"default": "linear", "type": "string"},
            "unit": {"description": "Unit label.", "type": "string"},
        }
    )
    new = _field_schema(
        {
            "type": {"enum": ["text", "number", "compute"]},
            "scale": {"type": "string"},
            "unit": {"description": "number and duration only.", "type": "string"},
            "documents": {"description": "Optional embedded PDFs.", "type": "array"},
            "properties": {"type": "object"},
        }
    )
    text = summarize("schema-input.json", diff(old, new))

    assert text.startswith("### `schema-input.json`: 5 changes\n")
    assert '**Removed**\n\n- `fields.*.scale.default`: was `"linear"`' in text
    assert "- `fields.*.documents`: Optional embedded PDFs." in text
    assert '- `fields.*.properties`: `{"type": "object"}`' in text
    assert '- `fields.*.type.enum`: new values `"compute"`' in text
    assert "- `fields.*.unit`:\n  - was: Unit label.\n  - now: number and duration only." in text
    assert text.index("**Removed**") < text.index("**Added**") < text.index("**Descriptions**")


def test_summary_of_list_items_and_extra_keys() -> None:
    old = {
        "properties": {
            "answers": {
                "additionalProperties": {
                    "properties": {"spans": {"items": {"type": "array"}}},
                }
            }
        }
    }
    new = {
        "properties": {
            "answers": {
                "additionalProperties": {
                    "additionalProperties": True,
                    "properties": {"spans": {"items": {"type": ["array", "null"]}}},
                }
            }
        }
    }
    text = summarize("schema-output.json", diff(old, new))

    assert "- `answers.*`: extra keys allowed" in text
    assert '- `answers.*.spans[].type`: `"array"` → `["array", "null"]`' in text


def test_report_without_changes() -> None:
    assert "match the vendored copies" in report([])
