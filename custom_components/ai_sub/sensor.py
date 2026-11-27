"""Sensors for subscription spend, pace, and rolling windows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_CURRENCY, DOMAIN
from .coordinator import AiSubCoordinator
from .entity import AiSubEntity


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all AI Sub sensors."""
    coordinator: AiSubCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SuggestedPaceSensor(coordinator),
            MaxUsageSensor(coordinator),
            UsageSensor(coordinator),
            RemainingBalanceSensor(coordinator),
            SpentSensor(coordinator),
            DailyUsageSensor(coordinator),
            WeeklyUsageSensor(coordinator),
            FiveHourUsageSensor(coordinator),
            WeeklyMaxSensor(coordinator),
            FiveHourMaxSensor(coordinator),
            PlanSensor(coordinator),
            PeriodEndSensor(coordinator),
        ]
    )


class _MonetarySensor(AiSubEntity, SensorEntity):
    """A money sensor that follows the currency reported by the provider."""

    _attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_unit_of_measurement(self) -> str:
        return self.budget.get("currency") or DEFAULT_CURRENCY


class SuggestedPaceSensor(AiSubEntity, SensorEntity):
    """How much per day keeps the account on pace for renewal.

    This is a rate, not money in the account: it carries a "<currency>/day"
    unit and no monetary device class (Home Assistant only accepts state class
    ``total`` for monetary sensors, which would be wrong for a pace).
    """

    _attr_translation_key = "suggested_pace"
    _attr_icon = "mdi:speedometer"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, "suggested_pace")

    @property
    def native_unit_of_measurement(self) -> str:
        return f"{self.budget.get('currency') or DEFAULT_CURRENCY}/day"

    @property
    def native_value(self) -> float | None:
        return self.budget.get("suggested_daily_pace")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        budget = self.budget
        windows = self.windows
        return {
            "status": budget.get("pace_status"),
            "current_daily_average": budget.get("current_daily_average"),
            "monthly_pace": budget.get("monthly_pace"),
            "weekly_pace": (windows.get("week") or {}).get("pace_per_day"),
            "five_hour_pace": (windows.get("five_hour") or {}).get("pace_per_day"),
            "days_left": budget.get("days_left"),
            "monthly_remaining": budget.get("monthly_remaining"),
            "purchased_remaining": budget.get("purchased_remaining"),
            "free_remaining": budget.get("free_remaining"),
            "remaining": budget.get("remaining"),
            "plan": budget.get("plan_name"),
            "period_end": _iso(
                (self.snapshot.get("subscription") or {}).get("period_end")
            ),
        }


class MaxUsageSensor(_MonetarySensor):
    """The monthly included allowance for the current plan."""

    _attr_translation_key = "max_usage"
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, "max_usage")

    @property
    def native_value(self) -> float | None:
        return self.budget.get("max")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        subscription = self.snapshot.get("subscription") or {}
        windows = self.windows
        return {
            "plan_id": subscription.get("plan_id"),
            "plan_name": self.budget.get("plan_name"),
            "subscription_status": subscription.get("status"),
            "weekly_cap": (windows.get("week") or {}).get("cap"),
            "five_hour_cap": (windows.get("five_hour") or {}).get("cap"),
            "monthly_remaining": self.budget.get("monthly_remaining"),
            "purchased_remaining": self.budget.get("purchased_remaining"),
            "free_remaining": self.budget.get("free_remaining"),
            "period_start": _iso(subscription.get("period_start")),
            "period_end": _iso(subscription.get("period_end")),
        }


class UsageSensor(AiSubEntity, SensorEntity):
    """Percentage of the included monthly allowance consumed."""

    _attr_translation_key = "usage"
    _attr_icon = "mdi:gauge"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, "usage")

    @property
    def native_value(self) -> float | None:
        return self.budget.get("percent")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "used": self.budget.get("used"),
            "total_spent": self.budget.get("total_spent"),
            "max": self.budget.get("max"),
            "remaining": self.budget.get("remaining"),
            "monthly_remaining": self.budget.get("monthly_remaining"),
            "plan": self.budget.get("plan_name"),
            "period_end": _iso(
                (self.snapshot.get("subscription") or {}).get("period_end")
            ),
        }


class RemainingBalanceSensor(_MonetarySensor):
    """All remaining credit for the account."""

    _attr_translation_key = "remaining_balance"
    _attr_icon = "mdi:wallet"

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, "remaining_balance")

    @property
    def native_value(self) -> float | None:
        return self.budget.get("remaining")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "monthly_remaining": self.budget.get("monthly_remaining"),
            "purchased_remaining": self.budget.get("purchased_remaining"),
            "free_remaining": self.budget.get("free_remaining"),
        }


