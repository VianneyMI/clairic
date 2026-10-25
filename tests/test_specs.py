"""Spec payloads and constructor rules.

Every rejected value below was rejected by the live API on 2026-10-25; the recorded response is
named in each test (tests/fixtures/responses/err_*.json).
"""

import datetime as dt
import math

import pytest

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

# Keys the live API accepts per field type, besides `type` and `instructions`, as listed in its
# error messages (err_unknown_field_key and the keys_* probes).
ACCEPTED_KEYS = {
    "text": {"unit", "null_threshold"},
    "number": {"unit", "null_threshold", "integer", "decimals"},
    "date": {"unit", "null_threshold"},
    "time": {"unit", "null_threshold"},
    "datetime": {"unit", "null_threshold"},
    "duration": {"unit", "null_threshold", "integer", "decimals"},
    "list": {"unit", "items", "integer", "decimals"},
    "estimate": {"unit", "min", "max", "scale", "step"},
    "forecast": {"unit", "min", "max", "scale", "step", "horizon", "interval"},
}

FULLY_SET: list[Spec] = [
    Text(unit="ref", null_threshold=0.9),
    Number(unit="USD", null_threshold=0.9, decimals=2),
    Date(null_threshold=0.9),
    Time(null_threshold=0.9),
    Datetime(null_threshold=0.9),
    Duration(unit="days", null_threshold=0.9, decimals=1),
    List(unit="USD", decimals=2),
    Estimate(min=1, max=10, step=1, scale="log", unit="USD"),
    Forecast(min=1, max=10, horizon=3, interval="day", step=1, scale="log", unit="visitors"),
]


@pytest.mark.parametrize("spec", FULLY_SET, ids=lambda spec: spec.field_type)
def test_payload_only_uses_keys_the_api_accepts(spec: Spec) -> None:
    """Should send only keys the Clairic API accepts for the spec's field type."""
    assert set(spec.to_payload()) <= ACCEPTED_KEYS[spec.field_type]


def test_payload_leaves_out_unset_options() -> None:
    """Should send no key for an option left unset."""
    assert Text().to_payload() == {}
    assert Number(decimals=0).to_payload() == {"decimals": 0}


def test_duration_unit_defaults_to_seconds() -> None:
    """Should always send a duration unit, defaulting to seconds as the API does."""
    assert Duration().to_payload() == {"unit": "seconds"}


def test_date_bounds_are_sent_as_iso_dates() -> None:
    """Should serialize date bounds of an estimate as ISO dates."""
    spec = Estimate(min=dt.date(2026, 1, 1), max=dt.date(2027, 1, 1), step="month")

    assert spec.to_payload() == {"min": "2026-01-01", "max": "2027-01-01", "step": "month"}


@pytest.mark.parametrize("null_threshold", [0, -0.1, 1.5])
def test_null_threshold_outside_zero_one_is_rejected(null_threshold: float) -> None:
    """Should reject a null_threshold outside (0, 1] (err_null_threshold_zero)."""
    with pytest.raises(ValueError, match="null_threshold"):
        Text(null_threshold=null_threshold)


@pytest.mark.parametrize("decimals", [-1, 7])
def test_decimals_outside_zero_six_are_rejected(decimals: int) -> None:
    """Should reject decimals outside 0 to 6 (err_decimals_7)."""
    with pytest.raises(ValueError, match="decimals"):
        Number(decimals=decimals)


@pytest.mark.parametrize("horizon", [0, 65])
def test_horizon_outside_one_sixty_four_is_rejected(horizon: int) -> None:
    """Should reject a forecast horizon outside 1 to 64 (err_horizon_65)."""
    with pytest.raises(ValueError, match="horizon"):
        Forecast(min=0, max=10, horizon=horizon)


def test_unknown_duration_unit_is_rejected() -> None:
    """Should reject a duration unit Clairic does not know (err_bad_duration_unit)."""
    with pytest.raises(ValueError, match="unit"):
        Duration(unit="fortnights")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("min", "max"), [(10, 5), (5, 5), (dt.date(2027, 1, 1), dt.date(2026, 1, 1))]
)
def test_min_not_below_max_is_rejected(min: float | dt.date, max: float | dt.date) -> None:
    """Should reject bounds where min is not lower than max (err_estimate_min_ge_max)."""
    with pytest.raises(ValueError, match="lower than max"):
        Estimate(min=min, max=max)


def test_infinite_bounds_are_rejected() -> None:
    """Should reject infinite bounds, which the API refuses as not finite."""
    with pytest.raises(ValueError, match="finite"):
        Estimate(min=0, max=math.inf)


def test_mixed_number_and_date_bounds_are_rejected() -> None:
    """Should reject bounds mixing a number and a date."""
    with pytest.raises(ValueError, match="both"):
        Estimate(min=0, max=dt.date(2026, 1, 1))


@pytest.mark.parametrize("min", [0, -5])
def test_log_scale_needs_positive_min(min: float) -> None:
    """Should reject a log scale whose min is not positive (forecast probe with min 0)."""
    with pytest.raises(ValueError, match="log"):
        Forecast(min=min, max=10, horizon=1, scale="log")


@pytest.mark.parametrize("step", [0, -1])
def test_non_positive_step_is_rejected(step: float) -> None:
    """Should reject a step that is not positive (err_bad_step)."""
    with pytest.raises(ValueError, match="positive"):
        Estimate(min=0, max=10, step=step)


def test_unknown_calendar_step_is_rejected() -> None:
    """Should reject a calendar step other than month or year (err_bad_step)."""
    with pytest.raises(ValueError, match="step"):
        Estimate(min=dt.date(2026, 1, 1), max=dt.date(2027, 1, 1), step="week")  # type: ignore[arg-type]


def test_calendar_step_needs_date_bounds() -> None:
    """Should reject a month or year step on number bounds."""
    with pytest.raises(ValueError, match="date bounds"):
        Estimate(min=0, max=10, step="month")


def test_specs_are_immutable() -> None:
    """Should refuse attribute assignment on a spec."""
    spec = Number(decimals=2)

    with pytest.raises(AttributeError):
        spec.decimals = 3  # type: ignore[misc]
