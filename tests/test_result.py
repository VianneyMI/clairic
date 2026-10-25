import datetime as dt
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from recorded import answers, load

from clairic._compile import build_data
from clairic.answers import (
    DateAnswer,
    EstimateAnswer,
    ForecastAnswer,
    NumberAnswer,
    TextAnswer,
    TextListAnswer,
)
from clairic.result import Result, Usage
from clairic.specs import Estimate, Forecast


class InvoiceExtraction(BaseModel):
    invoice_number: TextAnswer
    due_date: DateAnswer
    total: NumberAnswer[float]
    contacts: TextListAnswer
    po_number: TextAnswer
    days_to_pay: Annotated[EstimateAnswer[int], Estimate(min=0, max=120, step=1)]


class Invoice(BaseModel):
    invoice_number: str
    due_date: dt.date
    total: float
    contacts: list[str]
    po_number: str | None
    days_to_pay: int


def _result(model: type[Any], fixture: str) -> Result[Any]:
    response = load(fixture)["response"]
    assert isinstance(response, dict)
    result = response["result"]
    return Result[model](
        data=build_data(model, result["answers"]),
        usage=Usage.model_validate(result["usage"]),
        truncated=result["truncated"],
        model=result["model"],
        request_id="21d0233d-a285-4f04-969e-1f63c84d097d",
    )


def test_values_as_returns_the_plain_values() -> None:
    """Should copy each answer value into the field of the same name."""
    invoice = _result(InvoiceExtraction, "invoice").values_as(Invoice)

    assert invoice == Invoice(
        invoice_number="INV-2291",
        due_date=dt.date(2026, 10, 2),
        total=1080,
        contacts=["Dana Ruiz", "Priya Shah"],
        po_number=None,
        days_to_pay=31,
    )


def test_values_as_rejects_none_in_a_required_field() -> None:
    """Should raise a validation error when a None value lands in a non-Optional field."""

    class StrictInvoice(BaseModel):
        po_number: str

    with pytest.raises(ValidationError, match="po_number"):
        _result(InvoiceExtraction, "invoice").values_as(StrictInvoice)


def test_values_as_fills_a_subset_of_fields() -> None:
    """Should leave out answers the target does not declare, even with extra='forbid'."""

    class Totals(BaseModel):
        model_config = ConfigDict(extra="forbid")
        total: float

    assert _result(InvoiceExtraction, "invoice").values_as(Totals) == Totals(total=1080)


def test_values_as_exports_forecasts_as_lists() -> None:
    """Should export a forecast as the list of its point forecasts."""

    class VisitorsExtraction(BaseModel):
        next: Annotated[ForecastAnswer, Forecast(min=0, max=5000, horizon=3)]

    class Visitors(BaseModel):
        next: list[float]

    visitors = _result(VisitorsExtraction, "forecast_no_interval").values_as(Visitors)

    assert visitors.next == answers("forecast_no_interval")["next"]["value"]


def test_result_round_trips_through_json() -> None:
    """Should restore an equal result from its JSON dump."""
    result = _result(InvoiceExtraction, "invoice")

    restored = Result[InvoiceExtraction].model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.values_as(Invoice) == result.values_as(Invoice)


def test_result_with_aliases_round_trips_through_json() -> None:
    """Should restore aliased fields, which are dumped under their Clairic names."""

    class Aliased(BaseModel):
        invoice_number: TextAnswer = Field(alias="invoice.number")
        total_usd: NumberAnswer[float] = Field(alias="total-usd")

    result = _result(Aliased, "options_state_text")

    restored = Result[Aliased].model_validate_json(result.model_dump_json())

    assert restored.data.invoice_number.value == "INV-9"
    assert restored == result


def test_usage_counts_the_state_once_per_pass() -> None:
    """Should report billed input tokens covering every pass (recorded 9k-token state)."""
    response = load("trunc_10k")["response"]
    assert isinstance(response, dict)

    usage = Usage.model_validate(response["result"]["usage"])

    assert usage.passes == 2
    assert usage.input_tokens == 2 * usage.state_tokens + usage.schema_tokens
