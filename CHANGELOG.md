# Changelog

## 0.6.3 — 2026-06-10

Hotfix: restore compatibility with Python ≤ 3.13 (all Home Assistant
releases before mid-2026).

- **Fixed:** `api.py` used unparenthesized `except TypeError, ValueError:`
  (PEP 758, Python 3.14-only syntax). On Python ≤ 3.13 the module failed
  to import with a `SyntaxError`, so the integration could not load at
  all. Restored the parenthesized form.
- **Root cause:** 0.6.2 moved `ruff` `target-version` to `py314`, and with
  that setting `ruff format` actively rewrites `except (A, B):` into the
  3.14-only unparenthesized form — the formatter introduced the regression
  and would have re-introduced it on every format pass. `target-version`
  is now `py312`, matching the declared support floor (hacs.json HA
  2025.1.0 ran Python 3.12). mypy stays at 3.14 because it parses the
  installed (current) HA source, which itself uses 3.14-only syntax.
- **CI:** pytest now runs on a Python 3.13 + 3.14 matrix (3.13 resolves an
  older HA test harness, so the suite also exercises an older Home
  Assistant), and a new `syntax-floor` job compiles every module on
  Python 3.12 so newer-than-floor syntax can never ship silently again.

## 0.6.2 — 2026-06-10

Observability gap-fill (no functional changes).

- `data_description` hover help on every config-flow field, including
  treat-it-like-a-password framing for the viewToken.
- CI and mypy/ruff targets moved to Python 3.14 — the latest Home
  Assistant test harness requires ≥3.14, so a 3.13 pin silently tests
  against months-old HA.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.6.1] — 2026-06-09

### Logging

- Level-appropriate, secret-safe `debug` logging: a setup line (sensor name,
  MAC, poll interval) and a per-poll line (`Polled <MAC>: CO2=… PM2.5=…
  battery=…`). The viewToken is never logged at any level. See
  *README → Troubleshooting → Enabling debug logs*.

### Fixed (docs)

- `info.md` no longer claims a "Configurable poll cadence (30–600 s)" — there
  is no such option; the cadence is a fixed 60 s. Documented the reconfigure
  flow and the disabled-by-default entities.
- `CONTRIBUTING.md` test command now uses
  `pytest-homeassistant-custom-component` (the old command would fail) and runs
  with coverage.

## [0.6.0] — 2026-06-09

Quality scale **Bronze → Platinum** (`manifest.json` `"quality_scale": "platinum"`).

### Added

- **Full Home Assistant test suite** under `tests/` (config / reauth /
  reconfigure flows, setup/unload, coordinator auth + API-error paths,
  sensor + binary_sensor states, the API HTTP layer, diagnostics redaction)
  via `pytest-homeassistant-custom-component` — **100% line coverage**, on top
  of the existing normaliser/entity-map tests.
- **Reconfigure flow** — update a sensor's viewToken from **⋮ → Reconfigure**
  without removing and re-adding it.
- **`PARALLEL_UPDATES = 0`** on both platforms.
- **Translated exceptions** — coordinator auth/update failures raise with
  `translation_key`s (`strings.json` `exceptions`).
- **Icon translations** (`icons.json`) for the VOC-index, firmware, and
  PM-fan-cleaning entities (moved out of code).
- **CI**: pytest now runs with a ≥95% coverage gate.

### Changed

- **Niche PM sizes (0.1 / 0.3 / 0.5 / 4.0 / 5.0 µm) and battery voltage are
  now disabled by default** — enable per entity if wanted. PM 1 / 2.5 / 10 µm
  stay enabled.
- Quality scale: `brands`, `docs-removal-instructions`, `parallel-updates`,
  `config-flow-test-coverage`, `test-coverage`, and the full Gold + Platinum
  rule sets are now done/exempt. Single-device-specific rules
  (`dynamic-devices`, `stale-devices`, `discovery`) are exempt with rationale.

### Fixed (docs)

- Removed the dead `options` / `scan_interval` translation block (no
  OptionsFlow exists). Added **Removing the integration**, **Use cases**,
  **Example automations**, **Known limitations**, and **Troubleshooting**
  (incl. enable-debug-logs) sections; refreshed the stale test count.

## [0.5.0] — 2026-05-27

### Removed (breaking)

- **OptionsFlow** and user-configurable poll interval. HA Core convention
  is that the integration owns its cadence; we now poll at a fixed 60 s
  (matching VisiblAir's factory sample rate, which was the previous
  default). Old config entries with a saved `options.scan_interval` are
  tolerated — the value is simply ignored. `CONF_SCAN_INTERVAL`,
  `MIN_SCAN_INTERVAL_SECONDS`, and `MAX_SCAN_INTERVAL_SECONDS` dropped
  from `const.py`.

