"""Unit tests for the Command Code provider (payloads, math, registry)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.ai_sub.api import UnknownProviderError
from custom_components.ai_sub.providers import (
    available_providers,
    build_provider,
    get_provider_class,
)
from custom_components.ai_sub.providers.base import Account, DailyCache
from custom_components.ai_sub.providers.commandcode import (
    CommandCodeProvider,
    build_snapshot,
    parse_credits,
    parse_subscription,
    parse_summary,
    parse_whoami,
    parse_window,
    plan_credits,
    plan_name,
)

NOW = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)


def test_registry_exposes_commandcode_only() -> None:
    assert available_providers() == {"commandcode": "Command Code"}
    provider = build_provider(object(), "commandcode", {"api_key": "k"})
    assert isinstance(provider, CommandCodeProvider)
    assert provider.credential("api_key") == "k"
    assert provider.credential("missing") is None
    with pytest.raises(UnknownProviderError):
        get_provider_class("nope")


def test_plan_tables_resolve_prefixes() -> None:
    assert plan_credits("individual-pro-v1") == 80.0
    assert plan_credits("individual-pro-v2") == 30.0
    assert plan_credits("individual-max-20x") == 300.0
    assert plan_credits(None) is None
    assert plan_name("individual-goat") == "GOAT"
    assert plan_name("custom-plan") == "custom-plan"
    assert plan_name("") is None


def test_parse_whoami_prefers_organisation_scope() -> None:
    payload = {
        "user": {"id": "u1", "userName": "letruxux", "email": "a@b.c"},
        "org": {"id": "o1", "login": "acme"},
    }
    account = parse_whoami(payload)
    assert account is not None
    assert account["login"] == "acme"
    assert account["scope_key"] == "org:o1"
    assert account["org_id"] == "o1"

    user_only = parse_whoami({"user": {"id": 7, "email": "a@b.c"}})
    assert user_only is not None
    assert user_only["scope_key"] == "user:7"
    assert user_only["login"] == "a@b.c"
    assert parse_whoami({"success": False}) is None


def test_parse_credits_accepts_wrapped_payload() -> None:
    parsed = parse_credits(
        {
            "success": True,
            "data": {
                "monthlyCredits": "50.5",
                "purchasedCredits": 10,
                "freeCredits": 1.5,
                "belowThreshold": True,
                "creditThreshold": 5,
            },
        }
    )
    assert parsed == {
        "monthly_remaining": 50.5,
        "purchased_remaining": 10.0,
        "free_remaining": 1.5,
        "total_remaining": 62.0,
        "below_threshold": True,
        "threshold_usd": 5.0,
    }
    assert parse_credits({"data": {}}) is None


def test_parse_subscription_handles_list_and_object() -> None:
    subscription = {
        "planId": "individual-pro-v1",
        "status": "active",
        "currentPeriodStart": "2026-01-01T00:00:00Z",
        "currentPeriodEnd": "2026-02-01T00:00:00Z",
        "cancelAtPeriodEnd": False,
    }
    parsed = parse_subscription({"success": True, "data": [subscription]})
    assert parsed is not None
    assert parsed["plan_id"] == "individual-pro-v1"
    assert parsed["period_end"] == datetime(2026, 2, 1, tzinfo=UTC)
    assert parsed["period_start_raw"] == "2026-01-01T00:00:00Z"
    assert parse_subscription({"data": {}}) is None


def test_parse_summary_and_windows() -> None:
    summary = parse_summary(
        {
            "data": {
                "totalCost": 12.5,
                "totalCount": 40,
                "totalTokens": 1000,
                "totalTokensIn": 700,
                "totalTokensOut": 300,
                "successRate": 99.1,
            }
        }
    )
    assert summary is not None
    assert summary["total_cost"] == 12.5
    assert summary["total_tokens_out"] == 300.0
    assert parse_summary({"data": {}}) is None

    window = parse_window(
        {"used": 25, "cap": 50, "resetAt": "2026-01-21T00:00:00Z"},
        "week",
        NOW,
    )
    assert window is not None
    assert window["percent"] == 50.0
    assert window["remaining"] == 25.0
    assert window["days_left"] == 0.5
    assert window["exceeded"] is False
    assert window["label"] == "Weekly"
    assert parse_window({"used": 1, "cap": 0}, "week", NOW) is None


def test_build_snapshot_normalizes_plan_budget() -> None:
    snapshot = build_snapshot(
        credits_payload={
            "monthlyCredits": 50,
            "purchasedCredits": 5,
            "freeCredits": 0,
            "windowLimits": {
                "fiveHour": {"used": 5, "cap": 10, "resetAt": "2026-01-20T14:00:00Z"},
                "weekly": {"used": 40, "cap": 70, "resetAt": "2026-01-25T00:00:00Z"},
            },
        },
        subscription_payload={
            "planId": "individual-pro-v1",
            "status": "active",
            "currentPeriodStart": "2026-01-10T00:00:00Z",
            "currentPeriodEnd": "2026-02-09T00:00:00Z",
        },
        summary_payload={"totalCost": 33, "totalCount": 10},
        now=NOW,
    )
    budget = snapshot["budget"]
    # Grant 80, monthly left 50 -> 30 used of the plan allowance.
    assert budget["used"] == 30.0
    assert budget["max"] == 80.0
    assert budget["percent"] == 37.5
    assert budget["remaining"] == 55.0
    assert budget["total_spent"] == 33.0
    assert budget["plan_name"] == "Pro"
    assert budget["currency"] == "USD"
    assert budget["days_left"] == 19.5
    assert budget["days_elapsed"] == 10.5
    # 2.86/day actual against the 2.82/day monthly pace: essentially on pace.
    assert budget["pace_status"] == "on"
    assert set(snapshot["windows"]) == {"five_hour", "week"}
    assert snapshot["summary"]["total_cost"] == 33.0


def test_build_snapshot_derives_maximum_without_a_known_plan() -> None:
    snapshot = build_snapshot(
        credits_payload={"monthlyCredits": 4, "purchasedCredits": 1, "freeCredits": 0},
        subscription_payload={"planId": "mystery-plan"},
        summary_payload={"totalCost": 20},
        now=NOW,
    )
    budget = snapshot["budget"]
    assert budget["max"] == 25.0
    assert budget["used"] == 20.0
    assert budget["percent"] == 80.0
    assert snapshot["windows"] == {}
    assert budget["plan_name"] == "mystery-plan"


def test_account_unique_id_and_cache() -> None:
    account = Account(login="acme", scope_key="org:o1")
    assert account.unique_id("commandcode") == "commandcode:org:o1"
    assert account.as_dict() == {"login": "acme", "scope_key": "org:o1"}

    cache = DailyCache()
    assert cache.usable is False
    cache.boundaries = [NOW, NOW + timedelta(days=1)]
    cache.totals = [1.0, None]
    assert cache.usable is True
    cache.clear()
    assert cache.usable is False
    assert cache.day is None
