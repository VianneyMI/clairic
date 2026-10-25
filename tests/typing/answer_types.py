"""Static typing guarantees of extraction models, checked by pyright (never executed).

`reportUnnecessaryTypeIgnoreComment` turns each `pyright: ignore` below into an assertion that
the line is a type error.
"""
# pyright: reportUnnecessaryTypeIgnoreComment=true

import datetime as dt
from typing import Annotated

from pydantic import BaseModel
from typing_extensions import assert_type

from clairic.answers import (
    DateEstimateAnswer,
    DurationAnswer,
    EstimateAnswer,
    ForecastAnswer,
    ListAnswer,
    NumberAnswer,
    Span,
    TextAnswer,
    TextListAnswer,
)
from clairic.result import Result
from clairic.specs import Estimate, Forecast


class Extraction(BaseModel):
    invoice_number: TextAnswer
    total: NumberAnswer[float]
    items: NumberAnswer[int]
    wait: DurationAnswer[int]
    contacts: TextListAnswer
    dates: ListAnswer[dt.date]
    days_to_pay: Annotated[EstimateAnswer[int], Estimate(min=0, max=120, step=1)]
    sale: Annotated[DateEstimateAnswer, Estimate(min=dt.date(2026, 1, 1), max=dt.date(2027, 1, 1))]
    visitors: Annotated[ForecastAnswer, Forecast(min=0, max=10, horizon=2)]


def check(data: Extraction) -> None:
    assert_type(data.invoice_number.value, str | None)
    assert_type(data.invoice_number.span, Span | None)
    assert_type(data.total.value, float | None)
    assert_type(data.items.guess, int | None)
    assert_type(data.wait.value, int | None)
    assert_type(data.contacts.spans, list[Span])
    assert_type(data.dates.value, list[dt.date])
    assert_type(data.dates.confidences, list[float])
    assert_type(data.days_to_pay.p90, int)
    assert_type(data.days_to_pay.mean, float)
    assert_type(data.sale.median, dt.date)
    assert_type(data.visitors.steps[0].p10, float)

    _ = data.total.span  # pyright: ignore
    _ = data.days_to_pay.confidence  # pyright: ignore
    _ = data.sale.p_below  # pyright: ignore
    _ = data.dates.spans  # pyright: ignore
    _ = data.invoice_numbr  # pyright: ignore


class Values(BaseModel):
    total: float | None


def check_result(result: Result[Extraction]) -> None:
    assert_type(result.data, Extraction)
    assert_type(result.data.total.value, float | None)
    assert_type(result.values_as(Values), Values)
    assert_type(result.usage.input_tokens, int)
