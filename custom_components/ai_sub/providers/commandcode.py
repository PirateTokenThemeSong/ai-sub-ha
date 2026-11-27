"""Command Code: the first shipped provider.

Command Code (https://commandcode.ai) is an AI coding subscription.  Its alpha
billing API exposes the account identity, the credit balances, the rolling
five-hour/weekly windows and a usage summary.  Everything below -- endpoints,
plan tables, payload shapes -- is vendor specific and stays in this module.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from ..api import (
    ProviderApiError,
    ProviderAuthError,
    ProviderConnectionError,
    async_get_json,
)
from ..calc import (
    api_param,
    build_daily_series,
    day_boundaries,
    days_since,
    days_until,
    empty_daily_series,
    number,
    pace_status,
    parse_timestamp,
    percent,
)
from ..const import CONF_API_KEY
from .base import Account, BaseProvider, ConfigField

_LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.commandcode.ai"
CONFIG_URL = "https://commandcode.ai/usage"

CONF_BASE_URL = "base_url"

# The official CLI maps planId -> monthly included credits.  GOAT/Pro/Go are
# "usage value" plans, but the billing API still reports the included credit
# balance in these units, so this is the right denominator for percentages.
PLAN_MONTHLY_CREDITS: dict[str, float] = {
    "individual-go": 10.0,
    "individual-go-v1": 10.0,
    "individual-goat": 70.0,
    "individual-pro": 30.0,
    "individual-pro-v1": 80.0,
    "individual-provider": 15.0,
    "individual-max": 150.0,
    "individual-max-10x": 150.0,
    "individual-ultra": 300.0,
    "individual-max-20x": 300.0,
    "teams-pro": 40.0,
}

PLAN_NAMES: dict[str, str] = {
    "individual-go": "Go",
    "individual-go-v1": "Go",
    "individual-goat": "GOAT",
    "individual-pro": "Pro",
    "individual-pro-v1": "Pro",
    "individual-provider": "Provider",
    "individual-max": "Max 10x",
    "individual-max-10x": "Max 10x",
    "individual-ultra": "Max 20x",
    "individual-max-20x": "Max 20x",
    "teams-pro": "Team Pro",
}

# Command Code's rolling windows.  The monthly "window" is synthesised from the
# plan grant + billing period because the API only exposes fiveHour/weekly.
WINDOW_API_KEYS = {"five_hour": "fiveHour", "week": "weekly"}
WINDOW_LABELS = {"five_hour": "5-hour", "week": "Weekly"}


class CommandCodeClient:
    """Bearer-token client for Command Code's alpha endpoints."""

    def __init__(
        self,
        session: Any,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._session = session
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ha-ai_sub/1.0.0 (AI Sub)",
        }

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await async_get_json(
            self._session,
            f"{self._base_url}{path}",
            headers=self._headers,
            params=params,
        )

    async def whoami(self) -> Any:
        """Return the user/organisation identity and billing scope."""
        return await self._get("/alpha/whoami", {"limits": "1"})

    async def credits(self, org_id: str | None = None) -> Any:
        """Return credit balances and rolling window usage."""
        params = {"orgId": org_id} if org_id else None
        return await self._get("/alpha/billing/credits", params)

    async def subscription(self, org_id: str | None = None) -> Any:
        """Return the active subscription and billing period."""
        params = {"orgId": org_id} if org_id else None
        return await self._get("/alpha/billing/subscriptions", params)

    async def usage_summary(
        self, org_id: str | None = None, since: str | None = None
    ) -> Any:
        """Return aggregate usage for the current billing period."""
        params: dict[str, str] = {}
        if org_id:
            params["orgId"] = org_id
        if since:
            params["since"] = since
        return await self._get("/alpha/usage/summary", params or None)


def _unwrap(payload: Any) -> Any:
    """Strip the alpha API's ``{success, data}`` envelope when present."""
    if (
        isinstance(payload, dict)
        and "data" in payload
        and payload.get("success") is not False
    ):
        return payload["data"]
    return payload


