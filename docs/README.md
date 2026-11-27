# AI Sub documentation

This is the user documentation for the AI Sub Home Assistant integration. It
covers installing the integration, reading the entities day to day, and fixing
the usual problems.

## Start here

| I want to… | Read |
|------------|------|
| Install the integration and connect an account | [Installation](installation.md) |
| Understand the entities and build a dashboard | [Using the integration](usage.md) |
| React to a limit or a low balance | [Automations](usage.md#automations) |
| Fix a problem | [Troubleshooting](troubleshooting.md) |

## What the system is made of

1. **A provider module** (`custom_components/ai_sub/providers/`) talks to one
   subscription vendor and normalizes its payloads.
2. **A coordinator** polls the provider and keeps one snapshot per account.
3. **Entities** read that snapshot: twelve sensors and three binary sensors.

Command Code is the only provider shipped today. The integration is built so a
new provider does not touch the coordinator or the entities; see
[the provider contract](internal/PROVIDERS.md).

## Supported providers

| Provider | Config value | Status |
|----------|--------------|--------|
| Command Code | `commandcode` | Available |
| Anything else | — | Not yet implemented |

## Getting help

- Read [Troubleshooting](troubleshooting.md) first, and download the integration
  diagnostics from the config entry.
- For a reproducible bug, open an issue on
  [GitHub](https://github.com/PirateTokenThemeSong/ai-sub-ha/issues) with the
  Home Assistant log lines for `custom_components.ai_sub`.
- Never paste an API key, a full diagnostics dump or a raw billing response
  into a public issue. Diagnostics redact credentials, but payloads carry
  account names and spend.

## For developers

Architecture, the provider contract and the vendor API notes are kept in
[internal documentation](internal/README.md).
