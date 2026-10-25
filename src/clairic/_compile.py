"""Translation between extraction models and the Clairic request and response."""

from __future__ import annotations

import datetime as dt
import functools
import re
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from clairic.answers import (
    DateAnswer,
    DateEstimateAnswer,
    DatetimeAnswer,
    DurationAnswer,
    EstimateAnswer,
    ForecastAnswer,
    ListAnswer,
    NumberAnswer,
    TextAnswer,
    TextListAnswer,
    TimeAnswer,
)
from clairic.errors import ModelDefinitionError
from clairic.specs import (
    Date,
    Datetime,
    Duration,
    Estimate,
    Forecast,
    List,
    Number,
    Spec,
    Text,
    Time,
)

M = TypeVar("M", bound=BaseModel)

FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$")
"""Field names the Clairic API accepts."""


@dataclass(frozen=True)
class _AnswerKind:
    """How an answer class maps to a Clairic field."""

    spec_type: type[Spec]
    spec_required: bool = False


_KINDS: dict[type[BaseModel], _AnswerKind] = {
    TextAnswer: _AnswerKind(Text),
    NumberAnswer: _AnswerKind(Number),
    DateAnswer: _AnswerKind(Date),
    TimeAnswer: _AnswerKind(Time),
    DatetimeAnswer: _AnswerKind(Datetime),
    DurationAnswer: _AnswerKind(Duration),
    TextListAnswer: _AnswerKind(List),
    ListAnswer: _AnswerKind(List),
    EstimateAnswer: _AnswerKind(Estimate, spec_required=True),
    DateEstimateAnswer: _AnswerKind(Estimate, spec_required=True),
    ForecastAnswer: _AnswerKind(Forecast, spec_required=True),
}
_GENERIC = (NumberAnswer, DurationAnswer, ListAnswer, EstimateAnswer)
_SUPPORTED = ", ".join(
    f"{answer.__name__}[...]" if answer in _GENERIC else answer.__name__ for answer in _KINDS
)


def fields_payload(model: type[BaseModel]) -> dict[str, dict[str, Any]]:
    """Return the Clairic `fields` object for an extraction model.

    Raises:
        ModelDefinitionError:
            When a field of `model` cannot be sent to Clairic. The message names the field.
    """
    return {name: dict(spec) for name, spec in _compile(model)}


def build_data(model: type[M], answers: dict[str, Any]) -> M:
    """Return an instance of `model` holding the answers Clairic returned, keyed by field name."""
    return model.model_validate(answers)


@functools.cache
def _compile(model: type[BaseModel]) -> tuple[tuple[str, dict[str, Any]], ...]:
    if not model.model_fields:
        raise ModelDefinitionError(f"{model.__name__} has no fields; Clairic needs at least one")
    return tuple(
        _compile_field(model, attribute, info) for attribute, info in model.model_fields.items()
    )


def _compile_field(
    model: type[BaseModel], attribute: str, info: FieldInfo
) -> tuple[str, dict[str, Any]]:
    where = f"{model.__name__}.{attribute}"
    name = _clairic_name(where, attribute, info)
    origin, argument = _answer_class(where, info.annotation)
    kind = _KINDS[origin]
    spec = _spec(where, info, kind)

    payload: dict[str, Any] = {"type": spec.field_type}
    if info.description:
        payload["instructions"] = info.description
    payload.update(spec.to_payload())
    payload.update(_type_options(where, origin, argument, spec))
    return name, payload


def _clairic_name(where: str, attribute: str, info: FieldInfo) -> str:
    """Return the field name sent to Clairic: the alias when set, else the attribute name."""
    if info.validation_alias is not None and info.validation_alias != info.alias:
        raise ModelDefinitionError(
            f"{where}: validation_alias is not supported; use alias to rename the field"
        )
    name = info.alias or attribute
    if not FIELD_NAME.match(name):
        raise ModelDefinitionError(
            f"{where}: Clairic field names must match {FIELD_NAME.pattern}, got {name!r}"
        )
    return name


def _answer_class(where: str, annotation: Any) -> tuple[type[BaseModel], Any]:
    """Return the unparametrized answer class of an annotation and its type argument."""
    metadata = getattr(annotation, "__pydantic_generic_metadata__", None)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel) and metadata:
        origin = metadata["origin"] or annotation
        if origin in _KINDS:
            arguments = metadata["args"]
            if origin in _GENERIC and not arguments:
                raise ModelDefinitionError(
                    f"{where}: parametrize {origin.__name__} with its value type, "
                    f"for example {origin.__name__}[float]"
                )
            return origin, arguments[0] if arguments else None
    raise ModelDefinitionError(
        f"{where}: annotate the field with a Clairic answer type ({_SUPPORTED}), "
        f"got {annotation!r}. Answers already allow a None value; do not wrap them in Optional"
    )


def _spec(where: str, info: FieldInfo, kind: _AnswerKind) -> Spec:
    specs = [item for item in info.metadata if isinstance(item, Spec)]
    if len(specs) > 1:
        raise ModelDefinitionError(f"{where}: declare at most one spec, got {len(specs)}")
    if not specs:
        if kind.spec_required:
            raise ModelDefinitionError(
                f"{where}: add an {kind.spec_type.__name__}(...) spec with Annotated; "
                "its bounds are required"
            )
        return kind.spec_type()
    spec = specs[0]
    if not isinstance(spec, kind.spec_type):
        raise ModelDefinitionError(
            f"{where}: {type(spec).__name__} does not apply to this answer type; "
            f"use {kind.spec_type.__name__}"
        )
    return spec


def _type_options(where: str, origin: type[BaseModel], argument: Any, spec: Spec) -> dict[str, Any]:
    """Return the options implied by the answer type: `integer` and list `items`."""
    if origin in (NumberAnswer, DurationAnswer):
        return {"integer": True} if argument is int else {}
    if origin is TextListAnswer:
        return {"items": "text"}
    if origin is ListAnswer:
        if argument is dt.date:
            return {"items": "date"}
        return {"items": "number", "integer": True} if argument is int else {"items": "number"}
    if isinstance(spec, Estimate):
        _check_estimate_bounds(where, origin, argument, spec)
    return {}


def _check_estimate_bounds(
    where: str, origin: type[BaseModel], argument: Any, spec: Estimate
) -> None:
    date_bounds = isinstance(spec.min, dt.date)
    if origin is DateEstimateAnswer and not date_bounds:
        raise ModelDefinitionError(f"{where}: DateEstimateAnswer needs date bounds")
    if origin is EstimateAnswer and date_bounds:
        raise ModelDefinitionError(f"{where}: use DateEstimateAnswer for date bounds")
    if argument is int and not (
        isinstance(spec.step, (int, float)) and float(spec.step).is_integer()
    ):
        raise ModelDefinitionError(
            f"{where}: EstimateAnswer[int] needs a whole-number step, got {spec.step!r}"
        )
