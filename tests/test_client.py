import datetime as dt
import json
import warnings
from collections.abc import Callable
from typing import Annotated, Any

import httpx
import pytest
from pydantic import BaseModel, Field
from recorded import load

from clairic import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncClairic,
    AuthenticationError,
    Clairic,
    ClairicConfigurationError,
    ClairicTruncationWarning,
    ContextWindowExceededError,
    DateAnswer,
    Estimate,
    EstimateAnswer,
    InvalidRequestError,
    ModelDefinitionError,
    Number,
    NumberAnswer,
    TextAnswer,
    TextListAnswer,
)

ACCOUNT_ID = "0123456789abcdef0123456789abcdef"
TOKEN = "test-token"
URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/cloudflare/clairic"


class InvoiceExtraction(BaseModel):
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


Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    """Mock transport handler replaying a recorded response and keeping the requests."""

    def __init__(self, fixture: str, edit: Callable[[dict[str, Any]], None] | None = None):
        recording = load(fixture)
        self.status = recording["status"]
        self.headers = recording["headers"]
        self.body = recording["response"]
        if edit is not None:
            assert isinstance(self.body, dict)
            edit(self.body)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        content = self.body if isinstance(self.body, str) else json.dumps(self.body)
        return httpx.Response(self.status, headers=self.headers, content=content)


