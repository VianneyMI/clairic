"""Unofficial typed Python SDK for Cloudflare Clairic.

Clairic is a Workers AI extraction model: it reads a text and returns typed values for named
fields, with confidence scores, probabilities of absence and percentile ranges. This package is
not affiliated with or endorsed by Cloudflare.

See https://developers.cloudflare.com/workers-ai/models/clairic/ for the model reference.
"""

from clairic._client import AsyncClairic, Clairic
from clairic._version import __version__
from clairic.answers import (
    Answer,
    DateAnswer,
    DateEstimateAnswer,
    DatetimeAnswer,
    DurationAnswer,
    DurationUnit,
    EstimateAnswer,
    ForecastAnswer,
    ForecastStep,
    ListAnswer,
    NumberAnswer,
    Span,
    TextAnswer,
    TextListAnswer,
    TimeAnswer,
)
from clairic.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    ClairicConfigurationError,
    ClairicError,
    ClairicTruncationWarning,
    ContextWindowExceededError,
    InvalidRequestError,
    ModelDefinitionError,
)
from clairic.result import Result, Usage
from clairic.specs import (
    Date,
    Datetime,
    Duration,
    Estimate,
    Forecast,
    Interval,
    List,
    Number,
    Scale,
    Spec,
    Text,
    Time,
)

__all__ = [
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "Answer",
    "AsyncClairic",
    "AuthenticationError",
    "Clairic",
    "ClairicConfigurationError",
    "ClairicError",
    "ClairicTruncationWarning",
    "ContextWindowExceededError",
    "Date",
    "DateAnswer",
    "DateEstimateAnswer",
    "Datetime",
    "DatetimeAnswer",
    "Duration",
    "DurationAnswer",
    "DurationUnit",
    "Estimate",
    "EstimateAnswer",
    "Forecast",
    "ForecastAnswer",
    "ForecastStep",
    "Interval",
    "InvalidRequestError",
    "List",
    "ListAnswer",
    "ModelDefinitionError",
    "Number",
    "NumberAnswer",
    "Result",
    "Scale",
    "Span",
    "Spec",
    "Text",
    "TextAnswer",
    "TextListAnswer",
    "Time",
    "TimeAnswer",
    "Usage",
    "__version__",
]