class SpentSensor(_MonetarySensor):
    """Amount spent in the current billing period."""

    _attr_translation_key = "spent"
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, "spent")

    @property
    def native_value(self) -> float | None:
        total_spent = self.budget.get("total_spent")
        return total_spent if total_spent is not None else self.budget.get("used")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        summary = self.snapshot.get("summary") or {}
        return {
            "requests": summary.get("total_count"),
            "tokens": summary.get("total_tokens"),
            "tokens_in": summary.get("total_tokens_in"),
            "tokens_out": summary.get("total_tokens_out"),
            "success_rate": summary.get("success_rate"),
        }


class DailyUsageSensor(_MonetarySensor):
    """Amount spent today, plus the backfilled daily/cumulative series."""

    _attr_translation_key = "daily_usage"
    _attr_icon = "mdi:chart-bar"

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, "daily_usage")

    @property
    def daily(self) -> dict[str, Any]:
        return self.snapshot.get("daily") or {}

    @property
    def native_value(self) -> float | None:
        return self.daily.get("today")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        daily = self.daily
        return {
            "days": daily.get("days", []),
            "cumulative": daily.get("cumulative", []),
            "pace": daily.get("pace", []),
            "pace_per_day_usd": daily.get("pace_per_day_usd"),
            "period_start": daily.get("period_start"),
            "period_end": daily.get("period_end"),
            "max_usd": daily.get("max_usd"),
            "source": daily.get("source"),
            "backfilled_at": daily.get("backfilled_at"),
        }


class _WindowUsageSensor(AiSubEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _window_key = ""

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, f"{self._window_key}_usage")

    @property
    def native_value(self) -> float | None:
        return (self.windows.get(self._window_key) or {}).get("percent")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        window = self.windows.get(self._window_key) or {}
        return {
            "used": window.get("used"),
            "cap": window.get("cap"),
            "remaining": window.get("remaining"),
            "reset_at": _iso(window.get("reset_at")),
            "days_left": window.get("days_left"),
            "pace_per_day": window.get("pace_per_day"),
            "exceeded": window.get("exceeded"),
        }


class WeeklyUsageSensor(_WindowUsageSensor):
    """Weekly rolling window usage percentage."""

    _attr_translation_key = "weekly_usage"
    _attr_icon = "mdi:calendar-week"
    _window_key = "week"


class FiveHourUsageSensor(_WindowUsageSensor):
    """Five-hour rolling window usage percentage."""

    _attr_translation_key = "five_hour_usage"
    _attr_icon = "mdi:clock-fast"
    _window_key = "five_hour"


class _WindowMaxSensor(_MonetarySensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _window_key = ""

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, f"{self._window_key}_max")

    @property
    def native_value(self) -> float | None:
        return (self.windows.get(self._window_key) or {}).get("cap")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        window = self.windows.get(self._window_key) or {}
        return {
            "used": window.get("used"),
            "remaining": window.get("remaining"),
            "reset_at": _iso(window.get("reset_at")),
            "exceeded": window.get("exceeded"),
        }


class WeeklyMaxSensor(_WindowMaxSensor):
    """Weekly rolling cap in the account currency."""

    _attr_translation_key = "weekly_max"
    _attr_icon = "mdi:calendar-week"
    _window_key = "week"


class FiveHourMaxSensor(_WindowMaxSensor):
    """Five-hour rolling cap in the account currency."""

    _attr_translation_key = "five_hour_max"
    _attr_icon = "mdi:clock-fast"
    _window_key = "five_hour"


class PlanSensor(AiSubEntity, SensorEntity):
    """Active subscription plan name."""

    _attr_translation_key = "plan"
    _attr_icon = "mdi:card-account-details"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, "plan")

    @property
    def native_value(self) -> str | None:
        return self.budget.get("plan_name")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        subscription = self.snapshot.get("subscription") or {}
        return {
            "provider": self.snapshot.get("provider"),
            "plan_id": subscription.get("plan_id"),
            "status": subscription.get("status"),
            "cancel_at_period_end": subscription.get("cancel_at_period_end"),
            "period_start": _iso(subscription.get("period_start")),
            "period_end": _iso(subscription.get("period_end")),
            "monthly_allowance": self.budget.get("monthly_grant"),
        }


class PeriodEndSensor(AiSubEntity, SensorEntity):
    """Billing period renewal timestamp."""

    _attr_translation_key = "period_end"
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, "period_end")

    @property
    def native_value(self) -> datetime | None:
        return (self.snapshot.get("subscription") or {}).get("period_end")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        subscription = self.snapshot.get("subscription") or {}
        return {
            "days_left": self.budget.get("days_left"),
            "period_start": _iso(subscription.get("period_start")),
            "status": subscription.get("status"),
        }
