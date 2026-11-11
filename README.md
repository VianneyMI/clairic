# clairic

clairic is a typed Python SDK for [Clairic](https://developers.cloudflare.com/workers-ai/models/clairic/),
Cloudflare's Workers AI extraction model. Clairic reads a text and returns values for the fields you
name, whether extracted, computed, estimated or forecast. Each value comes with signals for
deciding what to automate: a confidence score, a probability of absence, a source span or a
percentile range. clairic turns your Pydantic model into the request and gives the answers back as
that model.

## Features

- Declare fields as a Pydantic model, with one answer type per field.
- Read each value with its confidence, probability of absence, span or percentiles one attribute
  away.
- Use all nine Clairic field types, from text spans to forecasts.
- Catch invalid declarations before any request.
- Export plain values to your own domain model with `values_as`.
- Read Cloudflare's documentation in your editor, through the docstrings.
- Use a sync or an async client, fully typed for pyright.

## Installation

```sh
pip install clairic
```

Python 3.10 or later. The client reads `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`, or takes
them as arguments with `Clairic(account_id="...", api_token="...")`. Create the token in the
Cloudflare dashboard with access to Workers AI.

## Usage

> The examples below extract the same invoice. Outputs come from a call to Clairic.

### Basic usage

```python
from typing import Annotated

from pydantic import BaseModel, Field

from clairic import Clairic, DateAnswer, Number, NumberAnswer, TextAnswer, TextListAnswer

INVOICE = (
    "Invoice INV-2291 from Northwind Supply, issued 2026-09-02, net 30. 4 pallets at $250.00 "
    "each, shipping $80.00. Contact: Dana Ruiz, Priya Shah."
)


# Declaring the fields to extract
class InvoiceExtraction(BaseModel):
    invoice_number: TextAnswer
    due_date: DateAnswer = Field(description="Issue date plus the net payment days")
    total: Annotated[NumberAnswer[float], Number(decimals=2, unit="USD")] = Field(
        description="Amount due including shipping"
    )
    contacts: TextListAnswer
    po_number: TextAnswer = Field(description="Purchase order number")


# Extracting
with Clairic() as clairic:
    result = clairic.extract(INVOICE, InvoiceExtraction)

invoice = result.data

invoice.invoice_number.value  # 'INV-2291'
invoice.due_date.value  # datetime.date(2026, 10, 2), computed from the issue date and net 30
invoice.total.value  # 1080.0, computed from the pallets and shipping
invoice.total.confidence  # 0.99995
invoice.contacts.value  # ['Dana Ruiz', 'Priya Shah']

invoice.po_number.value  # None
invoice.po_number.p_null  # 0.9999994, the probability that the PO number is absent
invoice.po_number.guess  # 'INV-2291', the best candidate
```

### Estimates

An estimate field asks Clairic for a number the text only hints at. Continuing from the previous
example:

```python
from clairic import Estimate, EstimateAnswer


# Adding an estimate to the extraction model
class InvoiceForecast(InvoiceExtraction):
    days_to_pay: Annotated[EstimateAnswer[int], Estimate(min=0, max=120, step=1)] = Field(
        description="Days after issue until this invoice is paid"
    )


with Clairic() as clairic:
    result = clairic.extract(INVOICE, InvoiceForecast)

days = result.data.days_to_pay

days.value  # 31, the mean rounded to the step
days.p10  # 24
days.p90  # 37
```

### Plain values

`values_as` copies each answer value into the same-named field of your own model, ready for the rest
of your program. Continuing from the previous example:

```python
import datetime as dt


class Invoice(BaseModel):
    invoice_number: str
    due_date: dt.date
    total: float
    contacts: list[str]
    po_number: str | None
    days_to_pay: int


result.values_as(Invoice)
# Invoice(invoice_number='INV-2291', due_date=datetime.date(2026, 10, 2), total=1080.0,
#         contacts=['Dana Ruiz', 'Priya Shah'], po_number=None, days_to_pay=31)
```

Pydantic validates the values on the way. A `None` landing in a field typed `str` raises
`ValidationError`, and `str | None` accepts it.

## Declaring fields

Each field of the extraction model has an answer type, which sets the Clairic field type. An
`Annotated` spec sets its options, `Field(description=...)` holds the instructions, and a Pydantic
`alias` sets the field name sent to Clairic.

| Answer type | Clairic type | Spec (options) |
|---|---|---|
| `TextAnswer` | `text`: a span of the input | `Text(unit, null_threshold)` |
| `NumberAnswer[float]`, `NumberAnswer[int]` | `number` (`int` requests whole numbers) | `Number(unit, null_threshold, decimals)` |
| `DateAnswer`, `TimeAnswer`, `DatetimeAnswer` | `date`, `time`, `datetime` | `Date(null_threshold)`, `Time(...)`, `Datetime(...)` |
| `DurationAnswer[float]`, `DurationAnswer[int]` | `duration` | `Duration(unit, null_threshold, decimals)`, unit defaults to seconds |
| `TextListAnswer` | `list` of text spans | `List(unit, decimals)` |
| `ListAnswer[int]`, `ListAnswer[float]`, `ListAnswer[date]` | `list` of numbers or dates | `List(unit, decimals)` |
| `EstimateAnswer[int]`, `EstimateAnswer[float]` | `estimate` with number bounds | `Estimate(min, max, step, scale, unit)`, required |
| `DateEstimateAnswer` | `estimate` with date bounds | `Estimate(min=date, max=date, step="month")`, required |
| `ForecastAnswer` | `forecast` of a series | `Forecast(min, max, horizon, interval, step, scale, unit)`, required |

Declarations are checked before any request. A field with a plain type, a missing or mismatched
spec, or an option Clairic rejects (such as `decimals=7`, or `scale="log"` with `min=0`) raises
`ModelDefinitionError` or `ValueError` with the problem named.

Fields that depend on today's date, or on dates written as day and month only, need a `reference_date`:

```python
clairic.extract(text, InvoiceExtraction, reference_date=date(2026, 9, 2))
```

## Reading answers

Every answer holds a `value` and the metadata Clairic attaches to it, all typed for your editor.

| Answers | Attributes |
|---|---|
| Single values (`text`, `number`, `date`, `time`, `datetime`, `duration`) | `value`, `guess`, `confidence`, `p_null` |
| Text | `span`, end-exclusive offsets into the input (`text[span.start:span.end]`). Text lists carry `spans` |
| Number and date lists | `confidences`, one per item |
| Estimates | `value` (the mean rounded to the `step` grid), `mean`, `median`, `p10`, `p90`. With number bounds, `p_below` and `p_above` hold the probability mass below `min` and above `max` |
| Forecasts | Per-step lists `value`, `median`, `p10`, `p90`, and `steps` with the full estimate of each step |

`value` turns to `None` when `p_null` exceeds the field's `null_threshold`, 0.5 by default, and
`guess` keeps the best candidate. On "can be reached at +33 6 12 34 56 78 or at
firstname.name@gmail.com", Clairic returned the phone number with a confidence of 1.0, and for the
email a `p_null` of 0.66 with the address in `guess`.

The p10 to p90 range is an 80% interval. Cloudflare publishes calibration measurements, and
intervals can come out too narrow on new kinds of data.

## Storing results

A `Result` serializes to JSON and back with its answers, token usage and request id:

```python
stored = result.model_dump_json()
result = Result[InvoiceExtraction].model_validate_json(stored)
```

## Async

```python
from clairic import AsyncClairic

async with AsyncClairic() as clairic:
    result = await clairic.extract(text, InvoiceExtraction)
```

## Errors

| Exception | When |
|---|---|
| `ModelDefinitionError` | The extraction model is invalid for Clairic. Raised before any request. |
| `ClairicConfigurationError` | The account id or token is missing. |
| `AuthenticationError` | HTTP 401: invalid token or unknown account. |
| `InvalidRequestError` | HTTP 400 or 422: Cloudflare rejected the request content. |
| `ContextWindowExceededError` | HTTP 413: the input exceeds the 65,536-token context window. |
| `APIError` | Any other error response, or answers outside the model's shape. Base class of the API errors. |
| `APIConnectionError`, `APITimeoutError` | Cloudflare was unreachable, or the timeout expired (30 seconds by default). |

API errors carry `status_code`, the Cloudflare error `code`, `message` and `request_id`. When
Clairic reports a truncated input, the client emits `ClairicTruncationWarning` and sets
`result.truncated`.

## Cost

Clairic bills input tokens, at $0.10 per million at the time of writing. It packs fields next to
the input in 8,192-token passes and runs extra passes in parallel when they overflow. Each pass
reads the whole input, and `result.usage.input_tokens` counts it once per pass. The full invoice
extraction above took 655 input tokens over 3 passes.

## Preview status

Clairic is a preview model. Cloudflare provides it as is and may withdraw it at any time. Field
options can change too, and a weekly CI job compares Cloudflare's published schemas with the ones
vendored here. The cause of `truncated: true` is under investigation in
[#15](https://github.com/VianneyMI/clairic/issues/15).

## Going further

- [examples/invoice.py](examples/invoice.py) runs the invoice extraction end to end.
- [Cloudflare's Clairic documentation](https://developers.cloudflare.com/workers-ai/models/clairic/)
  covers every field type and option.
- [python-jev](https://github.com/VianneyMI/python-jev) applies the same approach to TypeSafe's
  Jev, a decision model.

## Development

```sh
uv sync
uv run ruff format --check && uv run ruff check && uv run pyright && uv run pytest
uv run pytest -m live                         # real API, needs credentials
uv run python scripts/check_schema_drift.py   # compare Cloudflare's schemas with the vendored ones
```

## License and attribution

MIT. clairic is a community project, independent from Cloudflare. Docstrings adapt text from
Cloudflare's documentation, published under CC BY 4.0 (see `NOTICE`).
