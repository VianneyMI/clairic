"""Sync and async Clairic clients over the Workers AI REST API."""

from __future__ import annotations

import datetime as dt
import os
import warnings
from types import TracebackType
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from typing_extensions import Self

from clairic._compile import build_data, fields_payload
from clairic._version import __version__
from clairic.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    ClairicConfigurationError,
    ClairicTruncationWarning,
    ContextWindowExceededError,
    InvalidRequestError,
)
from clairic.result import Result, Usage

M = TypeVar("M", bound=BaseModel)

DEFAULT_BASE_URL = "https://api.cloudflare.com/client/v4"
DEFAULT_TIMEOUT = 30.0
ACCOUNT_ID_VARIABLE = "CLOUDFLARE_ACCOUNT_ID"
API_TOKEN_VARIABLE = "CLOUDFLARE_API_TOKEN"


class _ClientBase:
    """Request building and response parsing shared by the sync and async clients."""

    def __init__(self, *, account_id: str | None, api_token: str | None, base_url: str) -> None:
        account_id = account_id or os.environ.get(ACCOUNT_ID_VARIABLE)
        api_token = api_token or os.environ.get(API_TOKEN_VARIABLE)
        if not account_id:
            raise ClairicConfigurationError(
                f"Pass account_id or set the {ACCOUNT_ID_VARIABLE} environment variable"
            )
        if not api_token:
            raise ClairicConfigurationError(
                f"Pass api_token or set the {API_TOKEN_VARIABLE} environment variable"
            )
        self.account_id = account_id
        self._api_token = api_token
        self._url = f"{base_url.rstrip('/')}/accounts/{account_id}/ai/run/@cf/cloudflare/clairic"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(account_id={self.account_id!r})"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_token}",
            "User-Agent": f"clairic-python/{__version__}",
        }

    @staticmethod
    def _body(state: str, model: type[BaseModel], reference_date: dt.date | None) -> dict[str, Any]:
        fields = fields_payload(model)
        if not state:
            raise ValueError("state must be a non-empty text")
        body: dict[str, Any] = {"model": "clairic", "state": state, "fields": fields}
        if reference_date is not None:
            if isinstance(reference_date, dt.datetime):
                reference_date = reference_date.date()
            body["reference_date"] = reference_date.isoformat()
        return body

    @staticmethod
    def _parse(response: httpx.Response, model: type[M]) -> Result[M]:
        status_code = response.status_code
        request_id = response.headers.get("cf-ai-req-id")
        try:
            envelope = _Envelope.model_validate_json(response.content)
        except ValidationError as error:
            raise APIError(
                f"Unexpected response from Cloudflare: {response.text[:500]!r}",
                status_code=status_code,
                request_id=request_id,
            ) from error
        if response.is_error or not envelope.success:
            raise _api_error(status_code, envelope, request_id)

        try:
            result = _ResultBody.model_validate(envelope.result)
            data = build_data(model, result.answers)
        except ValidationError as error:
            raise APIError(
                f"Clairic returned answers that do not fit {model.__name__}: {error}",
                status_code=status_code,
                request_id=request_id,
            ) from error
        if result.truncated:
            warnings.warn(
                "Clairic truncated the input: the answers were computed on part of it",
                ClairicTruncationWarning,
                stacklevel=3,
            )
        return Result[model](
            data=data,
            usage=result.usage,
            truncated=result.truncated,
            model=result.model,
            request_id=request_id,
        )


class _ErrorItem(BaseModel):
    code: int | None = None
    message: str = ""


class _Envelope(BaseModel):
    """Cloudflare API response envelope."""

    success: bool = False
    errors: list[_ErrorItem] = []
    result: Any = None


class _ResultBody(BaseModel):
    """`result` of a successful Clairic response."""

    answers: dict[str, Any]
    truncated: bool
    usage: Usage
    model: str


def _api_error(status_code: int, envelope: _Envelope, request_id: str | None) -> APIError:
    first = envelope.errors[0] if envelope.errors else _ErrorItem()
    message = first.message or f"HTTP {status_code}"
    if status_code == 401:
        error_type: type[APIError] = AuthenticationError
    elif status_code == 413:
        error_type = ContextWindowExceededError
    elif status_code in (400, 422):
        error_type = InvalidRequestError
    else:
        error_type = APIError
    return error_type(message, status_code=status_code, code=first.code, request_id=request_id)


