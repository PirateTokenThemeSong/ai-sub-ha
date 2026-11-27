<p align="center">
  <img src="assets/icon.png" width="104" alt="AI Sub">
</p>

<h1 align="center">AI Sub</h1>

<p align="center">Your AI subscriptions, in Home Assistant.</p>

AI Sub turns the billing and rate-limit APIs of AI coding subscriptions into
regular Home Assistant sensors: how much of the monthly allowance is gone, how
much is left, what today cost, how close the five-hour and weekly windows are to
their cap, and when the plan renews. Command Code is the first provider; the
provider layer is pluggable, so more subscriptions can be added without touching
the coordinator or the entities.

## What it does

- **Monthly budget** — used, allowance, percentage and remaining balance for the
  current billing period, in the account currency.
- **Rolling windows** — five-hour and weekly usage against their caps, with the
  reset time and remaining headroom per day.
- **Daily spend** — a backfilled per-day series (today, per day, cumulative and
  the ideal pace) that works in a dashboard chart.
- **Pace guidance** — how much per day keeps the account on pace for renewal,
  and whether the current average is under, on or over that pace.
- **Limits as triggers** — binary sensors that flip when a window is maxed out,
  so automations can react before a session is wasted.
- **One entry per account** — add the integration again for a second account or
  provider; each account becomes its own device.

## Providers

| Provider | Status |
|----------|--------|
| Command Code (`commandcode`) | Available — the reference implementation |
| Others (OpenAI, Anthropic, Cursor, …) | Not yet — see [adding a provider](docs/internal/PROVIDERS.md) |

The config flow lists the providers this build ships; the selected provider is
stored on the config entry, and every entity reads one normalized snapshot, so a
new provider only adds a module and a registry line.

## Get started

1. Install the custom integration from this repository or HACS — see
   [Installation](docs/installation.md).
2. Add **AI Sub**, choose **Command Code** and paste an API key from
   [commandcode.ai/usage](https://commandcode.ai/usage) (the `command-code` CLI
   key works too).
3. The account appears as a device with its sensors and binary sensors.
4. Put the entities on a dashboard or wire the limit binary sensors into
   [automations](docs/usage.md#automations).

## Entities

Entity IDs follow the account login reported by the provider, for example
`sensor.<account>_usage`. All names are translated through the integration.

| Entity | Purpose |
|--------|---------|
| `sensor.<account>_usage` | Percentage of the monthly allowance consumed |
| `sensor.<account>_max_usage` | Monthly allowance in the account currency |
| `sensor.<account>_remaining_balance` | Everything left to spend |
| `sensor.<account>_suggested_pace` | Currency per day that stays on pace |
| `sensor.<account>_daily_usage` | Spend today, plus the daily history series |
| `sensor.<account>_weekly_usage` | Weekly rolling window, percent |
| `sensor.<account>_five_hour_usage` | Five-hour rolling window, percent |
| `sensor.<account>_spent` | Spend recorded by the usage summary |
| `sensor.<account>_weekly_max` / `..._five_hour_max` | Window caps |
| `sensor.<account>_plan` | Active plan and subscription status |
| `sensor.<account>_period_end` | Billing period renewal timestamp |
| `binary_sensor.<account>_limit_reached` | Any window at/over its cap |
| `binary_sensor.<account>_weekly_limit_reached` | Weekly window maxed out |
| `binary_sensor.<account>_five_hour_limit_reached` | Five-hour window maxed out |

## Documentation

- [Installation](docs/installation.md) — HACS, manual install and first setup
- [Using the integration](docs/usage.md) — entities, dashboard chart, automations
- [Troubleshooting](docs/troubleshooting.md) — auth, connectivity, empty sensors
- [Internal docs](docs/internal/README.md) — architecture, provider contract, API notes

## Status

Tested against Command Code's alpha billing API and Home Assistant 2025.1.
Command Code is the only shipped provider, and its API is still labelled alpha:
if a payload changes, the parsing helpers and their tests are the place to fix
it. Plan grants live in a table in the provider module, so an unknown plan still
reports what the API tells it, just without a percentage of the allowance.

This is an independent project, not affiliated with Command Code, OpenAI,
Anthropic or any other provider.

## License

MIT — see [LICENSE](LICENSE).
