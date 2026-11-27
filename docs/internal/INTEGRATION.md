# Integration notes

## Module map

| Module | Responsibility |
|--------|----------------|
| `__init__.py` | Build the coordinator, first refresh, forward `sensor` and `binary_sensor`, unload, reload on options change |
| `api.py` | `ProviderError` hierarchy and `async_get_json` (20 s timeout, 401/403 → auth error, other non-200 → API error) |
| `calc.py` | `number`, `parse_timestamp`, `api_param`, `days_until`, `days_since`, `percent`, `pace_status`, `day_boundaries`, `build_daily_series`, `empty_daily_series` |
| `providers/base.py` | `BaseProvider`, `ConfigField`, `Account`, `DailyCache`, snapshot schema documentation |
| `providers/commandcode.py` | HTTP client, payload parsers, plan table, normalized snapshot and daily backfill |
| `coordinator.py` | `AiSubCoordinator`: fetch loop, account cache, error mapping, snapshot envelope |
| `entity.py` | `AiSubEntity`: unique id, device info, `snapshot`/`budget`/`windows` accessors |
| `sensor.py` / `binary_sensor.py` | Entity definitions, translation keys, attributes |
| `config_flow.py` | Provider picker → credentials → entry; reauth; options |
| `diagnostics.py` | Redacted config entry, provider metadata, snapshot |

## Lifecycle

```text
config flow
  async_step_user        -> {"provider": "commandcode"}
  async_step_credentials -> provider.async_validate() -> Account
                            unique_id = "<provider_id>:<scope_key>"
                            entry.data = {"provider", ...credentials}

setup
  AiSubCoordinator(...)
    build_provider(...)          registry lookup, one provider instance
    async_config_entry_first_refresh()
      account is None            -> provider.async_validate()
      provider.async_fetch()     -> normalized snapshot
  runtime_data: hass.data[DOMAIN][entry_id] = coordinator
  platforms: sensor, binary_sensor
  update listener -> reload on options change

refresh (every 10 min by default)
  provider.async_fetch(account)  -> snapshot (cached daily history reused)
  envelope: provider, account, generated_at, budget, windows, subscription,
            summary, daily
```

The account is resolved once per coordinator and cached; only the fetch is
repeated. A 401/403 inside `async_fetch` also raises the auth error, so a key
revoked after startup still starts a reauth flow.

## Error mapping

| Raised by provider | Coordinator | Home Assistant behaviour |
|--------------------|-------------|--------------------------|
| `ProviderAuthError` | `ConfigEntryAuthFailed` | Warning, entry unloaded, reauth flow started |
| `ProviderConnectionError` | `UpdateFailed` | Retry on the next interval, entities keep the last state / go unavailable |
| `ProviderApiError` | `UpdateFailed` | Same as above, status and URL in the log |
| `UnknownProviderError` (registry) | `ConfigEntryError` during setup | Entry stops with a fatal setup error |

Config flow maps `ProviderAuthError` to `invalid_auth`, connection/API errors to
`cannot_connect`, anything else to `unknown`.

## Snapshot → entities

All entities read `coordinator.data`; `AiSubEntity` exposes `snapshot`,
`budget` and `windows`.

| Entity | Reads |
|--------|-------|
| `usage` | `budget.percent` |
| `max_usage` | `budget.max` |
| `remaining_balance` | `budget.remaining` |
| `suggested_pace` | `budget.suggested_daily_pace` (+ `pace_status`) |
| `spent` | `budget.total_spent` falling back to `budget.used` |
| `daily_usage` | `daily.today`, attributes from `daily.*` |
| `weekly_usage` / `five_hour_usage` | `windows.<key>.percent` |
| `weekly_max` / `five_hour_max` | `windows.<key>.cap` |
| `plan` | `budget.plan_name`, `subscription.*` |
| `period_end` | `subscription.period_end` (timezone-aware) |
| `limit_reached` | any `windows.*.exceeded` |
| `*_limit_reached` | `windows.<key>.exceeded` |

Money sensors read their unit from `budget.currency` (falling back to `USD`), so
a provider that reports EUR needs no sensor change.

## Daily backfill

The provider reconstructs a per-day series from a **cumulative-since** usage
endpoint:

1. `day_boundaries(period_start, now, tz)` returns the period start followed by
   local midnights, ending at today's local midnight. Capped at 45 entries.
2. One request per boundary asks "usage since `<boundary>`". The difference
   between adjacent totals is that day's spend; the last total is today.
3. The final day is reconciled so the cumulative series ends exactly at
   `budget.used`, which absorbs rounding and the plan-vs-total-cost distinction.
4. The ideal pace is a straight line from `(period_start, 0)` to
   `(period_end, max)`.

Requests are limited to four concurrent calls and retried once. Backfill is
skipped when `daily.source` would be `unavailable` (no period start).

`DailyCache` memoizes `day`, `period_end`, `boundaries` and `totals`. While the
local day and billing period do not change, only the last total is recomputed
from the cheap "since period start" summary; past days never change. The cache
lives on the coordinator and is rebuilt after a reload or restart.

## Unique IDs and device info

- Config entry: `"<provider_id>:<scope_key>"`, for example
  `commandcode:org:abc123`. `scope_key` is the provider's stable billing scope
  (organisation id when present, user id otherwise).
- Entity: `"<provider_id>:<scope_key>_<key>"`.
- Device: `identifiers={(DOMAIN, "<provider_id>:<scope_key>")}`, name = account
  login, manufacturer = provider name, model = "AI subscription",
  `entry_type=service`, `configuration_url` = provider usage page.

Renaming a device in Home Assistant changes entity IDs but not unique IDs, so
history survives.

## Options and reload

`AiSubOptionsFlow` writes `scan_interval` (60–3600 s). The update listener calls
`async_reload`, which recreates the coordinator (and therefore the `DailyCache`,
so the next poll backfills again). The entry ID and registry entries are kept.

## Tests

- `tests/test_calc.py` — math/time helpers, day boundaries, series differencing,
  reconciliation, unavailable series.
- `tests/test_commandcode.py` — registry, plan table, every parser, snapshot
  maths, `Account`/`DailyCache`.
- `tests/test_init.py` — real HA setup with a mocked aiohttp session: entity
  values, unload, 401 → reauth, config flow create/error paths.
- `tests/test_translations.py` � `strings.json` mirrors `translations/en.json`,
  every entity translation key is declared, every provider credential field has
  a label.

To debug a snapshot without Home Assistant, import the pure modules and call
`build_snapshot(credits_payload=..., subscription_payload=..., summary_payload=...)`;
it takes no session and accepts a fixed `now`.
