"""HTTP plumbing shared by every subscription provider.

Each provider is a bearer-token JSON API over HTTPS.  The error taxonomy and the
request helper live here so a provider only has to describe its endpoints and
how to normalize their payloads.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


class ProviderError(Exception):
    """Base error for a subscription provider."""


class ProviderAuthError(ProviderError):
    """The provider rejected the stored credentials."""


class ProviderConnectionError(ProviderError):
    """The provider API could not be reached."""


class ProviderApiError(ProviderError):
    """The provider API answered with an unexpected status."""

    def __init__(self, status: int, path: str) -> None:
        self.status = status
        self.path = path
        super().__init__(f"{path} returned HTTP {status}")


class UnknownProviderError(ProviderError):
    """A config entry references a provider that this build does not ship."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"Unknown AI subscription provider: {provider_id}")


async def async_get_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    headers: Mapping[str, str],
    params: Mapping[str, Any] | None = None,
    timeout: aiohttp.ClientTimeout | None = None,
) -> Any:
    """GET a JSON document, mapping transport failures to provider errors.

    ``401``/``403`` become :class:`ProviderAuthError` so the coordinator can
    trigger a reauth flow; every other non-200 answer is a
    :class:`ProviderApiError` and keeps the request URL for the log.
    """
    try:
        async with session.get(
            url,
            headers=dict(headers),
            params=params,
            timeout=timeout or REQUEST_TIMEOUT,
        ) as response:
            if response.status in (401, 403):
                raise ProviderAuthError("The provider rejected the API key")
            if response.status != 200:
                raise ProviderApiError(response.status, url)
            try:
                return await response.json(content_type=None)
            except (ValueError, aiohttp.ContentTypeError) as err:
                raise ProviderApiError(200, url) from err
    except TimeoutError as err:
        raise ProviderConnectionError(f"Timed out calling {url}") from err
    except aiohttp.ClientError as err:
        raise ProviderConnectionError(f"Could not reach {url}: {err}") from err
