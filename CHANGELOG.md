# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet — Phase 3 (options flow polish, reauth flow polish, diagnostics
download, brand assets, CI workflows) is next.

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
