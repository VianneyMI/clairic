"""Exceptions and warnings raised by the clairic SDK."""

from __future__ import annotations

__all__ = [
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "AuthenticationError",
    "ClairicConfigurationError",
    "ClairicError",
    "ClairicTruncationWarning",
    "ContextWindowExceededError",
    "InvalidRequestError",
    "ModelDefinitionError",
]


class ClairicError(Exception):
    """Base class of every exception raised by the clairic SDK."""


class ClairicConfigurationError(ClairicError):
    """Raised when the client is missing its Cloudflare account id or API token."""


class ModelDefinitionError(ClairicError):
    """Raised when an extraction model cannot be turned into Clairic fields.

    Raised before any request is sent. The message names the offending field.
    """


class APIError(ClairicError):
    """Raised when the Cloudflare API answers with an error.

    Attributes:
        message: str
            Error message returned by Cloudflare.
        status_code: int
            HTTP status of the response.
        code: int | None
            Cloudflare error code, such as 3030 for a request the model rejects.
        request_id: str | None
            Workers AI request id (`cf-ai-req-id` header), to quote when contacting Cloudflare.
            `None` when Cloudflare rejects the request before it reaches Workers AI, as with
            authentication errors and malformed bodies.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.request_id = request_id

    def __str__(self) -> str:
        return f"{self.message} (HTTP {self.status_code}, code {self.code})"


class AuthenticationError(APIError):
    """Raised on HTTP 401: the API token is missing or invalid, or the account id is unknown."""


class InvalidRequestError(APIError):
    """Raised when Cloudflare rejects the request content.

    Covers schema violations (HTTP 400, code 5006), field definitions the model rejects
    (HTTP 422, code 3030) and malformed bodies (HTTP 400, code 6003).
    """


class ContextWindowExceededError(APIError):
    """Raised on HTTP 413: the input is estimated to exceed Clairic's 65,536-token context window.

    Cloudflare estimates the input size from its length in characters before tokenizing it.
    """


class APIConnectionError(ClairicError):
    """Raised when the Cloudflare API cannot be reached."""


class APITimeoutError(APIConnectionError):
    """Raised when the Cloudflare API does not answer within the client timeout."""


class ClairicTruncationWarning(UserWarning):
    """Emitted when Clairic reports `truncated: true`: answers were computed on part of the input.

    Turn it into an error with `warnings.simplefilter("error", ClairicTruncationWarning)`.
    """
