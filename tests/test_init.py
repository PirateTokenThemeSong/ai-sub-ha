"""Integration-level tests: setup, entities, reauth and the config flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ai_sub.const import CONF_API_KEY, CONF_PROVIDER, DOMAIN

API = "https://api.commandcode.ai"
ENTRY_ID = "test_entry"


def _payloads() -> dict[str, object]:
    now = datetime.now(UTC).replace(microsecond=0)
    period_start = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    period_end = (now + timedelta(days=20)).isoformat().replace("+00:00", "Z")
    reset_at = (now + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    return {
        "whoami": {
            "user": {"id": "u1", "userName": "acme"},
            "org": {"id": "o1", "login": "acme"},
        },
        "credits": {
            "success": True,
            "data": {
                "monthlyCredits": 50,
                "purchasedCredits": 5,
                "freeCredits": 0,
                "windowLimits": {
                    "fiveHour": {"used": 5, "cap": 10, "resetAt": reset_at},
                    "weekly": {"used": 40, "cap": 70, "resetAt": reset_at},
                },
            },
        },
        "subscription": {
            "success": True,
            "data": {
                "planId": "individual-pro-v1",
                "status": "active",
                "currentPeriodStart": period_start,
                "currentPeriodEnd": period_end,
            },
        },
        "summary": {
            "success": True,
            "data": {"totalCost": 30, "totalCount": 12, "totalTokens": 4000},
        },
    }


def _register(
    aioclient_mock, payloads: dict[str, object], *, whoami_status: int = 200
) -> None:
    aioclient_mock.get(
        f"{API}/alpha/whoami",
        params={"limits": "1"},
        status=whoami_status,
        json=payloads["whoami"],
    )
    aioclient_mock.get(f"{API}/alpha/billing/credits", json=payloads["credits"])
    aioclient_mock.get(
        f"{API}/alpha/billing/subscriptions", json=payloads["subscription"]
    )
    aioclient_mock.get(f"{API}/alpha/usage/summary", json=payloads["summary"])


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Command Code (acme)",
        data={CONF_PROVIDER: "commandcode", CONF_API_KEY: "test-key"},
        unique_id="commandcode:org:o1",
        entry_id=ENTRY_ID,
    )


async def test_setup_entry_creates_entities(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A valid key loads the account and publishes every entity."""
    _register(aioclient_mock, _payloads())
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    usage = hass.states.get("sensor.acme_usage")
    assert usage is not None
    assert usage.state == "37.5"
    assert usage.attributes["used"] == 30.0
    assert hass.states.get("sensor.acme_remaining_balance").state == "55.0"
    assert hass.states.get("sensor.acme_plan").state == "Pro"
    assert hass.states.get("sensor.acme_weekly_usage").state == "57.14"
    assert hass.states.get("sensor.acme_daily_usage") is not None
    assert hass.states.get("binary_sensor.acme_limit_reached").state == "off"

    assert len(hass.states.async_entity_ids("sensor")) == 12
    assert len(hass.states.async_entity_ids("binary_sensor")) == 3

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    # The registry entries survive the unload, so their states become
    # unavailable instead of disappearing.
    assert hass.states.get("sensor.acme_usage").state == "unavailable"
    assert hass.states.get("binary_sensor.acme_limit_reached").state == "unavailable"


async def test_invalid_key_starts_reauth(hass: HomeAssistant, aioclient_mock) -> None:
    """A 401 on the first refresh asks the user to reconnect."""
    _register(aioclient_mock, _payloads(), whoami_status=401)
    entry = _entry()
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_user_config_flow(hass: HomeAssistant, aioclient_mock) -> None:
    """The flow picks a provider, validates the key and creates the entry."""
    _register(aioclient_mock, _payloads())

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVIDER: "commandcode"}
    )
    assert result["step_id"] == "credentials"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "test-key", "base_url": ""}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Command Code (acme)"
    assert result["data"] == {
        CONF_PROVIDER: "commandcode",
        CONF_API_KEY: "test-key",
    }
    assert result["result"].unique_id == "commandcode:org:o1"


async def test_config_flow_rejects_bad_key(hass: HomeAssistant, aioclient_mock) -> None:
    """A rejected key stays on the credentials form with an error."""
    _register(aioclient_mock, _payloads(), whoami_status=401)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVIDER: "commandcode"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "credentials"
    assert result["errors"]["base"] == "invalid_auth"