def plan_credits(plan_id: Any) -> float | None:
    """Return the included monthly credit grant for a plan id."""
    if not isinstance(plan_id, str) or not plan_id.strip():
        return None
    candidate = plan_id.strip().lower().replace("_", "-")
    if candidate in PLAN_MONTHLY_CREDITS:
        return PLAN_MONTHLY_CREDITS[candidate]
    for known, grant in sorted(
        PLAN_MONTHLY_CREDITS.items(), key=lambda item: -len(item[0])
    ):
        if candidate.startswith(known):
            return grant
    return None


def plan_name(plan_id: Any) -> str | None:
    """Return a human-readable plan name for a plan id."""
    if not isinstance(plan_id, str) or not plan_id.strip():
        return None
    candidate = plan_id.strip().lower().replace("_", "-")
    if candidate in PLAN_NAMES:
        return PLAN_NAMES[candidate]
    for known, name in sorted(PLAN_NAMES.items(), key=lambda item: -len(item[0])):
        if candidate.startswith(known):
            return name
    return plan_id.strip()


def parse_whoami(payload: Any) -> dict[str, Any] | None:
    """Extract the billing identity from the whoami response."""
    if not isinstance(payload, dict) or payload.get("success") is False:
        return None
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    org = payload.get("org") if isinstance(payload.get("org"), dict) else {}
    org_id = str(org["id"]).strip() if org.get("id") else None
    user_id = str(user["id"]).strip() if user.get("id") else None
    login = (
        (str(org.get("login")).strip() if org.get("login") else None)
        or (str(user.get("userName")).strip() if user.get("userName") else None)
        or (str(user.get("name")).strip() if user.get("name") else None)
        or (str(user.get("email")).strip() if user.get("email") else None)
    )
    if not login:
        return None
    return {
        "login": login,
        "user_id": user_id,
        "org_id": org_id,
        "org_login": str(org.get("login")).strip() if org.get("login") else None,
        "scope_key": f"org:{org_id}" if org_id else f"user:{user_id or login.lower()}",
    }


def parse_credits(payload: Any) -> dict[str, Any] | None:
    """Parse the billing credits response, tolerating a direct/wrapped shape."""
    root = _unwrap(payload)
    if not isinstance(root, dict):
        return None
    credits = root.get("credits") if isinstance(root.get("credits"), dict) else root
    monthly = number(credits.get("monthlyCredits"))
    purchased = number(credits.get("purchasedCredits"))
    free = number(credits.get("freeCredits"))
    known = [value for value in (monthly, purchased, free) if value is not None]
    if not known:
        return None
    total_remaining = round(sum(known), 4) if len(known) == 3 else None
    return {
        "monthly_remaining": monthly,
        "purchased_remaining": purchased,
        "free_remaining": free,
        "total_remaining": total_remaining,
        "below_threshold": credits.get("belowThreshold")
        if isinstance(credits.get("belowThreshold"), bool)
        else None,
        "threshold_usd": number(credits.get("creditThreshold")),
    }


def parse_subscription(payload: Any) -> dict[str, Any] | None:
    """Parse the subscription response, allowing an empty/absent subscription."""
    if not isinstance(payload, dict) or payload.get("success") is False:
        return None
    root = payload.get("data") if "data" in payload else payload
    if isinstance(root, list):
        root = next((item for item in root if isinstance(item, dict)), None)
    if not isinstance(root, dict):
        return None
    data = (
        root.get("subscription") if isinstance(root.get("subscription"), dict) else root
    )
    plan_id = data.get("planId") or data.get("plan_id") or data.get("plan")
    status = data.get("status")
    period_start_raw = data.get("currentPeriodStart") or data.get(
        "current_period_start"
    )
    period_end_raw = data.get("currentPeriodEnd") or data.get("current_period_end")
    if not plan_id and not status and not period_end_raw:
        return None
    return {
        "plan_id": str(plan_id).strip()
        if isinstance(plan_id, str) and plan_id.strip()
        else None,
        "status": str(status).strip()
        if isinstance(status, str) and status.strip()
        else None,
        "period_start": parse_timestamp(period_start_raw),
        "period_start_raw": api_param(period_start_raw),
        "period_end": parse_timestamp(period_end_raw),
        "cancel_at_period_end": bool(data.get("cancelAtPeriodEnd")),
    }


