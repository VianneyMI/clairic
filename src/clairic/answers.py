"""Typed answers returned by Clairic, one class per response shape.

Declare an extraction model by annotating each field with one of these classes. The class
chooses the Clairic field type, and after extraction the field holds the answer: the value and
the metadata Clairic attaches to it.

Clairic answers a field with `value = None` when the input does not determine it. Single-value
answers carry a confidence score and the probability that the value is absent (`p_null`).
Estimates and forecasts carry a distribution. Typed output constrains the shape of an answer,
not its correctness: use `confidence`, `p_null` and the percentile range to decide which
answers to act on and which to review.

Source: https://developers.cloudflare.com/workers-ai/concepts/extraction-models/
"""

from __future__ import annotations

import datetime as dt
from typing import Generic, Literal, NamedTuple, TypeVar

from pydantic import BaseModel, ConfigDict

__all__ = [
    "Answer",
    "DateAnswer",
    "DateEstimateAnswer",
    "DatetimeAnswer",
    "DurationAnswer",
    "DurationUnit",
    "EstimateAnswer",
    "ForecastAnswer",
    "ForecastStep",
    "ListAnswer",
    "NumberAnswer",
    "Span",
    "TextAnswer",
    "TextListAnswer",
    "TimeAnswer",
]

N = TypeVar("N", int, float)
"""Numeric value type of an answer: `int` sends `integer: true` to Clairic."""

V = TypeVar("V", int, float, dt.date)
"""Item type of a number or date list."""

DurationUnit = Literal["seconds", "minutes", "hours", "days", "weeks", "months", "years"]
"""Unit in which Clairic expresses a duration."""


class Span(NamedTuple):
    """Location of an extracted text in the input, as end-exclusive character offsets.

    `state[span.start:span.end]` returns the extracted text.

    Usage:
    >>> state = "Invoice INV-2291 from Northwind Supply"
    >>> span = Span(8, 16)
    >>> state[span.start : span.end]
    'INV-2291'
    """

    start: int
    end: int


class Answer(BaseModel):
    """Base class of every Clairic answer.

    Answers are immutable. Keys Clairic adds in the future are kept and readable through
    `model_extra`.
    """

    model_config = ConfigDict(frozen=True, extra="allow")


class _SingleValueAnswer(Answer):
    """Answer to a field with a single value: text, number, date, time, datetime, duration.

    Attributes:
        p_null: float
            Probability that the input does not contain or determine the value. `value` is
            `None` when it exceeds the field's `null_threshold` (default 0.5).
        confidence: float
            Probability that `guess` is the correct value, given that a value exists.
    """

    p_null: float
    confidence: float


class TextAnswer(_SingleValueAnswer):
    """Answer to a `text` field: an exact span of the input.

    `guess` and `span` describe the best candidate even when `value` is `None`, which lets you
    show a reviewer what Clairic considered before deciding the value was absent.

    Attributes:
        value: str | None
            The extracted text, or `None` when the input does not contain it.
        guess: str | None
            The best candidate text, reported even when `value` is `None`.
        span: Span | None
            Location of `guess` in the input.
    """

    type: Literal["text"] = "text"
    value: str | None
    guess: str | None = None
    span: Span | None = None


class NumberAnswer(_SingleValueAnswer, Generic[N]):
    """Answer to a `number` field, read from the input or computed from it.

    Parametrize with `int` for whole numbers (`NumberAnswer[int]` sends `integer: true`) or with
    `float`. Clairic rounds to the field's `decimals` and returns numbers without trailing
    zeros (`1080` for a two-decimal amount). Multi-step arithmetic is not yet reliable: prefer
    extracting the operands and computing in code.

    Attributes:
        value: N | None
            The number, or `None` when the input does not determine it.
        guess: N | None
            The best candidate number, reported even when `value` is `None`.
    """

    type: Literal["number"] = "number"
    value: N | None
    guess: N | None = None


class DateAnswer(_SingleValueAnswer):
    """Answer to a `date` field, read from the input or worked out from it.

    Pass `reference_date` when extracting to anchor dates written without a year and relative
    dates such as "net 30".

    Attributes:
        value: date | None
            The date, or `None` when the input does not determine it.
        guess: date | None
            The best candidate date, reported even when `value` is `None`.
    """

    type: Literal["date"] = "date"
    value: dt.date | None
    guess: dt.date | None = None


class TimeAnswer(_SingleValueAnswer):
    """Answer to a `time` field: a time of day, without time zone.

    Attributes:
        value: time | None
            The time, or `None` when the input does not determine it.
        guess: time | None
            The best candidate time, reported even when `value` is `None`.
    """

    type: Literal["time"] = "time"
    value: dt.time | None
    guess: dt.time | None = None


class DatetimeAnswer(_SingleValueAnswer):
    """Answer to a `datetime` field: a date and time of day, without time zone.

    Attributes:
        value: datetime | None
            The date and time, or `None` when the input does not determine them.
        guess: datetime | None
            The best candidate, reported even when `value` is `None`.
    """

    type: Literal["datetime"] = "datetime"
    value: dt.datetime | None
    guess: dt.datetime | None = None


