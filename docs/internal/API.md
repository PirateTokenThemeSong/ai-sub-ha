# Command Code API notes

Provider id `commandcode`, module `providers/commandcode.py`.

Base URL `https://api.commandcode.ai` (overridable per entry through the advanced
**API base URL** field). Authentication is `Authorization: Bearer <api key>` on
every call, plus `Accept: application/json`. Requests time out after 20 seconds.

## Endpoints

| Call | Path | Params | Purpose |
|------|------|--------|---------|
| `whoami` | `/alpha/whoami` | `limits=1` | User/organisation identity and billing scope |
| `credits` | `/alpha/billing/credits` | `orgId` (when the account has an org) | Credit balances and rolling window limits |
| `subscription` | `/alpha/billing/subscriptions` | `orgId` | Active plan and billing period |
| `usage_summary` | `/alpha/usage/summary` | `orgId`, `since` | Aggregate usage from `since` to now |

`orgId` is taken from the whoami organisation. Without an organisation the
account is scoped to the user and the parameter is omitted.

## Payloads

### whoami

```json
{
  "user": {"id": "u_…", "userName": "acme", "name": "…", "email": "…"},
  "org": {"id": "o_…", "login": "acme-org"}
}
```

The login prefers `org.login`, then `user.userName`, `user.name`, `user.email`.
The scope key is `org:<orgId>` when an organisation exists, otherwise
`user:<userId>` (or the lowercased login).

### billing/credits

```json
{
  "success": true,
  "data": {
    "credits": {"monthlyCredits": 50, "purchasedCredits": 5, "freeCredits": 0},
    "belowThreshold": false,
    "creditThreshold": 10,
    "windowLimits": {
      "fiveHour": {"used": 5, "cap": 10, "resetAt": "2026-01-20T14:00:00Z"},
      "weekly": {"used": 40, "cap": 70, "resetAt": "2026-01-25T00:00:00Z", "exceeded": false}
    }
  }
}
```

- The `credits` object may also be the response root; `_unwrap` handles the
  `{success, data}` envelope.
- `windowLimits` is read from the **unwrapped** payload, not from `credits`.
  Missing windows are simply absent from the snapshot.
- Credits may be serialized as strings; `number()` coerces them.
- `total_remaining` (snapshot `budget.remaining` / `total_remaining`) is the sum
  of monthly, purchased and free credit, and only computed when all three are
  present.

### billing/subscriptions

```json
{
  "success": true,
  "data": {
    "planId": "individual-pro-v1",
    "status": "active",
    "currentPeriodStart": "2026-01-01T00:00:00Z",
    "currentPeriodEnd": "2026-02-01T00:00:00Z",
    "cancelAtPeriodEnd": false
  }
}
```

`data` may be a list; the first object is used. An empty object (no plan, no
status, no period end) means "no subscription" and yields an empty snapshot
block — the entry still loads.

### usage/summary

```json
{
  "success": true,
  "data": {
    "totalCost": 12.5,
    "totalCount": 40,
    "totalTokens": 1000,
    "totalTokensIn": 700,
    "totalTokensOut": 300,
    "successRate": 99.1,
    "periodStart": "2026-01-01T00:00:00Z",
    "periodBasis": "billing_period"
  }
}
```

`totalCost` is cumulative from `since`. The daily series is built by calling this
endpoint once per day boundary in the billing period (max 45, four in parallel,
one retry) and differencing the totals.

**`since` formatting matters:** the endpoint rejects some ISO forms. The raw
`currentPeriodStart` string is therefore reused verbatim for the first request,
and generated boundaries are formatted as `YYYY-MM-DDTHH:MM:SS.mmmZ` by
`calc.api_param`. Do not introduce `+00:00` here without testing.

## Plan table and budgets

The API reports balances, not the plan's included allowance. The module keeps a
`planId -> monthly credits` table (mirroring the official CLI):

| planId | Credits | Display name |
|--------|---------|--------------|
| `individual-go`, `individual-go-v1` | 10 | Go |
| `individual-goat` | 70 | GOAT |
| `individual-pro` | 30 | Pro |
| `individual-pro-v1` | 80 | Pro |
| `individual-provider` | 15 | Provider |
| `individual-max`, `individual-max-10x` | 150 | Max 10x |
| `individual-ultra`, `individual-max-20x` | 300 | Max 20x |
| `teams-pro` | 40 | Team Pro |

Lookup is exact first, then longest known prefix, so `individual-pro-v2` resolves
through `individual-pro`. An unknown plan has no grant: the snapshot derives
`max` from `totalCost + remaining` when possible, otherwise leaves `used`/`max`
unset and only reports balances.

Derived values:

- `used = grant - monthlyCredits` (plan consumption). The usage summary's
  `totalCost` is kept as `budget.total_spent`, because it can include purchased
  and free credit.
- `percent = used / max`, clamped to 0–100 and rounded to two decimals.
- `days_left` from `currentPeriodEnd`, `days_elapsed` from `currentPeriodStart`.
- `current_daily_average = used / max(elapsed_days, 1h)`.
- `suggested_daily_pace = min(monthly remaining / days left, weekly headroom per
  day, five-hour headroom per day)`; window headroom uses
  `remaining / max(days_left, 1h)`.
- `pace_status`: `under` ≤ 0.95 × pace, `on` ≤ 1.05 × pace, else `over`.

## Quirks collected while writing this

- Numbers occasionally arrive as strings; booleans are not numbers.
- `resetAt` may be ISO with `Z` or epoch milliseconds; `parse_timestamp` handles
  both.
- 401 **and** 403 mean "bad credentials" and trigger reauth.
- A failed usage summary is non-fatal: credits and subscription still produce a
  snapshot, the daily series degrades to `source: unavailable`.
- The API is labelled alpha; parsing is defensive and tolerates direct or
  `{success, data}` shapes.
