"""The provider contract.

A provider turns one subscription account into the normalized snapshot that the
coordinator, the sensors and the dashboards all read.  Adding a provider is one
module plus one registry entry in ``providers/__init__.py``: nothing else in the
integration knows about vendor APIs.

Snapshot schema (all keys optional, but a provider should always return
``budget`` and ``windows``)::

    {
      "budget": {                       # the included monthly allowance
        "used": float, "max": float, "percent": float,
        "remaining": float,             # every dollar still available
        "currency": "USD",              # ISO 4217, drives the sensor unit
        "plan_name": str, "plan_id": str,
        "days_left": float, "days_elapsed": float,
        "current_daily_average": float,
        "suggested_daily_pace": float,
        "pace_status": "under" | "on" | "over",
      },
      "windows": {                      # rolling rate-limit windows
        "<window_key>": {
          "label": str, "used": float, "cap": float, "remaining": float,
          "percent": float, "reset_at": datetime, "days_left": float,
          "pace_per_day": float, "exceeded": bool,
        },
      },
      "subscription": {
        "plan_id": str, "status": str, "period_start": datetime,
        "period_end": datetime, "cancel_at_period_end": bool,
      },
      "summary": {
        "total_cost": float, "total_count": float, "total_tokens": float,
        "total_tokens_in": float, "total_tokens_out": float,
        "success_rate": float,
      },
      "daily": {
        "today": float,
        "days": [{"date": "YYYY-MM-DD", "usd": float}],
        "cumulative": [{"date": "YYYY-MM-DD", "usd": float}],
        "pace": [{"date": "YYYY-MM-DD", "usd": float}],
        "period_start": str, "period_end": str, "max_usd": float,
        "pace_per_day_usd": float, "source": "api" | "unavailable",
        "backfilled_at": str,
      },
    }

``budget.used``/``budget.max`` describe the *plan* allowance; anything extra the
provider knows (purchased credits, free credits, non-plan spend) is an extra
key, so adding a provider never has to touch the sensors.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, ClassVar

import aiohttp

from ..const import CONF_API_KEY, DEFAULT_CURRENCY


@dataclass(frozen=True, slots=True)
class ConfigField:
    """One credential field a provider asks for in the config flow."""

    key: str
    translation_key: str = ""
    required: bool = True
    default: str | None = None
    secret: bool = False

    def __post_init__(self) -> None:
        if not self.translation_key:
            object.__setattr__(self, "translation_key", self.key)


@dataclass(slots=True)
class Account:
    """The identity a provider resolved from the stored credentials."""

    login: str
    scope_key: str
    extra: dict[str, Any] = field(default_factory=dict)

    def unique_id(self, provider_id: str) -> str:
        """Return the config-entry unique id for this account."""
        return f"{provider_id}:{self.scope_key}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe view for diagnostics and the snapshot."""
        return {"login": self.login, "scope_key": self.scope_key, **self.extra}


@dataclass(slots=True)
class DailyCache:
    """Coordinator-owned memo for a provider's daily backfill.

    Past days never change, so a provider that has to request one range per day
    fills this once and afterwards only refreshes the final (today) total.
    """

    day: date | None = None
    period_end: datetime | None = None
    boundaries: list[datetime] = field(default_factory=list)
    totals: list[float | None] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Return True when a complete, consistent series is cached."""
        return bool(self.boundaries) and len(self.boundaries) == len(self.totals)

    def clear(self) -> None:
        """Forget the cached series."""
        self.day = None
        self.period_end = None
        self.boundaries = []
        self.totals = []


class BaseProvider:
    """Base class for a subscription provider."""

    provider_id: ClassVar[str] = ""
    name: ClassVar[str] = ""
    documentation_url: ClassVar[str] = ""
    setup_hint: ClassVar[str] = "Paste the API key for the account you want to track."
    currency: ClassVar[str] = DEFAULT_CURRENCY
    config_fields: ClassVar[tuple[ConfigField, ...]] = (
        ConfigField(CONF_API_KEY, secret=True),
    )

    def __init__(
        self,
        session: aiohttp.ClientSession,
        credentials: Mapping[str, Any],
        cache: DailyCache | None = None,
        timezone: str = "UTC",
    ) -> None:
        self._session = session
        self._credentials = dict(credentials)
        self.cache = cache if cache is not None else DailyCache()
        self.timezone = timezone or "UTC"

    @property
    def session(self) -> aiohttp.ClientSession:
        """Return the Home Assistant aiohttp session."""
        return self._session

    @property
    def credentials(self) -> Mapping[str, Any]:
        """Return a read-only view of the stored credentials."""
        return MappingProxyType(self._credentials)

    def credential(self, key: str) -> str | None:
        """Return one credential as a stripped string, or None."""
        value = self._credentials.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe provider metadata for diagnostics."""
        return {
            "id": self.provider_id,
            "name": self.name,
            "documentation_url": self.documentation_url,
        }

    async def async_validate(self) -> Account:
        """Resolve the account behind the stored credentials.

        Raises :class:`~..api.ProviderAuthError` when the credentials are
        rejected and :class:`~..api.ProviderApiError` when the identity payload
        is unexpected.
        """
        raise NotImplementedError

    async def async_fetch(self, account: Account) -> dict[str, Any]:
        """Return a fresh normalized snapshot for ``account``."""
        raise NotImplementedError
