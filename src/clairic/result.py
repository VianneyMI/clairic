"""The outcome of an extraction: answers, token usage and request metadata."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_serializer,
)

from clairic.answers import Answer

__all__ = ["Result", "Usage"]

M = TypeVar("M", bound=BaseModel)
P = TypeVar("P", bound=BaseModel)


class Usage(BaseModel):
    """Token counts of an extraction. Clairic bills input tokens only.

    Fields that do not fit next to the input in one 8,192-token pass are split across parallel
    passes, and every pass reads the whole input: `input_tokens` counts the state once per pass.
    Fewer fields, or a shorter input, lower the number of passes.

    Attributes:
        state_tokens: int
            Tokens of the input text.
        image_tokens: int
            Tokens of the input images.
        schema_tokens: int
            Tokens of the field definitions.
        input_tokens: int
            Billed input tokens, across all passes.
        output_tokens: int
            Generated tokens, always 0: Clairic answers without generating text.
        passes: int
            Number of parallel passes the fields were split into.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    state_tokens: int
    image_tokens: int
    schema_tokens: int
    input_tokens: int
    output_tokens: int
    passes: int


class Result(BaseModel, Generic[M]):
    """Answers to an extraction, with its token usage and request metadata.

    A result serializes to JSON and back, so storing it keeps the answers, the usage and the
    request id together:

    ```python
    stored = res.model_dump_json()
    res = Result[Invoice].model_validate_json(stored)
    ```

    Attributes:
        data: M
            The extraction model, holding one answer per field.
        usage: Usage
            Token counts of the request.
        truncated: bool
            True when Clairic computed the answers on part of the input only.
        model: str
            Clairic model that answered.
        request_id: str | None
            Workers AI request id, to quote when contacting Cloudflare.
    """

    model_config = ConfigDict(frozen=True)

    data: M
    usage: Usage
    truncated: bool
    model: str
    request_id: str | None = None

    @field_serializer("data", mode="wrap")
    def _serialize_data_by_alias(
        self, data: M, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> Any:
        # Answers arrive keyed by Clairic field name (the alias), so dump them the same way.
        return data.model_dump(mode=info.mode, by_alias=True)

    def values_as(self, target: type[P]) -> P:
        """Return the answer values as an instance of `target`, a model of plain values.

        Each field of `target` receives the `value` of the answer with the same attribute name;
        answers without a matching field are left out. Pydantic validates the values, so a
        `None` value in a field of `target` that does not accept `None` raises
        `pydantic.ValidationError`.

        Args:
            target: type[P]
                Pydantic model with plain value fields, such as `total: float | None`.
        """
        values: dict[str, Any] = {}
        for attribute in type(self.data).model_fields:
            answer = getattr(self.data, attribute)
            if attribute in target.model_fields and isinstance(answer, Answer):
                values[attribute] = answer.model_dump(include={"value"})["value"]
        return target.model_validate(values)
