"""Shared entity base for the AI Sub integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AiSubCoordinator


class AiSubEntity(CoordinatorEntity[AiSubCoordinator]):
    """Base entity bound to one provider account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AiSubCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.account_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.account_id)},
            name=coordinator.account_name,
            manufacturer=coordinator.provider_name,
            model="AI subscription",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.provider.documentation_url or None,
        )

    @property
    def snapshot(self) -> dict[str, Any]:
        """Return the latest normalized snapshot."""
        return self.coordinator.data or {}

    @property
    def budget(self) -> dict[str, Any]:
        """Return the monthly allowance block of the snapshot."""
        return self.snapshot.get("budget") or {}

    @property
    def windows(self) -> dict[str, Any]:
        """Return the rolling-window block of the snapshot."""
        return self.snapshot.get("windows") or {}
