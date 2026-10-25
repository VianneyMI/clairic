"""Field specs: the options of a Clairic field, attached to an answer type with `Annotated`.

A spec sets the options Clairic accepts for one field type. The answer type of the annotation
chooses the field type, and `Field(description=...)` gives the field its instructions:

```python
class Invoice(BaseModel):
    total: Annotated[NumberAnswer[float], Number(decimals=2, unit="USD")] = Field(
        description="Amount due including shipping"
    )
```

A field without a spec uses Clairic's defaults. Estimates and forecasts always need one, since
their bounds are mandatory. Constructors reject options the Clairic API rejects, so a mistake
surfaces where the model is declared instead of in an API error.

Source: https://developers.cloudflare.com/workers-ai/models/clairic/
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math
from typing import Any, ClassVar, Literal, get_args

from clairic.answers import DurationUnit

__all__ = [
    "Date",
    "Datetime",
    "Duration",
    "Estimate",
    "Forecast",
    "Interval",
    "List",
    "Number",
    "Scale",
    "Spec",
    "Text",
    "Time",
]

Scale = Literal["linear", "log"]
"""Grid on which estimates and forecasts spread their distribution."""

Interval = Literal["step", "minute", "hour", "day", "week", "month", "quarter", "year"]
"""Spacing between the steps of a forecast."""

CalendarStep = Literal["month", "year"]
"""Step for estimates with date bounds that snaps dates to the first day of a month or year."""


@dataclasses.dataclass(frozen=True, kw_only=True)
class Spec:
    """Base class of field specs.

    Attributes:
        field_type: ClassVar[str]
            Clairic field type the spec configures.
    """

    field_type: ClassVar[str]

    def to_payload(self) -> dict[str, Any]:
        """Return the options this spec sends to Clairic, leaving out the unset ones.

        Usage:
        >>> Number(decimals=2, unit="USD").to_payload()
        {'unit': 'USD', 'decimals': 2}
        """
        payload: dict[str, Any] = {}
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if value is None:
                continue
            payload[field.name] = value.isoformat() if isinstance(value, dt.date) else value
        return payload


def _check_null_threshold(null_threshold: float | None) -> None:
    if null_threshold is not None and not 0 < null_threshold <= 1:
        raise ValueError(f"null_threshold must be in (0, 1], got {null_threshold}")


def _check_decimals(decimals: int | None) -> None:
    if decimals is not None and not 0 <= decimals <= 6:
        raise ValueError(f"decimals must be between 0 and 6, got {decimals}")


def _check_choice(name: str, value: str | None, choices: Any) -> None:
    allowed: tuple[str, ...] = get_args(choices)
    if value is not None and value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}, got {value!r}")


def _check_bounds(
    min: float | dt.date, max: float | dt.date, step: float | str | None, scale: str | None
) -> None:
    """Check the bounds, step and scale of an estimate or forecast as the Clairic API does."""
    if isinstance(min, dt.date) and isinstance(max, dt.date):
        if not min < max:
            raise ValueError(f"min must be lower than max, got {min} and {max}")
    elif isinstance(min, (int, float)) and isinstance(max, (int, float)):
        if isinstance(min, bool) or isinstance(max, bool):
            raise ValueError(f"min and max must be numbers or dates, got {min!r} and {max!r}")
        if not (math.isfinite(min) and math.isfinite(max)):
            raise ValueError(f"min and max must be finite, got {min} and {max}")
        if not min < max:
            raise ValueError(f"min must be lower than max, got {min} and {max}")
        if scale == "log" and min <= 0:
            raise ValueError(f"scale 'log' needs min > 0, got {min}")
    else:
        raise ValueError(f"min and max must both be numbers or both be dates, got {min!r}, {max!r}")
    if isinstance(step, str):
        _check_choice("step", step, CalendarStep)
        if not isinstance(min, dt.date):
            raise ValueError(f"step {step!r} needs date bounds")
    elif step is not None and not step > 0:
        raise ValueError(f"step must be a positive number, got {step}")


@dataclasses.dataclass(frozen=True, kw_only=True)
class Text(Spec):
    """Options of a `text` field, answered by `TextAnswer`.

    Attributes:
        unit: str | None
            Unit label shown to the model.
        null_threshold: float | None
            Probability of absence above which the value is `None`, in (0, 1]. Defaults to 0.5.
            Raise it to keep low-certainty values, lower it to drop them.
    """

    field_type: ClassVar[str] = "text"

    unit: str | None = None
    null_threshold: float | None = None

    def __post_init__(self) -> None:
        _check_null_threshold(self.null_threshold)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Number(Spec):
    """Options of a `number` field, answered by `NumberAnswer`.

    Whole numbers are requested by annotating `NumberAnswer[int]`.

    Attributes:
        unit: str | None
            Unit label, such as `"USD"`.
        null_threshold: float | None
            Probability of absence above which the value is `None`, in (0, 1]. Defaults to 0.5.
        decimals: int | None
            Number of decimals to round to, between 0 and 6.
    """

    field_type: ClassVar[str] = "number"

    unit: str | None = None
    null_threshold: float | None = None
    decimals: int | None = None

    def __post_init__(self) -> None:
        _check_null_threshold(self.null_threshold)
        _check_decimals(self.decimals)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Date(Spec):
    """Options of a `date` field, answered by `DateAnswer`.

    Attributes:
        null_threshold: float | None
            Probability of absence above which the value is `None`, in (0, 1]. Defaults to 0.5.
    """

    field_type: ClassVar[str] = "date"

    null_threshold: float | None = None

    def __post_init__(self) -> None:
        _check_null_threshold(self.null_threshold)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Time(Spec):
    """Options of a `time` field, answered by `TimeAnswer`.

    Attributes:
        null_threshold: float | None
            Probability of absence above which the value is `None`, in (0, 1]. Defaults to 0.5.
    """

    field_type: ClassVar[str] = "time"

    null_threshold: float | None = None

    def __post_init__(self) -> None:
        _check_null_threshold(self.null_threshold)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Datetime(Spec):
    """Options of a `datetime` field, answered by `DatetimeAnswer`.

    Attributes:
        null_threshold: float | None
            Probability of absence above which the value is `None`, in (0, 1]. Defaults to 0.5.
    """

    field_type: ClassVar[str] = "datetime"

    null_threshold: float | None = None

    def __post_init__(self) -> None:
        _check_null_threshold(self.null_threshold)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Duration(Spec):
    """Options of a `duration` field, answered by `DurationAnswer`.

    Whole units are requested by annotating `DurationAnswer[int]`.

    Attributes:
        unit: DurationUnit
            Unit of the answer. Defaults to seconds.
        null_threshold: float | None
            Probability of absence above which the value is `None`, in (0, 1]. Defaults to 0.5.
        decimals: int | None
            Number of decimals to round to, between 0 and 6.
    """

    field_type: ClassVar[str] = "duration"

    unit: DurationUnit = "seconds"
    null_threshold: float | None = None
    decimals: int | None = None

    def __post_init__(self) -> None:
        _check_choice("unit", self.unit, DurationUnit)
        _check_null_threshold(self.null_threshold)
        _check_decimals(self.decimals)


@dataclasses.dataclass(frozen=True, kw_only=True)
class List(Spec):
    """Options of a `list` field, answered by `TextListAnswer` or `ListAnswer`.

    The item type comes from the annotation: `TextListAnswer` for text, `ListAnswer[int]`,
    `ListAnswer[float]` or `ListAnswer[date]` for numbers and dates.

    Attributes:
        unit: str | None
            Unit label of the items.
        decimals: int | None
            Number of decimals to round number items to, between 0 and 6.
    """

    field_type: ClassVar[str] = "list"

    unit: str | None = None
    decimals: int | None = None

    def __post_init__(self) -> None:
        _check_decimals(self.decimals)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Estimate(Spec):
    """Options of an `estimate` field, answered by `EstimateAnswer` or `DateEstimateAnswer`.

    Clairic spreads a distribution over `[min, max]` on a grid of `step`. Use number bounds with
    `EstimateAnswer` and date bounds with `DateEstimateAnswer`. Estimates need evidence in the
    input: comparable sales for a price, payment terms for a payment date.

    Attributes:
        min: float | date
            Lower bound of the distribution.
        max: float | date
            Upper bound of the distribution.
        step: float | CalendarStep | None
            Grid spacing: a positive number (days for date bounds), or `"month"` or `"year"`
            for date bounds.
        scale: Scale | None
            `"linear"` (default) or `"log"`. A log scale suits quantities spanning orders of
            magnitude, such as prices, and needs `min > 0`.
        unit: str | None
            Unit label, such as `"USD"`.
    """

    field_type: ClassVar[str] = "estimate"

    min: float | dt.date
    max: float | dt.date
    step: float | CalendarStep | None = None
    scale: Scale | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        _check_choice("scale", self.scale, Scale)
        _check_bounds(self.min, self.max, self.step, self.scale)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Forecast(Spec):
    """Options of a `forecast` field, answered by `ForecastAnswer`.

    Clairic forecasts `horizon` future steps of the series found in the input, each as a
    distribution over `[min, max]`.

    Attributes:
        min: float
            Lower bound of every step.
        max: float
            Upper bound of every step.
        horizon: int
            Number of steps to forecast, between 1 and 64.
        interval: Interval | None
            Spacing between steps, such as `"day"`.
        step: float | None
            Grid spacing of each step's distribution, a positive number.
        scale: Scale | None
            `"linear"` (default) or `"log"`, which needs `min > 0`.
        unit: str | None
            Unit label of the series.
    """

    field_type: ClassVar[str] = "forecast"

    min: float
    max: float
    horizon: int
    interval: Interval | None = None
    step: float | None = None
    scale: Scale | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.horizon <= 64:
            raise ValueError(f"horizon must be between 1 and 64, got {self.horizon}")
        _check_choice("interval", self.interval, Interval)
        _check_choice("scale", self.scale, Scale)
        _check_bounds(self.min, self.max, self.step, self.scale)