def parse_summary(payload: Any) -> dict[str, Any] | None:
    """Parse aggregate usage for the billing period."""
    root = _unwrap(payload)
    if not isinstance(root, dict):
        return None
    if isinstance(root.get("summary"), dict):
        root = root["summary"]
    total_cost = number(root.get("totalCost", root.get("total_cost")))
    total_count = number(root.get("totalCount", root.get("total_count")))
    total_tokens = number(root.get("totalTokens", root.get("total_tokens")))
    if all(value is None for value in (total_cost, total_count, total_tokens)):
        return None
    return {
        "total_cost": total_cost,
        "total_count": total_count,
        "total_tokens": total_tokens,
        "total_tokens_in": number(root.get("totalTokensIn")),
        "total_tokens_out": number(root.get("totalTokensOut")),
        "success_rate": number(root.get("successRate")),
        "period_start": parse_timestamp(root.get("periodStart")),
        "period_basis": root.get("periodBasis"),
    }


def parse_window(limit: Any, key: str, now: datetime) -> dict[str, Any] | None:
    """Parse one rolling window (``fiveHour`` or ``weekly``)."""
    if not isinstance(limit, dict):
        return None
    used = number(limit.get("used"))
    cap = number(limit.get("cap"))
    if used is None or cap is None or cap <= 0:
        return None
    reset_at = parse_timestamp(limit.get("resetAt"))
    seconds_left = max((reset_at - now).total_seconds(), 0.0) if reset_at else None
    days_left = seconds_left / 86400.0 if seconds_left is not None else None
    remaining = max(0.0, cap - used)
    pace = None
    if days_left is not None:
        pace = remaining / max(days_left, 1 / 24)
    return {
        "key": key,
        "label": WINDOW_LABELS.get(key, key),
        "used": used,
        "cap": cap,
        "remaining": round(remaining, 4),
        "percent": round(used / cap * 100, 2),
        "reset_at": reset_at,
        "seconds_left": round(seconds_left, 1) if seconds_left is not None else None,
        "days_left": round(days_left, 3) if days_left is not None else None,
        "pace_per_day": round(pace, 4) if pace is not None else None,
        "exceeded": bool(limit.get("exceeded"))
        if isinstance(limit.get("exceeded"), bool)
        else used >= cap,
    }


