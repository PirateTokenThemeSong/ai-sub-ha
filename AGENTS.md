# AGENTS.md

Instructions for coding agents working in this repository. Human docs live in
[README.md](README.md) and [docs/](docs/README.md); architecture, the provider
contract and the vendor API notes are in [docs/internal/](docs/internal/README.md).

## Git workflow (required)

- **Commit every logical change.** Do not leave finished work uncommitted or
  stashed at the end of a task.
- **Push immediately after each commit.** `origin` must never lag behind local
  work; a task is not done while `git status` is dirty or `main` is ahead.
- **Commit before you deploy.** Never run code on a Home Assistant instance that
  is not in a pushed commit. Order: edit → check → commit → push → deploy →
  verify. If a hotfix is unavoidable, commit and push it first.
- **One commit per logical change**, imperative subject (`fix(sensor): …`,
  `docs: …`). The body explains *why*, not the diff. Fold lint/format/test
  fixups into the commit they belong to instead of adding noise commits.
- **Never commit secrets**: API keys, tokens, credentials, diagnostics dumps,
  billing payloads or `.env` files. The integration only ever takes credentials
  through the config flow.
- **Keep version and release in step**: bump `custom_components/ai_sub/manifest.json`
  `version` for user-visible changes and tag the release (`vX.Y.Z`) after the
  push. HACS reads those tags.

## Checks before committing

```bash
pytest                              # unit + Home Assistant harness tests
ruff check custom_components tests conftest.py tools
ruff format --check custom_components tests conftest.py tools
```

- Add or update a test for every behavior change; parser and snapshot tests call
  the pure functions with a fixed `now`, no session.
- UI strings change in **both** `strings.json` and `translations/en.json` (they
  must stay identical; `tests/test_translations.py` enforces it).
- Keep vendor specifics in `providers/<vendor>.py`; `calc.py` owns only maths and
  time, and must not import Home Assistant.
- Providers raise `ProviderAuthError` / `ProviderConnectionError` /
  `ProviderApiError`; never a bare exception from `async_fetch`.

## Deploying (only when asked)

- Two systems are involved: this repository and the Home Assistant instance.
  The dashboard and the installed copy of the integration are **not** versioned
  here beyond the config's own backups.
- Live instance: Home Assistant runs as a Docker stack on the `woof` server,
  config at `/opt/homeassistant` (mounted as `/config`). Docker/stack work goes
  through the `komodo` helper script, not ad-hoc SSH.
- Copying new module files is not enough: Home Assistant caches imports, so a
  code change takes effect only after a container restart. Reloading the config
  entry is sufficient for options/data changes, not for code.
- Entity IDs follow the account login reported by the provider
  (`sensor.<login>_usage`), not the entry title. Dashboards must be updated to
  the IDs the entities actually get; verify every referenced entity exists after
  a change.
- Destructive actions (deleting an integration folder, restarting) need the
  user's explicit go-ahead, and the previous state is backed up first.
