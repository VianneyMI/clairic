import datetime as dt
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, Field
from recorded import answers, load

from clairic._compile import build_data, fields_payload
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
from clairic.specs import Duration, Estimate, Forecast, Number, Text


class Invoice(BaseModel):
    """The invoice example of the Clairic model reference."""

    invoice_number: TextAnswer
    due_date: DateAnswer = Field(description="Issue date plus the net payment days")
    total: Annotated[NumberAnswer[float], Number(decimals=2, unit="USD")] = Field(
        description="Amount due including shipping"
    )
    contacts: TextListAnswer
    po_number: TextAnswer = Field(description="Purchase order number")
    days_to_pay: Annotated[EstimateAnswer[int], Estimate(min=0, max=120, step=1)] = Field(
        description="Days after issue until this invoice is paid"
    )


def test_reference_invoice_compiles_to_the_documented_fields() -> None:
    """Should produce the `fields` object of the Clairic reference invoice example."""
    request = load("invoice")["request"]
    assert isinstance(request, dict)

    assert fields_payload(Invoice) == request["fields"]


def test_every_field_type_compiles_with_its_implied_options() -> None:
    """Should derive integer and list items from the answer type parameters."""

    class Everything(BaseModel):
        count: NumberAnswer[int]
        when: DateAnswer
        at: TimeAnswer
        meeting: DatetimeAnswer
        wait: Annotated[DurationAnswer[int], Duration(unit="days")]
        waited: DurationAnswer[float]
        names: TextListAnswer
        quantities: ListAnswer[int]
        prices: ListAnswer[float]
        dates: ListAnswer[dt.date]
        sale: Annotated[
            DateEstimateAnswer,
            Estimate(min=dt.date(2026, 1, 1), max=dt.date(2027, 1, 1), step="month"),
        ]
        visitors: Annotated[ForecastAnswer, Forecast(min=0, max=5000, horizon=4, interval="day")]

    assert fields_payload(Everything) == {
        "count": {"type": "number", "integer": True},
        "when": {"type": "date"},
        "at": {"type": "time"},
        "meeting": {"type": "datetime"},
        "wait": {"type": "duration", "unit": "days", "integer": True},
        "waited": {"type": "duration", "unit": "seconds"},
        "names": {"type": "list", "items": "text"},
        "quantities": {"type": "list", "items": "number", "integer": True},
        "prices": {"type": "list", "items": "number"},
        "dates": {"type": "list", "items": "date"},
        "sale": {"type": "estimate", "min": "2026-01-01", "max": "2027-01-01", "step": "month"},
        "visitors": {"type": "forecast", "min": 0, "max": 5000, "horizon": 4, "interval": "day"},
    }


def test_alias_is_the_clairic_field_name() -> None:
    """Should send the alias as the field name, allowing dots and dashes."""

    class Aliased(BaseModel):
        invoice_number: TextAnswer = Field(alias="invoice.number")
        total_usd: NumberAnswer[float] = Field(alias="total-usd")

    assert set(fields_payload(Aliased)) == {"invoice.number", "total-usd"}


def test_aliased_answers_are_read_back_into_the_model() -> None:
    """Should fill aliased attributes from answers keyed by the Clairic field name."""

    class Aliased(BaseModel):
        invoice_number: TextAnswer = Field(alias="invoice.number")
        total_usd: NumberAnswer[float] = Field(alias="total-usd")

    data = build_data(Aliased, answers("options_state_text"))

    assert data.invoice_number.value == "INV-9"
    assert data.total_usd.value == 10


def test_payload_is_a_fresh_copy_on_every_call() -> None:
    """Should not let a caller mutate the cached compilation."""
    fields_payload(Invoice)["total"]["decimals"] = 6

    assert fields_payload(Invoice)["total"]["decimals"] == 2


class _NotAnAnswer(BaseModel):
    total: float


class _Optional(BaseModel):
    total: TextAnswer | None


class _Unparametrized(BaseModel):
    total: NumberAnswer  # type: ignore[type-arg]


class _MissingSpec(BaseModel):
    days: EstimateAnswer[int]


class _WrongSpec(BaseModel):
    total: Annotated[NumberAnswer[float], Text()]


class _TwoSpecs(BaseModel):
    total: Annotated[NumberAnswer[float], Number(decimals=1), Number(decimals=2)]


class _DateBoundsOnNumbers(BaseModel):
    when: Annotated[EstimateAnswer[int], Estimate(min=dt.date(2026, 1, 1), max=dt.date(2027, 1, 1))]


class _NumberBoundsOnDates(BaseModel):
    when: Annotated[DateEstimateAnswer, Estimate(min=0, max=10)]


class _FractionalStep(BaseModel):
    days: Annotated[EstimateAnswer[int], Estimate(min=0, max=10, step=0.5)]


class _MissingStep(BaseModel):
    days: Annotated[EstimateAnswer[int], Estimate(min=0, max=10)]


class _InvalidName(BaseModel):
    total: TextAnswer = Field(alias="1total")


class _ValidationAlias(BaseModel):
    total: TextAnswer = Field(validation_alias="sum")


class _Empty(BaseModel):
    pass


@pytest.mark.parametrize(
    ("model", "message"),
    [
        (_NotAnAnswer, "annotate the field with a Clairic answer type"),
        (_Optional, "do not wrap them in Optional"),
        (_Unparametrized, r"NumberAnswer\[float\]"),
        (_MissingSpec, "add an Estimate"),
        (_WrongSpec, "use Number"),
        (_TwoSpecs, "at most one spec"),
        (_DateBoundsOnNumbers, "use DateEstimateAnswer"),
        (_NumberBoundsOnDates, "needs date bounds"),
        (_FractionalStep, "whole-number step"),
        (_MissingStep, "whole-number step"),
        (_InvalidName, "field names must match"),
        (_ValidationAlias, "validation_alias"),
        (_Empty, "no fields"),
    ],
)
def test_invalid_models_are_rejected_with_the_field_name(
    model: type[BaseModel], message: str
) -> None:
    """Should raise ModelDefinitionError naming the problem before any request."""
    with pytest.raises(ModelDefinitionError, match=message) as raised:
        fields_payload(model)

    assert model.__name__ in str(raised.value)


def test_recorded_types_compile_and_read_back() -> None:
    """Should read every recorded answer of a full extraction back into the model."""

    class Recorded(BaseModel):
        order_id: TextAnswer
        amount_with_tax: NumberAnswer[float]
        delivery_date: DateAnswer
        rain_exposure: Annotated[DurationAnswer[float], Duration(unit="hours")]
        damage: TextListAnswer
        quantities: ListAnswer[int]

    raw: dict[str, Any] = answers("types_present")
    data = build_data(Recorded, raw)

    assert data.rain_exposure.unit == "hours"
    assert data.quantities.value == [2, 1, 4]
