import datetime as dt

import pytest
from pydantic import BaseModel, ValidationError
from recorded import answers, state

from clairic.answers import (
    DateAnswer,
    DateEstimateAnswer,
    DatetimeAnswer,
    DurationAnswer,
    EstimateAnswer,
    ForecastAnswer,
    ListAnswer,
    NumberAnswer,
    Span,
    TextAnswer,
    TextListAnswer,
    TimeAnswer,
)


class TypesPresent(BaseModel):
    order_id: TextAnswer
    amount_with_tax: NumberAnswer[float]
    item_count: NumberAnswer[int]
    delivery_date: DateAnswer
    delivery_time: TimeAnswer
    meeting: DatetimeAnswer
    rain_exposure: DurationAnswer[float]
    days_since_delivery: DurationAnswer[int]
    damage: TextListAnswer
    quantities: ListAnswer[int]
    other_deliveries: ListAnswer[dt.date]


class TypesAbsent(BaseModel):
    order_id: TextAnswer
    amount: NumberAnswer[float]
    delivery_date: DateAnswer
    delivery_time: TimeAnswer
    meeting: DatetimeAnswer
    wait: DurationAnswer[float]
    damage: TextListAnswer
    quantities: ListAnswer[float]
    dates: ListAnswer[dt.date]


class Estimates(BaseModel):
    price_log: EstimateAnswer[int]
    price_linear: EstimateAnswer[int]
    days_on_market: EstimateAnswer[int]
    sale_date: DateEstimateAnswer
    sale_month: DateEstimateAnswer
    unknowable: EstimateAnswer[int]


class Forecasts(BaseModel):
    next_day: ForecastAnswer
    next_days: ForecastAnswer


def test_single_value_answers_parse_the_recorded_values() -> None:
    """Should parse every single-value and list type from a recorded response."""
    parsed = TypesPresent.model_validate(answers("types_present"))

    assert parsed.order_id.value == "#A-55120"
    assert parsed.amount_with_tax.value == pytest.approx(140.39)
    assert parsed.item_count.value == 7
    assert parsed.delivery_date.value == dt.date(2026, 2, 20)
    assert parsed.delivery_time.value == dt.time(16, 30)
    assert parsed.meeting.value == dt.datetime(2026, 3, 5, 14, 0)
    assert parsed.rain_exposure.value == 3
    assert parsed.rain_exposure.unit == "hours"
    assert parsed.days_since_delivery.value == 11
    assert parsed.damage.value == ["lid", "one hinge is bent"]
    assert parsed.quantities.value == [2, 1, 4]
    assert len(parsed.quantities.confidences) == 3
    assert parsed.other_deliveries.value == [dt.date(2026, 1, 12), dt.date(2026, 2, 2)]


def test_spans_slice_the_input_to_the_extracted_text() -> None:
    """Should locate text answers and text list items in the input with end-exclusive spans."""
    text = state("types_present")
    parsed = TypesPresent.model_validate(answers("types_present"))

    span = parsed.order_id.span
    assert span is not None
    assert span == Span(118, 126)
    assert text[span.start : span.end] == parsed.order_id.value
    assert [text[s.start : s.end] for s in parsed.damage.spans] == parsed.damage.value


def test_absent_values_are_none_with_a_guess() -> None:
    """Should return None values with a guess and a high p_null when the input lacks them."""
    parsed = TypesAbsent.model_validate(answers("types_absent"))

    for answer in (
        parsed.order_id,
        parsed.amount,
        parsed.delivery_date,
        parsed.delivery_time,
        parsed.meeting,
        parsed.wait,
    ):
        assert answer.value is None
        assert answer.guess is not None
        assert answer.p_null > 0.99
    assert parsed.damage.value == []
    assert parsed.damage.spans == []
    assert parsed.quantities.value == []
    assert parsed.dates.value == []


def test_estimates_parse_numeric_and_date_distributions() -> None:
    """Should parse numeric and date estimates, with 99 quantiles when they were requested."""
    parsed = Estimates.model_validate(answers("estimate_quantiles"))

    price = parsed.price_log
    assert price.value == 442000
    assert price.quantiles is not None
    assert len(price.quantiles) == 99
    assert (price.quantiles[9], price.quantiles[49], price.quantiles[89]) == (
        price.p10,
        price.median,
        price.p90,
    )
    assert parsed.sale_date.value == dt.date(2026, 6, 1)
    assert parsed.sale_month.p90 == dt.date(2026, 8, 1)


def test_estimate_value_is_the_mean_rounded_to_the_step_grid() -> None:
    """Should match the documented point-estimate semantics on recorded estimates."""
    parsed = Estimates.model_validate(answers("estimate_quantiles"))

    assert parsed.price_linear.value == round(parsed.price_linear.mean, -3)
    assert parsed.days_on_market.value == round(parsed.days_on_market.mean)
    assert parsed.unknowable.value == round(parsed.unknowable.mean)


def test_estimate_without_quantiles_leaves_them_unset() -> None:
    """Should set quantiles to None when the request did not ask for them."""
    parsed = EstimateAnswer[int].model_validate(answers("estimate_no_quantiles")["price_log"])

    assert parsed.quantiles is None


def test_forecasts_expose_parallel_lists_and_steps() -> None:
    """Should parse both the per-step lists and the steps of a forecast."""
    parsed = Forecasts.model_validate(answers("forecast_ok"))

    forecast = parsed.next_days
    assert len(forecast.value) == len(forecast.steps) == 4
    assert [step.p90 for step in forecast.steps] == forecast.p90
    assert forecast.steps[0].quantiles is not None
    assert len(forecast.steps[0].quantiles) == 99


def test_unknown_keys_are_kept_in_model_extra() -> None:
    """Should keep keys Clairic adds later instead of rejecting the answer."""
    raw = {**answers("invoice")["invoice_number"], "explanation": "new upstream key"}

    parsed = TextAnswer.model_validate(raw)

    assert parsed.model_extra == {"explanation": "new upstream key"}


def test_answers_are_immutable() -> None:
    """Should refuse attribute assignment on an answer."""
    parsed = TextAnswer.model_validate(answers("invoice")["invoice_number"])

    with pytest.raises(ValidationError):
        parsed.value = "edited"  # type: ignore[misc]


def test_integer_answer_rejects_a_fractional_number() -> None:
    """Should reject a fractional value for a field declared with an int parameter."""
    raw = answers("types_present")["amount_with_tax"]

    with pytest.raises(ValidationError):
        NumberAnswer[int].model_validate(raw)
