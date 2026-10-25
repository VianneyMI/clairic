# clairic

**Unofficial** typed Python SDK for [Cloudflare Clairic](https://developers.cloudflare.com/workers-ai/models/clairic/), the Workers AI extraction model. This project is not affiliated with or endorsed by Cloudflare.

Clairic reads a text and returns typed values for the fields you name: extracted, computed, estimated or forecast, each with a confidence score, a probability of absence, or a percentile range. `clairic` lets you declare those fields as a Pydantic model and get the answers back as typed Pydantic objects.

```python
from typing import Annotated

from pydantic import BaseModel, Field

from clairic import Clairic, DateAnswer, Estimate, EstimateAnswer, Number, NumberAnswer, TextAnswer


class InvoiceExtraction(BaseModel):
    invoice_number: TextAnswer
    due_date: DateAnswer = Field(description="Issue date plus the net payment days")
    total: Annotated[NumberAnswer[float], Number(decimals=2, unit="USD")] = Field(
        description="Amount due including shipping"
    )
    po_number: TextAnswer = Field(description="Purchase order number")
    days_to_pay: Annotated[EstimateAnswer[int], Estimate(min=0, max=120, step=1)] = Field(
        description="Days after issue until this invoice is paid"
    )


with Clairic() as clairic:
    result = clairic.extract(
        "Invoice INV-2291 from Northwind Supply, issued 2026-09-02, net 30. "
        "4 pallets at $250.00 each, shipping $80.00.",
        InvoiceExtraction,
    )

result.data.total.value  # 1080.0
result.data.total.confidence  # 0.99995
result.data.po_number.value  # None: the invoice has no PO number
result.data.days_to_pay.p90  # 37
```

## Install

```sh
pip install clairic
```

Python 3.10 or later. Dependencies: `httpx` and `pydantic` 2.

## Credentials

The client reads `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`, or takes them as arguments:

```python
clairic = Clairic(account_id="...", api_token="...")
```

Create the token in the Cloudflare dashboard with access to Workers AI.

## Declaring fields

Each field of the extraction model is an answer type. The answer type sets the Clairic field type; an `Annotated` spec sets its options; `Field(description=...)` gives Clairic the instructions; a Pydantic `alias` sets the field name sent to Clairic.

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

Invalid declarations fail before any request: a non-answer annotation, a missing or mismatched spec, or an option Clairic rejects (such as `decimals=7` or `scale="log"` with `min=0`) raises `ModelDefinitionError` or `ValueError` naming the problem.

Set `reference_date` whenever a field depends on today's date or on dates written without a year:

```python
clairic.extract(text, InvoiceExtraction, reference_date=date(2026, 9, 2))
```

## Reading answers

Every answer holds a `value` and the metadata Clairic attaches to it. Your editor completes the attributes, and a type checker knows their types.

- **Single values** (`text`, `number`, `date`, `time`, `datetime`, `duration`): `value`, `guess`, `confidence`, `p_null`. `value` is `None` when `p_null` exceeds the field's `null_threshold` (0.5 by default); `guess` still shows the best candidate.
- **Text**: `span`, end-exclusive offsets into the input: `text[span.start:span.end]`. Text lists carry `spans`.
- **Number and date lists**: `confidences`, one per item.
- **Estimates**: `value` (the mean rounded to the `step` grid), `mean`, `median`, `p10`, `p90`, and for number bounds `p_below` and `p_above`, the probability mass outside `[min, max]`.
- **Forecasts**: per-step lists `value`, `median`, `p10`, `p90`, and `steps` with the full estimate of each step.

The p10 to p90 range is an 80% interval. Cloudflare measures its calibration but does not guarantee it, and intervals can be too narrow on unfamiliar data. Use `confidence`, `p_null` and the interval to decide which answers to act on and which to review.

## Plain values

`values_as` copies each answer value into the same-named field of a plain Pydantic model, ready for the rest of your program:

```python
class Invoice(BaseModel):
    invoice_number: str
    total: float
    po_number: str | None
    days_to_pay: int


invoice = result.values_as(Invoice)
```

Pydantic validates the values, so a `None` landing in a field that does not accept `None` raises `ValidationError`.

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
| `ModelDefinitionError` | The extraction model cannot be sent to Clairic. Raised before any request. |
| `ClairicConfigurationError` | The account id or token is missing. |
| `AuthenticationError` | HTTP 401: invalid token or unknown account. |
| `InvalidRequestError` | HTTP 400 or 422: Cloudflare rejected the request content. |
| `ContextWindowExceededError` | HTTP 413: the input exceeds the 65,536-token context window. |
| `APIError` | Any other error response, or answers that do not fit the model. Base class of the API errors. |
| `APIConnectionError`, `APITimeoutError` | Cloudflare could not be reached, or did not answer within the timeout (30 seconds by default). |

API errors carry `status_code`, the Cloudflare error `code`, `message` and `request_id`. When Clairic reports a truncated input, the client emits `ClairicTruncationWarning` and sets `result.truncated`.

## Cost

Clairic bills input tokens only ($0.10 per million at the time of writing). Fields that do not fit next to the input in one 8,192-token pass are split across parallel passes, and each pass reads the whole input, so `result.usage.input_tokens` counts the input once per pass.

## Development

```sh
uv sync
uv run ruff format --check && uv run ruff check && uv run pyright && uv run pytest
uv run pytest -m live                         # real API, needs credentials
uv run python scripts/check_schema_drift.py   # compare Cloudflare's schemas with the vendored ones
```

`examples/invoice.py` runs the invoice extraction end to end.

## License and attribution

MIT. Docstrings adapt text from the Cloudflare documentation, published under CC BY 4.0; see `NOTICE`.