### Added

- **`quality_scale.yaml`** (Bronze tier) with Silver-tier rule status
  pre-mapped (done / todo / exempt).
- **`"quality_scale": "bronze"`** in `manifest.json`.
- **PEP-561 `py.typed`** marker so downstream type-checkers honour the
  integration's type hints.
- **`.github/copilot-instructions.md`** — HA Core integration conventions
  adapted for custom integrations, so AI assistants editing this repo
  produce idiomatic HA-style code.

### Changed

- HACS `homeassistant` floor bumped `2024.12.0` → `2025.1.0`.
- `VisiblAirCoordinator.__init__` now takes the `ConfigEntry` directly
  and passes it to `super().__init__(config_entry=entry)` per the
  HA 2024.10+ pattern (so HA can attribute coordinator errors).
- **`device_info_for()`** now uses `CONNECTION_NETWORK_MAC` +
  `format_mac()` for the `DeviceInfo.connections` field, so DHCP /
  Zeroconf discovery from other integrations can match this device. The
  `unique_id` (config-entry key) stays upper-case for backward
  compatibility with existing entries; the internal helper has been
  renamed `_normalise_mac` → `_canonicalise_uuid` with a docstring
  explaining the split between registry-facing canonical form and the
  upper-case internal storage form.
- `_async_options_updated` listener removed (no options to react to).
- README updated to reflect the fixed cadence.

### Notes

Closes most Bronze quality-scale blockers for HA Core acceptance.
Remaining gaps:

- Config-flow / coordinator tests still missing.
- `VisiblAirAuthError` still over-broad in `api.py` (any empty-body 200
  is treated as auth failure; should narrow to confirmed credential
  rejection).
- `firmware_version` sensor still duplicates `DeviceInfo.sw_version`.
- Silver-tier: `async_step_reconfigure` not implemented.

## [0.4.1] — 2026-05-27

### Added

- **Brand assets** (`icon.png` 256×256, `icon@2x.png` 512×512,
  `logo.png` 767×193, `logo@2x.png` 1534×386) — PNG-RGBA with
  transparency, sourced from VisiblAir branding. HA serves them as
  the integration tile icon directly from
  `custom_components/visiblair/brand/`. Live-verified on the
  development HA instance.
- **`.github/workflows/validate.yml`** — official `hacs/action@main`
  + `home-assistant/actions/hassfest@master` validators running on
  push, PR, daily cron, and manual dispatch. Both pass green.

### Fixed

- **Hassfest validation:** removed the URL from the add-sensor
  config-flow `description` string (`strings.json` +
  `translations/en.json`). Hassfest rejects URLs in translation
  description fields. Replaced with a query-parameter-name
  reference that conveys the same setup info without the URL.

### Changed

- **`docs/architecture.md`** entity table refreshed to reflect the
  current `pm_<size>` entity-key naming (previously held the early
  Phase-0 draft using upstream `pm10`/`pm100`/`pm03` field names).
  The "naming gotcha to fix later" callout is now resolved into a
  naming-collision note + display-name note documenting the v0.4.0
  µm-suffix correction. Phase plan reframed as historical now that
  Phase 4 is complete.
- **`brand/README.md`** rewritten — drops the "intentionally absent"
  framing now that assets are present; documents what's bundled and
  notes the dark-theme variants are absent (HA falls back to the
  non-dark variants).
- **`CONTRIBUTING.md`** Python target clarified to 3.13 (matches
  `pyproject.toml`).
- **`.github/ISSUE_TEMPLATE/bug_report.yml`** version-placeholder
  bumped to 0.4.0.

### Verified live

- All 4 sensors in the development fleet (Audi RS Q8, Great Room,
  South Bedroom, Study) report cleanly under the v0.4.0+ entity
  IDs — no residual `_mm` slugs.
- Brand assets render as the integration tile icon in HA Core
  Settings → Devices & Services → VisiblAir.

## [0.4.0] — 2026-05-26

### Changed (breaking — but caught during pre-release live test)

- **PM entity display names** dropped the `µm` suffix that HA's
  slugify was Unicode-normalising into `mm` (producing entity IDs
  like `sensor.family_room_visiblair_pm_0_1_mm`). New names are the
  decimal `PM 0.1` / `PM 1.0` / `PM 10.0` form, which slugify cleanly
  to `pm_0_1` / `pm_1_0` / `pm_10_0` — matching the internal
  description-key naming.
- **Migration:** users on v0.3.0 should delete + re-add the
  integration entries to pick up the new entity IDs. (Caught during
  the v0.3.0 live test before public release; v0.3.0 was never
  published, so this only affects local pre-release installs.)