class Clairic(_ClientBase):
    """Client for Cloudflare Clairic.

    Credentials default to the `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` environment
    variables. Close the client, or use it as a context manager, to release its connections.

    ```python
    with Clairic() as clairic:
        res = clairic.extract(text, InvoiceExtraction)
    ```

    Args:
        account_id: str | None
            Cloudflare account id.
        api_token: str | None
            Cloudflare API token.
        base_url: str
            Cloudflare API root, to route requests through a proxy.
        timeout: float | httpx.Timeout
            Seconds to wait for a response. Ignored when `http_client` is given.
        http_client: httpx.Client | None
            HTTP client to send requests with, for custom transports or proxies. The caller
            closes it.

    Raises:
        ClairicConfigurationError:
            When the account id or the token is neither passed nor set in the environment.
    """

    def __init__(
        self,
        *,
        account_id: str | None = None,
        api_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(account_id=account_id, api_token=api_token, base_url=base_url)
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.Client(timeout=timeout)

    def extract(
        self, state: str, model: type[M], *, reference_date: dt.date | None = None
    ) -> Result[M]:
        """Extract the fields of `model` from `state`.

        Clairic answers every field in a single pass without generating text, usually in under
        a second. Each field of `model` declares its Clairic type through its answer type, its
        options through an `Annotated` spec, and its instructions through
        `Field(description=...)`.

        Args:
            state: str
                Text to read, up to Clairic's 65,536-token context window.
            model: type[M]
                Extraction model whose fields are answer types.
            reference_date: date | None
                Date that anchors dates written without a year and relative computations, such
                as "net 30". Set it whenever a field depends on today's date.

        Returns:
            The answers in an instance of `model`, with the token usage and the request id.

        Raises:
            ModelDefinitionError:
                When `model` cannot be sent to Clairic, before any request.
            AuthenticationError:
                When Cloudflare rejects the credentials.
            InvalidRequestError:
                When Cloudflare rejects the request content.
            ContextWindowExceededError:
                When `state` is too long.
            APIError:
                For any other error response, or answers that do not fit `model`.
            APIConnectionError:
                When Cloudflare cannot be reached; `APITimeoutError` on timeout.
        """
        body = self._body(state, model, reference_date)
        try:
            response = self._http_client.post(self._url, json=body, headers=self._headers())
        except httpx.TimeoutException as error:
            raise APITimeoutError(f"Clairic did not answer in time: {error}") from error
        except httpx.TransportError as error:
            raise APIConnectionError(f"Could not reach Cloudflare: {error}") from error
        return self._parse(response, model)

    def close(self) -> None:
        """Close the HTTP connections, unless the HTTP client was passed in."""
        if self._owns_http_client:
            self._http_client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class AsyncClairic(_ClientBase):
    """Async client for Cloudflare Clairic.

    Same options and behavior as `Clairic`, with `extract` as a coroutine.

    ```python
    async with AsyncClairic() as clairic:
        res = await clairic.extract(text, InvoiceExtraction)
    ```

    Args:
        account_id: str | None
            Cloudflare account id.
        api_token: str | None
            Cloudflare API token.
        base_url: str
            Cloudflare API root, to route requests through a proxy.
        timeout: float | httpx.Timeout
            Seconds to wait for a response. Ignored when `http_client` is given.
        http_client: httpx.AsyncClient | None
            HTTP client to send requests with. The caller closes it.

    Raises:
        ClairicConfigurationError:
            When the account id or the token is neither passed nor set in the environment.
    """

    def __init__(
        self,
        *,
        account_id: str | None = None,
        api_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(account_id=account_id, api_token=api_token, base_url=base_url)
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout)

    async def extract(
        self, state: str, model: type[M], *, reference_date: dt.date | None = None
    ) -> Result[M]:
        """Extract the fields of `model` from `state`. See `Clairic.extract`."""
        body = self._body(state, model, reference_date)
        try:
            response = await self._http_client.post(self._url, json=body, headers=self._headers())
        except httpx.TimeoutException as error:
            raise APITimeoutError(f"Clairic did not answer in time: {error}") from error
        except httpx.TransportError as error:
            raise APIConnectionError(f"Could not reach Cloudflare: {error}") from error
        return self._parse(response, model)

    async def aclose(self) -> None:
        """Close the HTTP connections, unless the HTTP client was passed in."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
