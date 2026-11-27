# Troubleshooting

Most problems show up in one of two places: the integration log lines and the
downloaded diagnostics.

## Where to look

- **Logs**: search for `custom_components.ai_sub`. The coordinator logs failed
  refreshes, the provider logs a failed daily backfill at debug level.
- **Diagnostics**: config entry → **⋮ → Download diagnostics**. It contains the
  config entry (API key redacted), the provider id and the last normalized
  snapshot, including the daily series source.
- **Entities**: `sensor.<account>_plan` shows the subscription status and period
  dates; the `*_usage` attributes show caps and reset times.

## The API key is rejected

You see a **Reconfigure** notification and the entry asks to reconnect.

- The key was rotated, revoked or belongs to a deleted account. Create a new key
  and paste it in the reconnect dialog.
- The reconnect flow refuses a key for a **different** account (`wrong_account`).
  Keys are tied to the account the entry was created for; add a new integration
  entry for a different account.
- A key with leading/trailing whitespace is fine — values are stripped.

## "Could not reach the provider" / `cannot_connect`

- The integration could not open an HTTPS request to the billing API.
- Check that Home Assistant has outbound HTTPS access. DNS or firewall problems
  on the Home Assistant host affect every cloud integration at once.
- If you changed **API base URL**, verify it is the API host and not the web
  dashboard: `https://api.commandcode.ai`, without a trailing path.
- A `5xx` for a single poll marks the entities unavailable but keeps the entry
  loaded; the next poll retries.

## Entities are `unknown`

`unknown` means the snapshot has no value for that field, not that the
integration failed:

- **`weekly_usage` / `five_hour_usage`** — the account has no rolling windows
  (for example an inactive subscription), or the API stopped returning
  `windowLimits`.
- **`usage` / `max_usage`** — the plan is not in the provider's plan table, and
  the API does not report enough balance to derive the allowance. `remaining`
  and `spent` still work. Add the plan id to
  `PLAN_MONTHLY_CREDITS` in `providers/commandcode.py`.
- **`daily_usage`** — see below.
- **`period_end`** — the account has no active billing period.

## Daily usage is empty

The daily series is built from the usage summary endpoint. `source` in the
`daily_usage` attributes tells you why it is empty:

| `source` | Meaning |
|----------|---------|
| `api` | Series built normally |
| `unavailable` | The period start is missing, or every backfill request failed; check the debug log for `Daily usage backfill failed` |

The backfill stops at 45 days and needs the billing period start from the
subscription endpoint. Without an active subscription there is no period, so
there is no series.

## States stay `unavailable` after a reload

When a config entry is unloaded — including during a Home Assistant restart — the
entity registry entries survive, so Home Assistant marks their states
`unavailable` instead of removing them. They come back on the next successful
poll. `unavailable` while running means the last poll failed: look for
`UpdateFailed` or an auth error in the log.

## Duplicate devices or double polling

Two entries for the same account (for example the old `commandcode` folder plus
AI Sub) both poll and both create entities. Delete the entry you do not want.
Adding the same account again is refused by the config flow
(`already_configured`).

## Timezone and "today"

Daily buckets use Home Assistant's configured timezone. A day boundary is local
midnight, so changing the Home Assistant timezone shifts which usage counts as
"today". The monthly and rolling figures are provider-side and unaffected.

## Nothing changes after an options change

Options changes reload the entry, which re-poll immediately. If the new value
does not stick, check that the interval is inside 60–3600 seconds; the form
rejects anything outside that range.

## Before opening an issue

Include:

- Home Assistant version and integration version (**Settings → Devices & services
  → AI Sub** shows it).
- The provider id and plan shown by `sensor.<account>_plan`.
- Log lines for `custom_components.ai_sub` covering one failed refresh.
- The diagnostics file with account names and spend trimmed.

Never paste the API key, the `Authorization` header or a raw billing response.