### Added (Phase 4a — docs polish for public release)

- **README rewrite** dropping the "Phase 0 (architecture)" framing now
  that the integration is feature-complete. Adds HACS install steps,
  a setup walk-through that highlights the MAC + viewToken extraction
  from the public-viewer URL, an entity-category table, options-flow
  description, the cloud-only rationale, a quality-bar callout, and a
  diagnostics blurb.
- **SECURITY.md** — vulnerability-reporting policy (private email
  rather than public issue), scope, response timeline.
- **`.github/ISSUE_TEMPLATE/bug_report.yml`** — structured form prompting
  for integration version, HA Core version, sensor model + firmware,
  logs, and a diagnostics download.
- **`.github/ISSUE_TEMPLATE/config.yml`** — disables the blank-issue
  shortcut for security reports and routes general questions to GitHub
  Discussions.

Phase 4b (public-GitHub push + HACS default-registry submission)
intentionally deferred — those are publishing actions that need
explicit user authorization.

## [0.3.0] — 2026-05-26

### Added (Phase 3 — diagnostics, CI, polish)

- **`diagnostics.py`** — HA "Download diagnostics" handler with full
  credential redaction. Dumps the config entry (data + options), the
  coordinator's state (interval, last-success, last-exception type),
  and the latest normalised reading. The `view_token` and all
  hypothetical-future raw-payload secrets (lat/long, email, MQTT
  creds, delegate accounts, internal user IDs) are scrubbed via HA's
  `async_redact_data` at any depth.
- **`pyproject.toml`** with tool configuration for ruff (lint + format),
  mypy strict, and pytest. Targets Python 3.13 (matching HA Core's
  current floor — needed for mypy because HA itself uses PEP 696
  generic-type-defaults internally).
- **`.github/workflows/ci.yml`** — single-job GitHub Actions workflow
  that runs ruff (check + format), mypy strict, and pytest on every
  push to main + every PR. Uses `uv` to install Python + deps
  on-demand (no requirements.txt needed; the workflow is the source
  of truth for test deps).
- **`CONTRIBUTING.md`** — bug-report format, dev setup with the exact
  `uv run` commands, code-style notes, live-HA testing instructions.
- **`custom_components/visiblair/brand/README.md`** — placeholder
  documenting which PNG asset files HA expects for the integration
  tile and HACS browse view, and the official HA brand spec. Real
  asset files intentionally absent pending VisiblAir branding
  approval; the integration is fully functional without them.
- **`tests/test_diagnostics.py`** — 3 tests:
  - `view_token` from entry.data must not survive the dump
  - non-sensitive metadata (uuid, model, firmware, readings)
    round-trips intact
  - REDACT set covers every architecture-doc-documented secret
    field (locks against silent drift)

### Changed

- **Ruff/mypy lint pass** on Phase 1 + Phase 2 code: import sorting
  normalised, `from datetime import timezone` → `from datetime import
  UTC` (Python 3.11+ alias), import-block formatting standardised,
  ruff format applied to all 13 .py files.
- **Manifest version** bumped to 0.3.0.

### Verified

- `ruff check custom_components/ tests/` — all checks passed
- `ruff format --check` — 13 files already formatted
- `mypy --strict custom_components/visiblair/` — 0 issues across 8
  source files
- `pytest tests/` — 18/18 pass in ~0.85s (warm cache)

## [0.2.0] — 2026-05-26

### Added (Phase 2 — full entity coverage)

- **Sensor platform** now exposes 18 entities per VisiblAir sensor,
  driven by a `SENSOR_DESCRIPTIONS` table in `sensor.py`:
  - Environmental: CO₂, temperature, humidity, VOC index, atmospheric pressure
  - Particulate matter: PM 0.1, 0.3, 0.5, 1, 2.5, 4, 5, 10 µm (8 entities;
    HA device classes attached where they exist — PM1, PM2.5, PM10 — and
    intentionally absent on the others, which still record + graph fine)
  - Power: battery (%)
  - Diagnostic: battery voltage (V), firmware version (str), last sample
    (timestamp), last calibration (timestamp)
- **Binary-sensor platform** (new) exposes 8 entities per sensor:
  - Power: AC connected (`PLUG`), charging (`BATTERY_CHARGING`)
  - Health: PM fan fail, PM laser fail, PM RHT error, PM gas-sensor error,
    PM fan speed warning (all `PROBLEM`, `DIAGNOSTIC`), PM fan cleaning
    (informational, `DIAGNOSTIC`, no device class)
- **Translation keys + display names** for all 26 entities in
  `strings.json` + `translations/en.json` (82 keys, identical key sets).
- **`device_info_for(data)` helper** in `sensor.py`, shared with
  `binary_sensor.py` so both platforms wire entities under the same HA
  device.
