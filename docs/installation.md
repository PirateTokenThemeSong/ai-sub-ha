# Installation

## Before you start

You need:

- Home Assistant **2024.11** or newer.
- An **AI subscription account** with an API key. For Command Code, create or
  copy the key at [commandcode.ai/usage](https://commandcode.ai/usage); the key
  used by the `command-code` CLI is the same key.
- No extra container, add-on or YAML. The integration is cloud polling only.

The API key is read-only in practice: the integration calls billing, usage and
whoami endpoints and never sends prompts or changes a subscription.

## Install the integration

### HACS

1. In HACS, open **⋮ → Custom repositories**.
2. Add `https://github.com/PirateTokenThemeSong/ai-sub-ha` as an **Integration**.
3. Install **AI Sub** from HACS and restart Home Assistant.

### Manual installation

1. Copy the `custom_components/ai_sub` folder from this repository into your
   Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

The integration has no Python requirements beyond Home Assistant itself.

### Updating

Replace the `custom_components/ai_sub` folder (or update through HACS) and
restart Home Assistant. Config entries, unique IDs and history are preserved.

## Add an account

1. Open **Settings → Devices & services**.
2. Choose **Add integration** and search for **AI Sub**.
3. Pick the provider — **Command Code** is the only one available today.
4. Paste the API key.

   | Field | Notes |
   |-------|-------|
   | API key | Required. Stored in the config entry, redacted in diagnostics |
   | API base URL | Advanced. Defaults to `https://api.commandcode.ai`; change it only for a proxy or a test environment |

The integration calls the provider's identity endpoint, names the account after
the login it reports and creates the device with its sensors. A rejected key
stays on the form with an error instead of creating a broken entry.

## Several accounts or providers

Add the integration again for each account. Entries are unique per provider and
provider account, so two Command Code organisations — or one Command Code and,
later, another provider — coexist as separate devices. Entity IDs are derived
from the account login; if two accounts report the same login, Home Assistant
appends a numeric suffix.

## Coming from a local `commandcode` folder

An earlier bench version of this integration lived in
`custom_components/commandcode` with the domain `commandcode`. The generic
integration uses the domain `ai_sub`, so it is **not** a drop-in replacement:

1. Remove the old `custom_components/commandcode` folder and delete its config
   entry (**Settings → Devices & services → Command Code → Delete**). Leaving
   both installed gives two devices polling the same account.
2. Install AI Sub and add the account again with the same API key.
3. Entity IDs change (`sensor.<account>_usage` instead of whatever the old
   device produced). Update dashboards and automations that referenced them;
   long-term statistics start fresh per entity.

The sensors and their meaning are unchanged.

## Remove the integration

Delete the config entry, then remove `custom_components/ai_sub` if you no longer
want it. Removing the entry stops polling immediately; the entity registry
entries are cleaned up when the entry is deleted.
