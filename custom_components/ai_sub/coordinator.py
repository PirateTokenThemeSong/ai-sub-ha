"""Polling coordinator for AI subscription usage."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ProviderApiError,
    ProviderAuthError,
    ProviderConnectionError,
    UnknownProviderError,
)
from .const import (
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .providers import DEFAULT_PROVIDER_ID, BaseProvider, DailyCache, build_provider

_LOGGER = logging.getLogger(__name__)


class AiSubCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch every provider payload for one account on a schedule."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        provider_id = entry.data.get(CONF_PROVIDER) or DEFAULT_PROVIDER_ID
        self.entry = entry
        self.provider_id = provider_id
        self.cache = DailyCache()
        self.provider: BaseProvider = build_provider(
            async_get_clientsession(hass),
            provider_id,
            entry.data,
            self.cache,
            timezone=hass.config.time_zone or "UTC",
        )
        self._account: Any = None
        self._account_dict: dict[str, Any] = {}
        interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    @property
    def account(self) -> Any:
        """Return the resolved account, if the first refresh ran."""
        return self._account

    @property
    def account_id(self) -> str:
        """Stable device identifier for this provider account."""
        scope = (self._account_dict or {}).get("scope_key")
        return f"{self.provider_id}:{scope}" if scope else self.entry.entry_id

    @property
    def account_name(self) -> str:
        """Human-readable account label used for the device name."""
        return (self._account_dict or {}).get("login") or self.entry.title

    @property
    def provider_name(self) -> str:
        """Display name of the provider behind this entry."""
        return self.provider.name

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            if self._account is None:
                self._account = await self.provider.async_validate()
                self._account_dict = self._account.as_dict()
            snapshot = await self.provider.async_fetch(self._account)
        except ProviderAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ProviderConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except ProviderApiError as err:
            raise UpdateFailed(str(err)) from err
        except UnknownProviderError as err:  # pragma: no cover - registry is static
            raise UpdateFailed(str(err)) from err

        snapshot = dict(snapshot)
        snapshot.setdefault("budget", {})
        snapshot.setdefault("windows", {})
        snapshot["provider"] = self.provider_id
        snapshot["account"] = self._account_dict
        snapshot["generated_at"] = datetime.now(UTC)
        return snapshot