class DurationAnswer(_SingleValueAnswer, Generic[N]):
    """Answer to a `duration` field: a length of time expressed in `unit`.

    Parametrize with `int` for whole units (`DurationAnswer[int]` sends `integer: true`) or with
    `float`. Choose the unit with the `Duration` spec; it defaults to seconds.

    Attributes:
        value: N | None
            The duration in `unit`, or `None` when the input does not determine it.
        guess: N | None
            The best candidate duration, reported even when `value` is `None`.
        unit: DurationUnit
            The unit of `value` and `guess`.
    """

    type: Literal["duration"] = "duration"
    value: N | None
    guess: N | None = None
    unit: DurationUnit


class TextListAnswer(Answer):
    """Answer to a `list` field of text items: every matching span of the input, in order.

    An empty list means nothing in the input matches.

    Attributes:
        value: list[str]
            The extracted texts, in input order.
        spans: list[Span]
            Location of each item of `value` in the input.
        confidence: float
            Confidence in the list as a whole.
    """

    type: Literal["list"] = "list"
    value: list[str]
    spans: list[Span]
    confidence: float


class ListAnswer(Answer, Generic[V]):
    """Answer to a `list` field of numbers or dates, in input order.

    Parametrize with `int`, `float` or `date`. For a list of text, use `TextListAnswer`. An
    empty list means nothing in the input matches.

    Attributes:
        value: list[V]
            The extracted items, in input order.
        confidences: list[float]
            Confidence in each item of `value`.
        confidence: float
            Confidence in the list as a whole.
    """

    type: Literal["list"] = "list"
    value: list[V]
    confidences: list[float]
    confidence: float


class EstimateAnswer(Answer, Generic[N]):
    """Answer to a numeric `estimate` field: a distribution over the `[min, max]` range.

    An estimate predicts a value the input does not state, such as a likely sale price, from the
    evidence the input contains. The 80% interval from `p10` to `p90` is calibrated on
    Cloudflare's measurements, which does not guarantee that a given outcome falls inside it.
    Intervals can be too narrow on unfamiliar data.

    Attributes:
        value: N | None
            Point estimate: the mean rounded to the field's `step` grid.
        mean: float
            Mean of the distribution.
        median: N
            50th percentile.
        p10: N
            10th percentile, lower bound of the 80% interval.
        p90: N
            90th percentile, upper bound of the 80% interval.
        p_below: float
            Probability mass below `min`.
        p_above: float
            Probability mass above `max`.
        quantiles: list[N] | None
            Percentiles 1 to 99 (`quantiles[9] == p10`), when requested with
            `include_quantiles`.
    """

    type: Literal["estimate"] = "estimate"
    value: N | None
    mean: float
    median: N
    p10: N
    p90: N
    p_below: float
    p_above: float
    quantiles: list[N] | None = None


class DateEstimateAnswer(Answer):
    """Answer to an `estimate` field with date bounds: a distribution over dates.

    With a `"month"` or `"year"` step, every date is the first day of its period.

    Attributes:
        value: date | None
            Point estimate: the mean date rounded to the field's `step` grid.
        mean: date
            Mean of the distribution.
        median: date
            50th percentile.
        p10: date
            10th percentile, lower bound of the 80% interval.
        p90: date
            90th percentile, upper bound of the 80% interval.
        quantiles: list[date] | None
            Percentiles 1 to 99, when requested with `include_quantiles`.
    """

    type: Literal["estimate"] = "estimate"
    value: dt.date | None
    mean: dt.date
    median: dt.date
    p10: dt.date
    p90: dt.date
    quantiles: list[dt.date] | None = None


class ForecastStep(BaseModel):
    """Estimate for one future step of a forecast series.

    Attributes:
        value: float
            Point forecast for the step.
        mean: float
            Mean of the step's distribution.
        median: float
            50th percentile.
        p10: float
            10th percentile, lower bound of the 80% interval.
        p90: float
            90th percentile, upper bound of the 80% interval.
        p_below: float
            Probability mass below `min`.
        p_above: float
            Probability mass above `max`.
        quantiles: list[float] | None
            Percentiles 1 to 99, when requested with `include_quantiles`.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    value: float
    mean: float
    median: float
    p10: float
    p90: float
    p_below: float
    p_above: float
    quantiles: list[float] | None = None


class ForecastAnswer(Answer):
    """Answer to a `forecast` field: one estimate per future step of a series.

    Clairic reads the history as plain text in the input (a CSV export, a pasted table, rows
    mixed with notes) and forecasts `horizon` steps ahead within `[min, max]`. It learns patterns
    from the series only, so events the series does not show, such as holidays, are missed.
    Forecasting is basic and does not replace a dedicated time-series model.

    The parallel lists hold one entry per step. `steps` holds the same per-step figures together
    with the mean and tail probabilities.

    Attributes:
        value: list[float]
            Point forecast for each step.
        median: list[float]
            50th percentile for each step.
        p10: list[float]
            10th percentile for each step.
        p90: list[float]
            90th percentile for each step.
        steps: list[ForecastStep]
            Full estimate for each step.
    """

    type: Literal["forecast"] = "forecast"
    value: list[float]
    median: list[float]
    p10: list[float]
    p90: list[float]
    steps: list[ForecastStep]
