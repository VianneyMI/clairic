"""Extractions against the real Cloudflare API. Run with `uv run pytest -m live`."""

import datetime as dt
from typing import Annotated

import pytest
from pydantic import BaseModel, Field

from clairic import (
    AsyncClairic,
    AuthenticationError,
    Clairic,
    DateAnswer,
    DateEstimateAnswer,
    DatetimeAnswer,
    Duration,
    DurationAnswer,
    Estimate,
    EstimateAnswer,
    Forecast,
    ForecastAnswer,
    ListAnswer,
    Number,
    NumberAnswer,
    TextAnswer,
    TextListAnswer,
    TimeAnswer,
)

pytestmark = pytest.mark.live

EMAIL = (
    "Sent: Tuesday, March 3, 2026 9:14 AM\n"
    "Hi, my order #A-55120 was delivered on Feb 20 at 4:30 PM. I paid $129.99 plus 8% tax. "
    "The lid is cracked and one hinge is bent. The courier left it outside for about 3 hours. "
    "Our meeting is booked for 2026-03-05T14:00:00. Order quantities: 2 chairs, 1 table. "
    "Other deliveries arrived on 2026-01-12 and 2026-02-02."
)


class Claim(BaseModel):
    order_id: TextAnswer = Field(description="Order number")
    amount_paid: Annotated[NumberAnswer[float], Number(decimals=2, unit="USD")] = Field(
        description="Total paid including tax"
    )
    delivery_date: DateAnswer = Field(description="Date the order was delivered")
    delivery_time: TimeAnswer = Field(description="Time of day the order was delivered")
    meeting: DatetimeAnswer = Field(description="When the meeting is booked")
    rain_exposure: Annotated[DurationAnswer[float], Duration(unit="hours")] = Field(
        description="How long the parcel sat outside"
    )
    damage: TextListAnswer = Field(description="Each kind of damage described")
    quantities: ListAnswer[int] = Field(description="Quantities of each product ordered")
    other_deliveries: ListAnswer[dt.date] = Field(description="Dates of other deliveries")
    tracking_number: TextAnswer = Field(description="Parcel tracking number")


class Claimed(BaseModel):
    order_id: str
    delivery_date: dt.date
    tracking_number: str | None


def test_every_single_value_and_list_type(clairic: Clairic) -> None:
    """Should extract every single-value and list type from a real response."""
    result = clairic.extract(EMAIL, Claim, reference_date=dt.date(2026, 3, 3))
    data = result.data

    assert data.order_id.value is not None
    assert "A-55120" in data.order_id.value
    assert data.amount_paid.value == pytest.approx(140.39, abs=0.01)
    assert data.delivery_date.value == dt.date(2026, 2, 20)
    assert data.delivery_time.value == dt.time(16, 30)
    assert data.meeting.value == dt.datetime(2026, 3, 5, 14, 0)
    assert data.rain_exposure.value == pytest.approx(3)
    assert data.damage.value
    assert data.quantities.value == [2, 1]
    assert data.other_deliveries.value == [dt.date(2026, 1, 12), dt.date(2026, 2, 2)]
    assert data.tracking_number.value is None
    assert result.request_id is not None
    assert result.values_as(Claimed).tracking_number is None


class Pricing(BaseModel):
    price: Annotated[
        EstimateAnswer[int], Estimate(min=50_000, max=5_000_000, step=1000, scale="log")
    ] = Field(description="Likely sale price of the subject")
    sale_month: Annotated[
        DateEstimateAnswer,
        Estimate(min=dt.date(2026, 4, 1), max=dt.date(2027, 4, 1), step="month"),
    ] = Field(description="Month the subject sells")


def test_numeric_and_date_estimates(clairic: Clairic) -> None:
    """Should return distributions ordered from p10 to p90."""
    homes = (
        "Comparable sales, same street, 2025: 12 Oak St, 1,650 sqft, sold $402,000. "
        "18 Oak St, 1,720 sqft, sold $431,000. Subject: 21 Oak St, 1,700 sqft. Listed 2026-04-01."
    )

    data = clairic.extract(homes, Pricing).data

    assert data.price.p10 <= data.price.median <= data.price.p90
    assert data.sale_month.p10 <= data.sale_month.p90
    assert data.sale_month.median.day == 1


class Visitors(BaseModel):
    visitors: Annotated[ForecastAnswer, Forecast(min=0, max=5000, horizon=3, interval="day")] = (
        Field(description="Visitors on each of the next days")
    )


def test_forecast(clairic: Clairic) -> None:
    """Should return one forecast step per horizon step."""
    series = "date,visitors\n" + "\n".join(f"2026-09-{d:02d},{1000 + 10 * d}" for d in range(1, 29))

    forecast = clairic.extract(series, Visitors).data.visitors

    assert len(forecast.value) == len(forecast.steps) == 3


def test_invalid_token_raises_authentication_error() -> None:
    """Should raise AuthenticationError for a token Cloudflare rejects."""
    client = Clairic(account_id="0123456789abcdef0123456789abcdef", api_token="invalid")
    with client, pytest.raises(AuthenticationError):
        client.extract("Total $10.", Visitors)


@pytest.mark.anyio
async def test_async_client(async_clairic: AsyncClairic) -> None:
    """Should extract with the async client."""
    async with async_clairic as client:
        result = await client.extract(EMAIL, Claim, reference_date=dt.date(2026, 3, 3))

    assert result.data.delivery_date.value == dt.date(2026, 2, 20)