- **`tests/test_entities.py`** with 6 new tests:
  - Wiring-map completeness check — every `VisiblAirSensorData` field
    is either declared as an entity or explicitly marked as
    device-metadata (catches "I added a field but forgot the entity").
  - Description-set completeness — every declared entity key has a
    matching description.
  - No-key-collision-across-platforms check (since unique_id format is
    `visiblair_{uuid}_{key}`).
  - `value_fn` smoke tests for both sensor and binary-sensor descriptions
    against the captured fixture.
  - Canonical-value spot-checks (CO₂=523, battery=96.02, etc.).

### Changed

- **`__init__.py`** registers `Platform.BINARY_SENSOR` alongside
  `Platform.SENSOR`.
- **`sensor.py` was rewritten** from the Phase 1 proof-of-wire single-CO₂
  class to the description-driven pattern. The pre-Phase-2 CO₂-only
  entity is replaced by the full surface.
- **Unique-ID format** is now `visiblair_{uuid}_{key}` (was `{uuid}_co2`
  for the lone Phase-1 entity). The `visiblair_` prefix prevents
  collisions if another integration ever uses the same MAC as a stable
  identifier. No-op for users — Phase 1 was never released.

### Verified

- `pytest tests/` — 15/15 pass under Python 3.13 + HA installed via uv
- `python3.14 -m compileall` clean
- `strings.json` and `translations/en.json` — 82 keys, identical structure

## [0.1.0] — 2026-05-26

### Added (Phase 1 — integration scaffold + proof-of-wire)

- `custom_components/visiblair/` integration package:
  - `manifest.json` — HACS-ready, `iot_class: cloud_polling`,
    `integration_type: device` (one entry = one sensor), no external
    runtime requirements (uses only `aiohttp` + `voluptuous` which ship
    with HA core)
  - `api.py` — async client for the single documented cloud endpoint,
    with the full defensive-parsing rules from `docs/architecture.md`:
    empty-body-as-failure regardless of HTTP status, JSON parse without
    trusting `Content-Type`, schema-shape validation, and three distinct
    exception classes (`VisiblAirAuthError`, `VisiblAirOfflineError`,
    `VisiblAirParseError`). Includes `VisiblAirSensorData` dataclass
    and a normaliser that handles the Go-style nullable-numeric blobs
    plus the JSON-encoded `lastSampleDataRedis` nested string
  - `coordinator.py` — `DataUpdateCoordinator` per sensor, maps API
    exceptions onto `ConfigEntryAuthFailed` / `UpdateFailed`
  - `config_flow.py` — user + reauth + options flows; MAC + viewToken
    on initial add, viewToken-only on reauth, scan-interval slider
    (30–600 s) in options
  - `__init__.py` — `async_setup_entry` / `async_unload_entry` with
    coordinator stored on `entry.runtime_data` per modern HA pattern;
    options-update listener triggers entry reload
  - `sensor.py` — proof-of-wire CO₂ entity (full sensor surface lands
    in Phase 2)
  - `strings.json` + `translations/en.json` for the config/options UI
- `tests/` with `conftest.py` exposing the captured fixture as both
  raw-string and parsed-dict fixtures; `tests/test_api.py` with 9
  passing tests covering normalisation, type coercion, nullable-wrapper
  handling, nested-blob parsing, garbage-input tolerance, and
  nanosecond-precision ISO 8601 timestamps

### Verified

- `python3.14 -m compileall` clean
- `pytest tests/test_api.py` — 9/9 pass under Python 3.13 + HA installed
- `strings.json` and `translations/en.json` have identical key
  structures (31 keys)
- All JSON files validate

## [0.0.1] — 2026-05-26

### Added (Phase 0 — architecture)

- Repository scaffolded with public-quality layout: `LICENSE` (Apache 2.0),
  `README.md`, `CHANGELOG.md`, `info.md`, `hacs.json`, `.gitignore`
- `docs/architecture.md` capturing:
  - Cloud API surface (single documented endpoint;
    `https://api.visiblair.com:11000/api/v1/sensor?uuid=<MAC>&viewToken=<TOKEN>`)
  - Authentication model (per-device viewToken, no account-level API key)
  - The "open catch-all" trap (every unknown route returns `200 OK` with
    `Content-Length: 0` — defensive parsing required)
  - Local API documented but non-viable (firmware 1.7.2 disconnect bug)
  - Entity map: which payload fields become which HA entity types
  - Defensive parsing rules
  - Coordinator + polling design
  - Config-flow model (one entry per sensor)
- `tests/fixtures/sensor_response.json` — captured real-world response
  with credentials redacted, for use in unit tests