def build_snapshot(
    *,
    credits_payload: Any,
    subscription_payload: Any,
    summary_payload: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the normalized snapshot consumed by the coordinator/entities."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    credits = parse_credits(credits_payload) or {}
    subscription = parse_subscription(subscription_payload) or {}
    summary = parse_summary(summary_payload) or {}

    plan_id = subscription.get("plan_id")
    grant = plan_credits(plan_id)
    monthly_remaining = credits.get("monthly_remaining")
    total_remaining = credits.get("total_remaining")

    # The monthly balance is authoritative for *plan* consumption.  The usage
    # summary's totalCost can also include purchased/free credits, so it is kept
    # separately for the "credits used" diagnostic sensor.
    total_spent = summary.get("total_cost")
    plan_used = None
    if grant is not None and monthly_remaining is not None:
        plan_used = max(0.0, grant - monthly_remaining)
    used = plan_used if plan_used is not None else total_spent

    maximum = grant
    if maximum is None:
        if total_spent is not None and total_remaining is not None:
            maximum = total_spent + total_remaining
        elif used is not None and total_remaining is not None:
            maximum = used + total_remaining

    period_end = subscription.get("period_end")
    period_start = subscription.get("period_start")
    left_days = days_until(current, period_end)
    elapsed_days = days_since(period_start, current)
    current_daily = None
    if used is not None and elapsed_days is not None:
        current_daily = used / max(elapsed_days, 1 / 24)

    windows: dict[str, dict[str, Any]] = {}
    raw_windows = credits_payload
    if isinstance(raw_windows, dict) and "data" in raw_windows:
        raw_windows = raw_windows.get("data")
    limits = raw_windows.get("windowLimits") if isinstance(raw_windows, dict) else None
    if isinstance(limits, dict):
        for key, api_key in WINDOW_API_KEYS.items():
            parsed = parse_window(limits.get(api_key), key, current)
            if parsed:
                windows[key] = parsed

    # Daily pace: the strictest of the monthly and rolling budgets.
    monthly_pace = None
    if total_remaining is not None and left_days is not None:
        monthly_pace = total_remaining / max(left_days, 1 / 24)
    weekly_pace = windows.get("week", {}).get("pace_per_day")
    five_hour_pace = windows.get("five_hour", {}).get("pace_per_day")
    pace_candidates = [
        value
        for value in (monthly_pace, weekly_pace, five_hour_pace)
        if value is not None
    ]
    suggested_pace = min(pace_candidates) if pace_candidates else None

    return {
        "generated_at": current,
        "subscription": subscription,
        "summary": summary,
        "budget": {
            **credits,
            "currency": "USD",
            "monthly_grant": grant,
            "plan_name": plan_name(plan_id),
            "used": used,
            "total_spent": total_spent,
            "max": maximum,
            "remaining": total_remaining,
            "percent": percent(used, maximum),
            "days_left": round(left_days, 3) if left_days is not None else None,
            "days_elapsed": round(elapsed_days, 3)
            if elapsed_days is not None
            else None,
            "current_daily_average": round(current_daily, 4)
            if current_daily is not None
            else None,
            "monthly_pace": round(monthly_pace, 4)
            if monthly_pace is not None
            else None,
            "suggested_daily_pace": round(suggested_pace, 4)
            if suggested_pace is not None
            else None,
            "pace_status": pace_status(current_daily, suggested_pace),
        },
        "windows": windows,
    }


class CommandCodeProvider(BaseProvider):
    """Command Code billing/usage provider."""

    provider_id: ClassVar[str] = "commandcode"
    name: ClassVar[str] = "Command Code"
    documentation_url: ClassVar[str] = CONFIG_URL
    setup_hint: ClassVar[str] = (
        "Create a key at commandcode.ai/usage (or reuse the key from the "
        "command-code CLI) and paste it below."
    )
    config_fields: ClassVar[tuple[ConfigField, ...]] = (
        ConfigField(CONF_API_KEY, secret=True),
        ConfigField(
            CONF_BASE_URL,
            required=False,
            default=DEFAULT_BASE_URL,
            secret=False,
        ),
    )

    def __init__(
        self, session: Any, credentials: Any, cache: Any = None, timezone: str = "UTC"
    ) -> None:
        super().__init__(session, credentials, cache, timezone)
        self._client = CommandCodeClient(
            session,
            self.credential(CONF_API_KEY) or "",
            self.credential(CONF_BASE_URL) or DEFAULT_BASE_URL,
        )

    async def async_validate(self) -> Account:
        """Resolve the billing identity behind the API key."""
        account = parse_whoami(await self._client.whoami())
        if account is None:
            raise ProviderApiError(200, "/alpha/whoami")
        return Account(
            login=account["login"],
            scope_key=account["scope_key"],
            extra={
                key: value
                for key, value in account.items()
                if key not in ("login", "scope_key")
            },
        )

    async def async_fetch(self, account: Account) -> dict[str, Any]:
        """Fetch balances, subscription, summary and the daily series."""
        org_id = account.extra.get("org_id")
        credits, subscription = await asyncio.gather(
            self._client.credits(org_id),
            self._client.subscription(org_id),
        )

        summary: Any = None
        since = (parse_subscription(subscription) or {}).get("period_start_raw")
        if since:
            try:
                summary = await self._client.usage_summary(org_id, since)
            except ProviderAuthError:
                raise
            except (ProviderConnectionError, ProviderApiError) as err:
                # The aggregate summary is nice-to-have; credits/subscription
                # are enough to keep the headline sensors alive.
                _LOGGER.debug("Command Code usage summary unavailable: %s", err)

        snapshot = build_snapshot(
            credits_payload=credits,
            subscription_payload=subscription,
            summary_payload=summary,
        )
        try:
            snapshot["daily"] = await self._async_daily(snapshot, org_id, summary)
        except ProviderAuthError:
            raise
        except Exception:
            _LOGGER.exception("Could not build Command Code daily usage history")
            snapshot["daily"] = empty_daily_series(
                self.timezone,
                (snapshot.get("budget") or {}).get("max"),
                (snapshot.get("subscription") or {}).get("period_end"),
            )
        return snapshot

    def _local_today(self, now: datetime) -> tuple[str, Any]:
        """Return the local timezone name and today's local date."""
        try:
            return self.timezone, now.astimezone(ZoneInfo(self.timezone)).date()
        except Exception:
            return "UTC", now.date()

    async def _async_daily(
        self,
        snapshot: dict[str, Any],
        org_id: str | None,
        summary_payload: Any,
    ) -> dict[str, Any]:
        """Build/backfill the per-day usage series once per local day."""
        budget = snapshot.get("budget") or {}
        subscription = snapshot.get("subscription") or {}
        period_start = subscription.get("period_start")
        period_end = subscription.get("period_end")
        used = budget.get("used")
        max_usd = budget.get("max")
        now = datetime.now(UTC)
        tz_name, today_local = self._local_today(now)

        cache = self.cache
        # Past days are immutable; only today's value changes during the day.
        if cache.day == today_local and cache.period_end == period_end and cache.usable:
            return build_daily_series(
                cache.boundaries,
                cache.totals,
                used,
                tz_name,
                max_usd,
                period_end,
                now,
            )

        boundaries = day_boundaries(period_start, now, tz_name)
        if not boundaries:
            cache.day = today_local
            cache.period_end = period_end
            cache.boundaries = []
            cache.totals = []
            return build_daily_series([], [], used, tz_name, max_usd, period_end, now)

        totals: list[float | None] = []
        pending = boundaries[1:]
        if summary_payload is not None:
            parsed = parse_summary(summary_payload)
            if parsed is not None and parsed.get("total_cost") is not None:
                totals.append(parsed["total_cost"])
            else:
                pending = boundaries
        else:
            pending = boundaries

        semaphore = asyncio.Semaphore(4)

        async def fetch(boundary: datetime) -> float | None:
            async with semaphore:
                for attempt in range(2):
                    try:
                        payload = await self._client.usage_summary(
                            org_id, api_param(boundary)
                        )
                        parsed = parse_summary(payload)
                        return parsed.get("total_cost") if parsed else None
                    except ProviderAuthError:
                        raise
                    except (ProviderConnectionError, ProviderApiError) as err:
                        if attempt == 1:
                            _LOGGER.debug(
                                "Daily usage backfill failed for %s: %s", boundary, err
                            )
                return None

        totals.extend(await asyncio.gather(*(fetch(boundary) for boundary in pending)))
        cache.day = today_local
        cache.period_end = period_end
        cache.boundaries = boundaries
        cache.totals = totals
        return build_daily_series(
            boundaries,
            totals,
            used,
            tz_name,
            max_usd,
            period_end,
            now,
        )