def _client(handler: Handler) -> Clairic:
    return Clairic(
        account_id=ACCOUNT_ID,
        api_token=TOKEN,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _async_client(handler: Handler) -> AsyncClairic:
    return AsyncClairic(
        account_id=ACCOUNT_ID,
        api_token=TOKEN,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


INVOICE_STATE = (
    "Invoice INV-2291 from Northwind Supply, issued 2026-09-02, net 30. 4 pallets at $250.00 "
    "each, shipping $80.00. Contact: Dana Ruiz, Priya Shah."
)


def test_extract_sends_the_documented_request() -> None:
    """Should post the model, state and compiled fields with bearer authentication."""
    recorder = Recorder("invoice")

    _client(recorder).extract(INVOICE_STATE, InvoiceExtraction, reference_date=dt.date(2026, 9, 2))

    (request,) = recorder.requests
    expected = load("invoice")["request"]
    assert isinstance(expected, dict)
    assert str(request.url) == URL
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["User-Agent"].startswith("clairic-python/")
    assert json.loads(request.content) == {**expected, "reference_date": "2026-09-02"}


def test_extract_returns_typed_answers_and_metadata() -> None:
    """Should return the answers in the model with usage and request id."""
    recorder = Recorder("model_full_name")

    class Total(BaseModel):
        total: NumberAnswer[float]

    result = _client(recorder).extract("Total $10.", Total)

    assert result.data.total.value == 10
    assert result.usage.input_tokens == 115
    assert result.truncated is False
    assert result.model == "clairic"
    assert result.request_id == "21d0233d-a285-4f04-969e-1f63c84d097d"


def test_datetime_reference_date_is_sent_as_a_date() -> None:
    """Should send only the date part of a datetime reference date."""
    recorder = Recorder("invoice")

    _client(recorder).extract(
        INVOICE_STATE, InvoiceExtraction, reference_date=dt.datetime(2026, 9, 2, 15, 30)
    )

    assert json.loads(recorder.requests[0].content)["reference_date"] == "2026-09-02"


@pytest.mark.parametrize(
    ("fixture", "error_type", "status_code", "code", "has_request_id"),
    [
        ("err_bad_token", AuthenticationError, 401, 10000, False),
        ("err_bad_account", AuthenticationError, 401, 10000, False),
        ("err_bad_type", InvalidRequestError, 400, 5006, True),
        ("err_list_no_items", InvalidRequestError, 422, 3030, True),
        ("err_malformed_json", InvalidRequestError, 400, 6003, False),
        ("trunc_70k", ContextWindowExceededError, 413, 5021, True),
    ],
)
def test_error_responses_raise_typed_errors(
    fixture: str,
    error_type: type[APIError],
    status_code: int,
    code: int,
    has_request_id: bool,
) -> None:
    """Should map each recorded Cloudflare error to its exception with code and request id."""
    recorder = Recorder(fixture)
    expected_message = recorder.body["errors"][0]["message"]  # type: ignore[index]

    with pytest.raises(error_type) as raised:
        _client(recorder).extract(INVOICE_STATE, InvoiceExtraction)

    error = raised.value
    assert error.status_code == status_code
    assert error.code == code
    assert error.message == expected_message
    assert (error.request_id is not None) is has_request_id


def test_unknown_error_status_raises_api_error() -> None:
    """Should raise the base APIError for statuses without a dedicated exception."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503, json={"success": False, "errors": [{"code": 7000, "message": "Unavailable"}]}
        )

    with pytest.raises(APIError) as raised:
        _client(handler).extract(INVOICE_STATE, InvoiceExtraction)

    assert type(raised.value) is APIError
    assert raised.value.code == 7000


def test_non_json_response_raises_api_error() -> None:
    """Should raise APIError carrying the body when the response is not JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad gateway</html>")

    with pytest.raises(APIError, match="Bad gateway"):
        _client(handler).extract(INVOICE_STATE, InvoiceExtraction)


def test_answers_that_do_not_fit_the_model_raise_api_error() -> None:
    """Should raise APIError naming the model when an answer does not validate."""

    class WholeTotal(BaseModel):
        amount_with_tax: NumberAnswer[int]

    with pytest.raises(APIError, match="WholeTotal"):
        _client(Recorder("types_present")).extract("Total $140.39", WholeTotal)


def test_truncated_result_emits_a_warning() -> None:
    """Should warn, pointing at the caller, when Clairic reports a truncated input."""

    def truncate(body: dict[str, Any]) -> None:
        body["result"]["truncated"] = True

    with pytest.warns(ClairicTruncationWarning) as caught:
        result = _client(Recorder("invoice", truncate)).extract(INVOICE_STATE, InvoiceExtraction)

    assert result.truncated is True
    assert caught[0].filename == __file__


def test_untruncated_result_emits_no_warning() -> None:
    """Should not warn on a complete result."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _client(Recorder("invoice")).extract(INVOICE_STATE, InvoiceExtraction)


def test_timeout_raises_api_timeout_error() -> None:
    """Should raise APITimeoutError when Cloudflare does not answer in time."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(APITimeoutError):
        _client(handler).extract(INVOICE_STATE, InvoiceExtraction)


def test_connection_failure_raises_api_connection_error() -> None:
    """Should raise APIConnectionError when Cloudflare cannot be reached."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(APIConnectionError):
        _client(handler).extract(INVOICE_STATE, InvoiceExtraction)


def test_invalid_model_fails_before_any_request() -> None:
    """Should raise ModelDefinitionError without sending a request."""
    recorder = Recorder("invoice")

    class Invalid(BaseModel):
        total: float

    with pytest.raises(ModelDefinitionError):
        _client(recorder).extract(INVOICE_STATE, Invalid)

    assert recorder.requests == []


def test_empty_state_fails_before_any_request() -> None:
    """Should reject an empty state without sending a request (err_empty_state)."""
    recorder = Recorder("err_empty_state")

    with pytest.raises(ValueError, match="state"):
        _client(recorder).extract("", InvoiceExtraction)

    assert recorder.requests == []


def test_credentials_fall_back_to_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should read the account id and token from the Cloudflare environment variables."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    recorder = Recorder("invoice")

    Clairic(http_client=httpx.Client(transport=httpx.MockTransport(recorder))).extract(
        INVOICE_STATE, InvoiceExtraction
    )

    assert str(recorder.requests[0].url) == URL
    assert recorder.requests[0].headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("missing", ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"])
def test_missing_credentials_raise_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """Should name the missing environment variable."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.delenv(missing)

    with pytest.raises(ClairicConfigurationError, match=missing):
        Clairic()


def test_repr_does_not_reveal_the_token() -> None:
    """Should leave the API token out of the client representation."""
    client = Clairic(account_id=ACCOUNT_ID, api_token=TOKEN)

    assert TOKEN not in repr(client)
    client.close()


def test_context_manager_closes_an_owned_http_client() -> None:
    """Should close the HTTP client it created, and leave a passed-in one open."""
    with Clairic(account_id=ACCOUNT_ID, api_token=TOKEN) as owned:
        pass
    passed_in = httpx.Client()
    with Clairic(account_id=ACCOUNT_ID, api_token=TOKEN, http_client=passed_in):
        pass

    assert owned._http_client.is_closed  # pyright: ignore[reportPrivateUsage]
    assert not passed_in.is_closed
    passed_in.close()


@pytest.mark.anyio
async def test_async_extract_returns_typed_answers() -> None:
    """Should extract with the async client like with the sync one."""
    recorder = Recorder("invoice")

    async with _async_client(recorder) as client:
        result = await client.extract(INVOICE_STATE, InvoiceExtraction)

    assert result.data.invoice_number.value == "INV-2291"
    assert result.data.days_to_pay.p90 == 37
    assert len(recorder.requests) == 1


@pytest.mark.anyio
async def test_async_error_responses_raise_typed_errors() -> None:
    """Should map errors with the async client like with the sync one."""
    async with _async_client(Recorder("err_list_no_items")) as client:
        with pytest.raises(InvalidRequestError) as raised:
            await client.extract(INVOICE_STATE, InvoiceExtraction)

    assert raised.value.code == 3030


@pytest.mark.anyio
async def test_async_timeout_raises_api_timeout_error() -> None:
    """Should raise APITimeoutError with the async client."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with _async_client(handler) as client:
        with pytest.raises(APITimeoutError):
            await client.extract(INVOICE_STATE, InvoiceExtraction)


@pytest.mark.anyio
async def test_async_truncated_result_emits_a_warning() -> None:
    """Should warn, pointing at the caller, with the async client."""

    def truncate(body: dict[str, Any]) -> None:
        body["result"]["truncated"] = True

    async with _async_client(Recorder("invoice", truncate)) as client:
        with pytest.warns(ClairicTruncationWarning) as caught:
            await client.extract(INVOICE_STATE, InvoiceExtraction)

    assert caught[0].filename == __file__
