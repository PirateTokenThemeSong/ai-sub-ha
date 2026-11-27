# Provider contract

A provider is the only vendor-specific part of the integration. It resolves an
account from stored credentials and returns one normalized snapshot. The
coordinator, the config flow and every entity work against that contract.

Command Code (`providers/commandcode.py`) is the reference implementation.

## `BaseProvider`

```python
class BaseProvider:
    provider_id: ClassVar[str]        # stable id stored in the config entry
    name: ClassVar[str]               # display name in the config flow
    documentation_url: ClassVar[str]  # used as the device configuration_url
    setup_hint: ClassVar[str]         # shown above the credentials form
    currency: ClassVar[str] = "USD"
    config_fields: ClassVar[tuple[ConfigField, ...]]
    timezone: str                     # Home Assistant timezone, injected

    def __init__(self, session, credentials, cache=None, timezone="UTC"): ...
    def credential(self, key: str) -> str | None: ...
    async def async_validate(self) -> Account: ...
    async def async_fetch(self, account: Account) -> dict[str, Any]: ...
```

`Account` carries the billing identity:

```python
@dataclass(slots=True)
class Account:
    login: str          # device name
    scope_key: str      # "org:<id>" / "user:<id>"; part of the unique id
    extra: dict         # provider-specific ids (org id, tenant, …)
```

`ConfigField` describes one credential field:

```python
ConfigField("api_key", secret=True)                      # required
ConfigField("base_url", required=False, default="https://…")
```

The config flow builds its form from this tuple, strips values, drops blanks and
redacts `secret=True` fields in diagnostics. Every field also needs a label in
`strings.json` under `config.step.credentials.data` (and `reauth_confirm`), using
`field.translation_key` (defaults to `field.key`).

`DailyCache` is coordinator-owned scratch space for expensive history backfills:
`day`, `period_end`, `boundaries`, `totals`, plus `usable` and `clear()`.

## Snapshot schema

`async_fetch` returns a plain dict (JSON-safe, `datetime` allowed). Everything is
optional, but a provider should always return `budget` and `windows`.

```python
{
  "budget": {
    "used": float, "max": float, "percent": float,
    "remaining": float,            # aggregate remaining (autonomy sensor)
    "currency": "USD",
    "plan_name": str, "plan_id": str,
    "days_left": float, "days_elapsed": float,
    "current_daily_average": float, "suggested_daily_pace": float,
    "pace_status": "under" | "on" | "over",
    # provider extras, e.g. monthly_remaining, purchased_remaining,
    # free_remaining, total_spent, monthly_grant
  },
  "windows": {
    "five_hour": {"label": "5-hour", "used": float, "cap": float,
                  "remaining": float, "percent": float,
                  "reset_at": datetime, "days_left": float,
                  "pace_per_day": float, "exceeded": bool},
    "week": {...},
  },
  "subscription": {"plan_id", "status", "period_start", "period_end",
                   "cancel_at_period_end"},
  "summary": {"total_cost", "total_count", "total_tokens", "total_tokens_in",
              "total_tokens_out", "success_rate"},
  "daily": {"today": float, "days": [{"date", "usd"}],
            "cumulative": [{"date", "usd"}], "pace": [{"date", "usd"}],
            "period_start", "period_end", "max_usd", "pace_per_day_usd",
            "source": "api" | "unavailable", "backfilled_at"},
}
```

The coordinator adds `provider`, `account` and `generated_at`. Entity keys are
fixed (`usage`, `max_usage`, …), so a provider only fills numbers; sensors,
attributes and translations stay unchanged.

`percent` is the share of the monthly allowance: `used` is plan consumption,
`max` is the plan grant. Extra credits are extra keys, never baked into `max`,
so the percentages stay comparable across plans.

## Adding a provider

1. **Create the module** `custom_components/ai_sub/providers/<vendor>.py`:

   ```python
   from ..api import ProviderApiError, async_get_json
   from ..calc import number, parse_timestamp
   from .base import Account, BaseProvider, ConfigField

   class ExampleProvider(BaseProvider):
       provider_id = "example"
       name = "Example AI"
       documentation_url = "https://example.com/usage"
       setup_hint = "Paste an API key from example.com/usage."
       config_fields = (ConfigField("api_key", secret=True),)

       def __init__(self, session, credentials, cache=None, timezone="UTC"):
           super().__init__(session, credentials, cache, timezone)
           self._token = self.credential("api_key") or ""

       async def async_validate(self) -> Account:
           payload = await self._get("/v1/me")
           login = payload.get("email")
           if not login:
               raise ProviderApiError(200, "/v1/me")
           return Account(login=login, scope_key=f"user:{payload['id']}")

       async def async_fetch(self, account: Account) -> dict:
           usage = await self._get("/v1/usage")
           return {
               "budget": {...},
               "windows": {...},
               "subscription": {...},
               "summary": {...},
               "daily": {...},
           }
   ```

2. **Register it** in `providers/__init__.py`:

   ```python
   PROVIDERS = {
       CommandCodeProvider.provider_id: CommandCodeProvider,
       ExampleProvider.provider_id: ExampleProvider,
   }
   ```

3. **Add UI strings** to `strings.json` *and* `translations/en.json`: one label
   per credential field. `name`, `setup_hint` and `documentation_url` come from
   the class, so no extra text is needed for the provider picker.

4. **Reuse `calc.py`** for numbers, timestamps, percentages, pace status and the
   daily series. Do not import Home Assistant in a provider: the unit tests load
   providers without it.

5. **Add tests** in `tests/test_<vendor>.py` for every parser and for the
   snapshot maths (fixed `now`, no session), plus a case in
   `test_registry_exposes_commandcode_only` (rename it to a generic registry test
   once there is more than one provider).

### Adding a rolling window

1. Add the key to the provider's `windows` dict (`"day"`, `"month"`, …) with the
   same fields as the existing ones.
2. Add `sensor.<key>_usage`, `sensor.<key>_max` and
   `binary_sensor.<key>_limit_reached` classes to the platform files, following
   the `_WindowUsageSensor` / `_WindowMaxSensor` / `_WindowLimitBinarySensor`
   subclasses that already exist.
3. Add the three names under `entity.sensor` / `entity.binary_sensor` in both
   string files.

`limit_reached` picks up new windows automatically.

### Adding a currency

Set `budget.currency` to the ISO code the API reports. All monetary sensors
adopt it through `_MonetarySensor.native_unit_of_measurement`; no sensor change
is needed. The daily series attribute names keep the `usd` key for stability —
treat it as "amount in the account currency".

## What stays out of a provider

- Home Assistant imports, config flow steps, entity keys, translations.
- Retry/backoff logic: the coordinator owns polling, the provider owns one
  attempt per call.
- Secrets handling: never log credentials; diagnostics redacts `secret` fields
  and any key containing `key`, `token`, `secret` or `password`.
