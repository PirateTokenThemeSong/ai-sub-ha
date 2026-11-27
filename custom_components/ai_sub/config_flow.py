"""Config and options flow for AI Sub."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ProviderApiError,
    ProviderAuthError,
    ProviderConnectionError,
)
from .const import (
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    NAME,
)
from .providers import (
    DEFAULT_PROVIDER_ID,
    Account,
    BaseProvider,
    DailyCache,
    available_providers,
    get_provider_class,
)


async def _validate(
    hass: HomeAssistant,
    provider: type[BaseProvider],
    user_input: dict[str, Any],
) -> Account:
    """Resolve the account behind the submitted credentials."""
    instance = provider(
        async_get_clientsession(hass),
        user_input,
        DailyCache(),
        timezone=hass.config.time_zone or "UTC",
    )
    return await instance.async_validate()


def _credentials_schema(provider: type[BaseProvider]) -> vol.Schema:
    """Build a voluptuous schema from a provider's config fields."""
    fields: dict[Any, Any] = {}
    for field in provider.config_fields:
        if field.required:
            fields[vol.Required(field.key)] = str
        else:
            fields[vol.Optional(field.key, default=field.default or "")] = str
    return vol.Schema(fields)


def _clean(user_input: dict[str, Any]) -> dict[str, str]:
    """Strip submitted values and drop blanks."""
    cleaned: dict[str, str] = {}
    for key, value in user_input.items():
        if isinstance(value, str):
            value = value.strip()
        if value:
            cleaned[key] = value
    return cleaned


class AiSubConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick a provider, then ask for its credentials."""

    VERSION = 1

    def __init__(self) -> None:
        self._provider_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the subscription provider to connect."""
        providers = available_providers()
        errors: dict[str, str] = {}
        if user_input is not None:
            provider_id = user_input.get(CONF_PROVIDER)
            if provider_id in providers:
                self._provider_id = provider_id
                return await self.async_step_credentials()
            errors["base"] = "unknown"

        default = self._provider_id or next(iter(providers), DEFAULT_PROVIDER_ID)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_PROVIDER, default=default): vol.In(providers)}
            ),
            errors=errors,
            description_placeholders={"name": NAME},
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the credentials of the selected provider."""
        if self._provider_id is None:
            # The flow was restored without its in-memory provider choice.
            return await self.async_step_user()

        provider = get_provider_class(self._provider_id)
        errors: dict[str, str] = {}
        if user_input is not None:
            credentials = _clean(user_input)
            try:
                account = await _validate(self.hass, provider, credentials)
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except (ProviderConnectionError, ProviderApiError):
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(account.unique_id(provider.provider_id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{provider.name} ({account.login})",
                    data={CONF_PROVIDER: provider.provider_id, **credentials},
                )

        return self.async_show_form(
            step_id="credentials",
            data_schema=_credentials_schema(provider),
            errors=errors,
            description_placeholders={
                "provider": provider.name,
                "hint": provider.setup_hint,
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after the provider rejected the key."""
        self._provider_id = entry_data.get(CONF_PROVIDER) or DEFAULT_PROVIDER_ID
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh key for the same account."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_successful")
        provider = get_provider_class(
            entry.data.get(CONF_PROVIDER) or DEFAULT_PROVIDER_ID
        )
        if user_input is not None:
            credentials = _clean(user_input)
            try:
                account = await _validate(self.hass, provider, credentials)
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except (ProviderConnectionError, ProviderApiError):
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                if account.unique_id(provider.provider_id) != entry.unique_id:
                    errors["base"] = "wrong_account"
                else:
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, **credentials}
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(provider),
            errors=errors,
            description_placeholders={"provider": provider.name},
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AiSubOptionsFlow()


class AiSubOptionsFlow(OptionsFlow):
    """Tune the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = int(
            self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                        int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    )
                }
            ),
        )
