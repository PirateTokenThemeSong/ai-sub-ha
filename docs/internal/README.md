# Internal documentation

This directory is the technical reference for the integration. It is aimed at
developers, maintainers and people debugging a provider API. User-facing
installation and usage instructions live in the
[user documentation](../README.md).

## Technical documents

| Document | Contents |
|----------|----------|
| [Integration notes](INTEGRATION.md) | Module map, coordinator lifecycle, snapshot → entity mapping, daily backfill, error mapping, unique IDs |
| [Provider contract](PROVIDERS.md) | `BaseProvider`, the normalized snapshot schema, and a checklist for adding a provider |
| [Command Code API](API.md) | Endpoints, payload shapes, quirks and the plan table |

## Repository layout

```text
custom_components/ai_sub/     Home Assistant integration
  __init__.py                 setup/unload and platform forwarding
  api.py                      shared HTTP helper and provider error types
  calc.py                     pure math/time helpers (no HA imports)
  config_flow.py              provider picker, credentials, reauth, options
  const.py                    domain, config keys, polling bounds
  coordinator.py              DataUpdateCoordinator, one per account
  entity.py                   shared entity base and device info
  sensor.py                   twelve sensors
  binary_sensor.py            three limit binary sensors
  diagnostics.py              redacted config + snapshot dump
  providers/
    __init__.py               provider registry
    base.py                   provider contract and snapshot schema
    commandcode.py            Command Code client, parsers, plan table
  brand/                      icon.png / icon@2x.png
  strings.json, translations/ UI strings
assets/icon.png               README icon
docs/                         User documentation
docs/internal/                This technical reference
tests/                        Unit and Home Assistant harness tests
tools/make_icon.py            Regenerates the icon artwork
```

## Local checks

Create a virtual environment and install the test requirements:

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements_test.txt
```

Run the suite:

```bash
pytest
ruff check custom_components tests conftest.py
ruff format --check custom_components tests conftest.py
```

`pytest` runs both layers: pure unit tests for `calc` and the Command Code
parsers, and integration tests using `pytest-homeassistant-custom-component`
that set up the config entry against a mocked aiohttp session.

Notes:

- The Home Assistant harness blocks sockets. On Windows this breaks asyncio's
  Proactor event loop, so `conftest.py` neutralises the guard there; HTTP is
  still mocked.
- On Windows, `aiodns` needs a selector event loop that Home Assistant does not
  use in tests. If session creation fails with `aiodns needs a SelectorEventLoop`,
  uninstall `aiodns` in the test environment.
- The integration itself imports Home Assistant, so importing
  `custom_components.ai_sub` without the harness only works with Home Assistant
  installed.

## Conventions

- Provider vendors' quirks stay in their module: endpoint paths, payload shapes,
  plan tables, window keys. `calc.py` owns only maths and time.
- Never let a provider raise a bare exception from `async_fetch`: use
  `ProviderAuthError` for credentials, `ProviderConnectionError` for transport,
  `ProviderApiError` for unexpected answers. The coordinator maps them to
  reauth/retry.
- Any new display string goes in `strings.json` **and**
  `translations/en.json` (they must stay identical) plus the entity's
  `_attr_translation_key`.
- Keep the snapshot plain JSON types (plus `datetime`), because diagnostics has
  to serialize it.
