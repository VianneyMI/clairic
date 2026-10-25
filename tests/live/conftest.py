import os
from collections.abc import Iterator

import pytest
from dotenv import load_dotenv

from clairic import AsyncClairic, Clairic

load_dotenv()

pytestmark = pytest.mark.live


def _require_credentials() -> None:
    if not (os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_API_TOKEN")):
        pytest.skip("set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN to run live tests")


@pytest.fixture
def clairic() -> Iterator[Clairic]:
    _require_credentials()
    with Clairic() as client:
        yield client


@pytest.fixture
def async_clairic() -> AsyncClairic:
    _require_credentials()
    return AsyncClairic()
