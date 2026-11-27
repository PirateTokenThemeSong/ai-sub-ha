"""Diagnostics support for AI Sub (credentials redacted)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_SECRET_WORDS = ("key", "token", "secret", "password")


def _is_secret(field_key: str, secret: bool) -> bool:
    return secret or any(word in field_key.lower() for word in _SECRET_WORDS)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with every credential redacted."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    provider = coordinator.provider
    secrets = {
        field.key
        for field in provider.config_fields
        if _is_secret(field.key, field.secret)
    }

    data = dict(entry.data)
    for key in list(data):
        if key in secrets or _is_secret(key, False):
            data[key] = "**REDACTED**"

    return {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": data,
            "options": dict(entry.options),
        },
        "provider": provider.as_dict(),
        "snapshot": _json_safe(coordinator.data),
    }
