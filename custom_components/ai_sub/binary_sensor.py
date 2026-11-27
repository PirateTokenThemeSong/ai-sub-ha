"""Binary sensors for subscription rate-limit state."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AiSubCoordinator
from .entity import AiSubEntity


def any_limit_exceeded(snapshot: dict[str, Any] | None) -> bool:
    """Return True when any rolling window is currently at/over its cap."""
    windows = (snapshot or {}).get("windows") or {}
    return any(bool(window.get("exceeded")) for window in windows.values())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AI Sub limit binary sensors."""
    coordinator: AiSubCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LimitReachedBinarySensor(coordinator),
            WeeklyLimitReachedBinarySensor(coordinator),
            FiveHourLimitReachedBinarySensor(coordinator),
        ]
    )


class LimitReachedBinarySensor(AiSubEntity, BinarySensorEntity):
    """On when any subscription rolling window is at its cap."""

    _attr_translation_key = "limit_reached"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-octagon"

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, "limit_reached")

    @property
    def is_on(self) -> bool:
        return any_limit_exceeded(self.snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            key: {
                "percent": window.get("percent"),
                "used": window.get("used"),
                "cap": window.get("cap"),
                "reset_at": window.get("reset_at").isoformat()
                if window.get("reset_at")
                else None,
            }
            for key, window in self.windows.items()
        }


class _WindowLimitBinarySensor(AiSubEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _window_key = ""

    def __init__(self, coordinator: AiSubCoordinator) -> None:
        super().__init__(coordinator, f"{self._window_key}_limit_reached")

    @property
    def is_on(self) -> bool:
        return bool((self.windows.get(self._window_key) or {}).get("exceeded"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        window = self.windows.get(self._window_key) or {}
        return {
            "used": window.get("used"),
            "cap": window.get("cap"),
            "percent": window.get("percent"),
            "remaining": window.get("remaining"),
            "reset_at": window.get("reset_at").isoformat()
            if window.get("reset_at")
            else None,
        }


class WeeklyLimitReachedBinarySensor(_WindowLimitBinarySensor):
    """On when the weekly rolling cap is reached."""

    _attr_translation_key = "weekly_limit_reached"
    _attr_icon = "mdi:calendar-alert"
    _window_key = "week"


class FiveHourLimitReachedBinarySensor(_WindowLimitBinarySensor):
    """On when the five-hour rolling cap is reached."""

    _attr_translation_key = "five_hour_limit_reached"
    _attr_icon = "mdi:clock-alert"
    _window_key = "five_hour"
