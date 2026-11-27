# Using the integration

Once an account is configured it appears as a normal Home Assistant device. All
entities belong to that device, are translated and are named after the account
login the provider reports.

## Entities

Entity IDs follow the device name, so an account reported as `acme` produces
`sensor.acme_usage`, `binary_sensor.acme_limit_reached` and so on. The exact IDs
depend on the login and on what else is in your registry.

| Entity | Unit | What it tells you |
|--------|------|-------------------|
| `sensor.<account>_usage` | % | Share of the monthly allowance already used |
| `sensor.<account>_max_usage` | currency | The monthly allowance for the plan |
| `sensor.<account>_remaining_balance` | currency | Everything left: plan, purchased and free credit |
| `sensor.<account>_suggested_pace` | currency/day | Daily spend that keeps the account on pace |
| `sensor.<account>_daily_usage` | currency | Spend today; carries the per-day series as attributes |
| `sensor.<account>_weekly_usage` | % | Weekly rolling window |
| `sensor.<account>_five_hour_usage` | % | Five-hour rolling window |
| `sensor.<account>_spent` | currency | Spend reported by the usage summary |
| `sensor.<account>_weekly_max` | currency | Weekly window cap |
| `sensor.<account>_five_hour_max` | currency | Five-hour window cap |
| `sensor.<account>_plan` | — | Plan name, subscription status, period dates |
| `sensor.<account>_period_end` | timestamp | Renewal instant, also a timestamp device class |
| `binary_sensor.<account>_limit_reached` | — | On when **any** window is at/over its cap |
| `binary_sensor.<account>_weekly_limit_reached` | — | On when the weekly window is maxed out |
| `binary_sensor.<account>_five_hour_limit_reached` | — | On when the five-hour window is maxed out |

Sensors marked as diagnostic in the UI (`spent`, the two `*_max`, `plan` and
`period_end`) are supporting data. The headline entities are `usage`,
`remaining_balance`, `suggested_pace`, `daily_usage` and the three binary
sensors.

### Attributes worth knowing

- **`suggested_pace`** carries `status` (`under`, `on`, `over`),
  `current_daily_average`, `monthly_pace`, `weekly_pace`, `five_hour_pace`,
  `days_left` and the per-source remaining balances.
- **`daily_usage`** carries `days` (date + amount), `cumulative`, `pace` (the
  ideal straight line from 0 to the allowance), `pace_per_day_usd`,
  `period_start`, `period_end`, `max_usd` and `source`.
- **`weekly_usage` / `five_hour_usage`** carry `used`, `cap`, `remaining`,
  `reset_at`, `days_left`, `pace_per_day` and `exceeded`.
- **`limit_reached`** carries one entry per window with its percent, used, cap
  and reset time.

If the provider does not expose a rolling window, its sensors simply stay
`unknown`; the monthly ones keep working.

## Dashboard chart

The daily series is exposed as attributes, so a chart card can read it without a
template sensor:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: AI spend this period
graph_span: 30d
span:
  end: day
series:
  - entity: sensor.<account>_daily_usage
    name: Per day
    type: column
    data_generator: |
      return entity.attributes.days.map((day) => [new Date(day.date), day.usd]);
  - entity: sensor.<account>_daily_usage
    name: Cumulative
    type: area
    opacity: 0.2
    data_generator: |
      return entity.attributes.cumulative.map((day) => [new Date(day.date), day.usd]);
  - entity: sensor.<account>_daily_usage
    name: Pace
    type: line
    curve: straight
    data_generator: |
      return entity.attributes.pace.map((day) => [new Date(day.date), day.usd]);
```

`apexcharts-card` is a HACS frontend card. A built-in alternative is a
statistics graph card on `sensor.<account>_usage`.

A compact glance card:

```yaml
type: glance
title: AI subscription
entities:
  - entity: sensor.<account>_usage
  - entity: sensor.<account>_remaining_balance
  - entity: sensor.<account>_suggested_pace
  - entity: binary_sensor.<account>_limit_reached
```

## Automations

The binary sensors are the intended triggers. They flip on while a window is at
its cap and back off after the reset.

```yaml
automation:
  - alias: Warn when the AI five-hour window is exhausted
    triggers:
      - trigger: state
        entity_id: binary_sensor.<account>_five_hour_limit_reached
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: AI subscription
          message: >-
            The five-hour window is used up. It resets at
            {{ state_attr('binary_sensor.<account>_five_hour_limit_reached', 'reset_at') }}.

  - alias: Warn when AI credit runs low
    triggers:
      - trigger: numeric_state
        entity_id: sensor.<account>_remaining_balance
        below: 10
    actions:
      - action: notify.mobile_app_phone
        data:
          title: AI subscription
          message: >-
            Only {{ states('sensor.<account>_remaining_balance') }} left on
            {{ states('sensor.<account>_plan') }}.

  - alias: Daily AI spend summary
    triggers:
      - trigger: time
        at: "21:00:00"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: >-
            Today: {{ states('sensor.<account>_daily_usage') }} ·
            {{ states('sensor.<account>_usage') }}% of the allowance ·
            pace {{ states('sensor.<account>_suggested_pace') }}/day.
```

Pace status is available as an attribute, so a template can distinguish "slightly
over" from "burning through the plan":

```jinja
{{ state_attr('sensor.<account>_suggested_pace', 'status') }}
```

## Polling

Data is polled every **600 seconds** (10 minutes) by default. Command Code
implements rolling windows and a billing balance, so more frequent polling buys
little and costs API calls. Change it in the integration options:

1. **Settings → Devices & services → AI Sub → Configure**.
2. Set the polling interval between **60** and **3600** seconds.

Polling is only one source of latency: the coordinator refreshes on start and
then on the interval. After changing the options the entry reloads immediately.

The daily history is backfilled once per local day; intraday refreshes only
recompute today's figure from the cached boundaries.

## Diagnostics

**Settings → Devices & services → AI Sub → ⋮ → Download diagnostics** returns the
config entry (credentials redacted), the provider metadata and the last snapshot.
It is the fastest way to see what the API returned without opening a terminal —
but it still contains account names and spend, so trim it before posting.
