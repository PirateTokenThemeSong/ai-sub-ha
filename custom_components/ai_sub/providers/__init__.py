"""Registry of the subscription providers shipped with AI Sub.

Command Code is the only provider available today.  A new provider is one module
plus one line in :data:`PROVIDERS`; the coordinator, the config flow and the
entities only ever talk to the :class:`~.base.BaseProvider` contract.
"""

from __future__ import annotations

from typing import Any

from ..api import UnknownProviderError
from .base import Account, BaseProvider, ConfigField, DailyCache
from .commandcode import CommandCodeProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    CommandCodeProvider.provider_id: CommandCodeProvider,
}

DEFAULT_PROVIDER_ID = CommandCodeProvider.provider_id


def available_providers() -> dict[str, str]:
    """Return ``{provider_id: display name}`` for every shipped provider."""
    return {provider_id: provider.name for provider_id, provider in PROVIDERS.items()}


def get_provider_class(provider_id: str) -> type[BaseProvider]:
    """Return the provider class for ``provider_id``.

    Raises :class:`~..api.UnknownProviderError` when the entry references a
    provider this build does not ship (for example after a downgrade).
    """
    try:
        return PROVIDERS[provider_id]
    except KeyError as err:
        raise UnknownProviderError(provider_id) from err


def build_provider(
    session: Any,
    provider_id: str,
    credentials: Any,
    cache: DailyCache | None = None,
    timezone: str = "UTC",
) -> BaseProvider:
    """Instantiate the provider for one config entry."""
    return get_provider_class(provider_id)(session, credentials, cache, timezone)


__all__ = [
    "DEFAULT_PROVIDER_ID",
    "PROVIDERS",
    "Account",
    "BaseProvider",
    "ConfigField",
    "DailyCache",
    "available_providers",
    "build_provider",
    "get_provider_class",
]
