# VisiblAir Home Assistant integration — architecture

Frozen design record as of Phase 0 (2026-05-26). Captures the upstream
API surface, the constraints that shape the integration, and the
specific decisions locked before Phase 1 code begins.

The goal of this document is that someone (future-us, a contributor)
reading it cold should not need to re-do the API discovery work we did
to reach these conclusions.

## Upstream system: VisiblAir

- Vendor: VisiblAir (visiblair.com), sells "CO2click"-branded air-quality
  sensors
- Hardware verified: Model E, firmware 1.7.2
- The vendor exposes **two** HTTP APIs:
  1. **Cloud REST API** — `https://api.visiblair.com:11000/api/v1/sensor`
     (this integration's target)
  2. **Local API** — `http://co2click-AABBCC.local:8080/state` on each
     sensor (deliberately not used; see below)

## Authentication model

Per-sensor share tokens — there is **no account-level API key**.

Each sensor in the VisiblAir cloud portal has a "Public view" page. The
portal generates a URL of the form:

```
https://public.visiblair.com/index.html?id=<MAC>&viewToken=<TOKEN>
```

- `<MAC>` is the sensor's Wi-Fi MAC, colon-separated, e.g.
  `30:C6:F7:25:C4:A0`. (Spelled `uuid` in the REST API.)
- `<TOKEN>` is an opaque 8-character hex string the portal owner can
  regenerate.

Both values combined authorize read access to that one sensor's last
sample. There is no token that authorizes the whole fleet.

**Implication for HA UX:** the integration cannot enumerate the user's
sensors from a single login. Each sensor must be added explicitly with
its own (MAC, viewToken) pair. → one HA config entry per sensor.

## Cloud REST API surface

**The documented endpoint is the *entire* surface.**

```
GET https://api.visiblair.com:11000/api/v1/sensor?uuid=<MAC>&viewToken=<TOKEN>
```

Returns the sensor's full device record as JSON — latest sample,
firmware state, calibration history, alert thresholds, MQTT-bridge
config fields, sharing/delegate config, geolocation.

We probed for the following on 2026-05-26 and they **do not exist**:

| Path probed | Behavior |
|---|---|
| `/`, `/api/`, `/api/v1/`, `/api/v2/` | `200 OK` with `Content-Length: 0` |
| `/api/openapi.json` | `200 OK` empty |
| `/api/v1/sensors`, `/devices`, `/account`, `/user` | `200 OK` empty |
| `/api/v1/sensor/<MAC>` (path-style) | `200 OK` empty |
| `/api/v1/sensor/<MAC>/{history,measurements,data,samples}` | `200 OK` empty |
| `/api/v1/{history,measurements,data,samples}?uuid=…` | `200 OK` empty |
| `/api/v1/sensor/<MAC>/{calibration,firmware,config}` | `200 OK` empty |
| `/api/v1/{map,public,version,health}` | `200 OK` empty |
| `/api/v2/sensor?uuid=…&viewToken=…` | `200 OK` empty |

### The open catch-all trap

The server returns `HTTP/1.1 200 OK` with `Content-Length: 0` for **any
URL under the API root that isn't an exact match for a defined route**.
This is a developer trap: it's easy to think you've discovered an
endpoint because it 200'd. **It hasn't.**

Defensive parsing rule for this integration:

- A response is only considered "data" if the body is non-empty *and*
  parses as JSON *and* contains an expected schema field
  (`uuid`/`description`/`lastSampleTimeStampRedis`).
- A 200 with empty body on the documented URL means a different failure
  mode (auth, missing param, unknown sensor) — do not treat HTTP status
  family as the signal.
- `GET /api/v1/sensor` with **no** query parameters returns *zero bytes
  on the wire* (no status line at all) — a third distinct error mode.
  Handle as a connection-level error in the lib.

### What the cloud API cannot do

- **No history.** Only the latest sample. HA's recorder handles history.
- **No enumeration.** No list-my-sensors endpoint.
- **No control.** The payload includes fields like `calibrationRequested:
  false` and `firmwareUpgradeRequested: false` which look like they
  imply a write endpoint, but no documented or undocumented verb on this
  surface flips them. This integration is **strictly read-only**.

### Response shape quirks

- **`Content-Type: text/plain; charset=utf-8`** on JSON responses.
  Parse as JSON regardless of the advertised type — do not let
  `aiohttp`'s `response.json()` auto-content-type check trip on this.
  Use `json.loads(await response.text())` or
  `response.json(content_type=None)`.
- **`Vary: Origin` duplicated** in response headers. Cosmetic.
- **HEAD requests return `409 Conflict`.** Don't switch on status code
  *families* when handling responses; switch on observed content. If
  any future mutation flow is discovered, expect quirky status codes.
- **No cache headers anywhere** — no `Cache-Control`, no `ETag`, no
  `Expires`, no CDN fingerprint. An aiohttp coordinator gets fresh data
  on every poll with no cache-busting needed.

### Sample response

See [`tests/fixtures/sensor_response.json`](../tests/fixtures/sensor_response.json)
for a real captured payload (credentials redacted) showing the full shape.

Notable nested structure: the field `lastSampleDataRedis` is a JSON
string (not a nested object) — its value must be `json.loads()`ed a
second time to extract per-metric fields. The top-level
`lastSampleCo2` / `lastSampleTemperature` / `lastSampleHumidity` /
`lastSamplePm*` fields duplicate a subset of this data and are easier
to consume, but the nested blob has richer values (sub-second precision,
extra fault flags).

**Integration choice:** read top-level convenience fields where they
exist; fall back to parsing `lastSampleDataRedis` for fields that only
appear there (`PMFanFail`, `PMLaserFail`, `PMRhtError`,
`PMGasSensorError`, `PMFanCleaning`, `PMFanSpeedWarning`,
`firmwareVersion`).

## Local API: documented but not used

The VisiblAir how-to page documents a local-network endpoint:

```
GET http://co2click-AABBCC.local:8080/state
Authorization: Bearer <UUID_UPPER_CASE>
```

where `AABBCC` is the MAC suffix shown on the sensor's Info screen.
Enabled per-sensor via Configuration → Data handling options → "Local
API".

**This is not used by this integration.** On firmware 1.7.2 (confirmed
on the user's fleet of 4 sensors), enabling the Local API toggle causes
the sensor to disconnect from the VisiblAir cloud and then loop endlessly
trying to upload data. The sensor becomes inaccessible from the cloud
API until Local API is disabled and the sensor is power-cycled.

Architectural decision (locked 2026-05-26): cloud-only. If VisiblAir
fixes the firmware so Local API can coexist with cloud uploads, this
decision should be revisited and a local-first transport added. Until
then, do not introduce local-API code paths even speculatively.

## Integration architecture

### Repository layout

Single repository, no PyPI-published client lib. Rationale: the cloud
surface is one endpoint, and the integration can be implemented
entirely with `aiohttp` + `voluptuous` + the Python standard library
— both of which HA already ships in core. With zero non-stdlib runtime
dependencies, the "HA container rebuild wipes pip-installed wheels"
failure mode that motivated the sibling `aranet-cloud` PyPI lib does
not apply here.

```
visiblair-homeassistant/
├── README.md, CHANGELOG.md, LICENSE, hacs.json, info.md
├── docs/
│   └── architecture.md      (this file)
├── custom_components/
│   └── visiblair/           (Phase 1+)
│       ├── __init__.py      (async_setup_entry, async_unload_entry)
│       ├── config_flow.py   (add-sensor + reauth + options)
│       ├── const.py
│       ├── coordinator.py   (DataUpdateCoordinator subclass)
│       ├── api.py           (aiohttp wrapper for the one endpoint, defensive parser)
│       ├── sensor.py
│       ├── binary_sensor.py
│       ├── diagnostics.py
│       ├── manifest.json
│       ├── strings.json
│       └── translations/en.json
└── tests/
    ├── fixtures/
    │   └── sensor_response.json   (Phase 0: captured payload, redacted)
    └── …                          (Phase 1+: unit tests)
```

### Domain + display name

- Integration domain (technical, snake_case): `visiblair`
- Display name (UI, HACS): "VisiblAir" (matches vendor's brand spelling
  on visiblair.com)

### Config entries

**One HA config entry per sensor.** Each entry stores:

- `unique_id`: the sensor MAC (e.g. `30:C6:F7:25:C4:A0`)
- `data`:
  - `uuid`: MAC as written
  - `view_token`: the 8-char hex string

Config flow validates the credentials by hitting the live API once
during the add flow; rejects on empty body or non-JSON content.

A **reauth flow** triggers when the API begins returning empty bodies
for a previously-working entry (token rotated by the user from the
VisiblAir portal). The flow prompts for a new `view_token` only — MAC
stays put.

An **options flow** exposes:

- `scan_interval` (30–600 s, default 60 s)

### Coordinator

One `DataUpdateCoordinator` instance per config entry (per sensor).
60-second default cadence, configurable via options flow. Coordinator
calls into the API wrapper, normalizes the response (parsing the
nested `lastSampleDataRedis` JSON string), and exposes a typed dict to
the platform entities.

The API wrapper raises domain-specific exceptions
(`VisiblAirAuthError`, `VisiblAirOfflineError`,
`VisiblAirParseError`) that map cleanly to `UpdateFailed` /
`ConfigEntryAuthFailed`.

### Entity map

All entities are children of a single HA device per sensor. Device info
populated from the API response (`description`, `model`,
`firmwareVersion`, MAC as identifier).

#### Sensor entities

| Entity suffix | Source field | Unit | Device class |
|---|---|---|---|
| `co2` | `lastSampleCo2` | `ppm` | `carbon_dioxide` |
| `temperature` | `lastSampleTemperature` | `°C` | `temperature` |
| `humidity` | `lastSampleHumidity` | `%` | `humidity` |
| `voc_index` | `lastSampleVocIndex.Int64` | (none) | `aqi` (not perfect but closest) |
| `pressure` | `lastSamplePressure.Float64` | `hPa` | `atmospheric_pressure` |
| `pm01` | `lastSamplePm01.Float64` | `µg/m³` | `pm1` |
| `pm03` | `lastSamplePm03.Float64` | `µg/m³` | (no HA class — leave unset) |
| `pm05` | `lastSamplePm05.Float64` | `µg/m³` | (no HA class) |
| `pm10` | `lastSamplePm10.Float64` | `µg/m³` | (PM 1 µm — `pm1`, not the HA `pm10` class which is 10 µm) |
| `pm25` | `lastSamplePm25.Float64` | `µg/m³` | `pm25` |
| `pm40` | (from nested `lastSampleDataRedis.pm40`) | `µg/m³` | (no HA class) |
| `pm50` | `lastSamplePm50.Float64` | `µg/m³` | (no HA class) |
| `pm100` | `lastSamplePm100.Float64` | `µg/m³` | `pm10` (10 µm) |
| `battery` | `lastSampleBattPct.Float64` | `%` | `battery` |
| `battery_voltage` | `lastSampleBattVoltage.Float64` | `V` | `voltage` (diagnostic) |

**Naming gotcha to fix later:** the API uses `pm10` for PM 1.0 µm and
`pm100` for PM 10.0 µm — the trailing digit is a decimal-position quirk
(`pm03` = 0.3 µm, `pm25` = 2.5 µm, `pm100` = 10.0 µm). The HA entity
naming should be unambiguous: `pm_1_0_um`, `pm_10_0_um`, etc., to avoid
confusion with HA's standard `pm1` / `pm10` device classes that share
the names but have different meanings.

#### Binary sensor entities

All `diagnostic` entity category. Sourced from nested `lastSampleDataRedis`.

| Entity suffix | Source field | Device class |
|---|---|---|
| `ac_connected` | `isACIN` | `plug` |
| `charging` | `isCharging` | `battery_charging` |
| `pm_fan_fail` | `PMFanFail` | `problem` |
| `pm_laser_fail` | `PMLaserFail` | `problem` |
| `pm_rht_error` | `PMRhtError` | `problem` |
| `pm_gas_sensor_error` | `PMGasSensorError` | `problem` |
| `pm_fan_cleaning` | `PMFanCleaning` | (none — informational) |
| `pm_fan_speed_warning` | `PMFanSpeedWarning` | `problem` |

#### Diagnostic sensor entities

| Entity suffix | Source field | Notes |
|---|---|---|
| `firmware_version` | top-level `firmwareVersion` | string |
| `last_calibration` | `lastCalibration` | timestamp |
| `last_sample` | `lastSampleTimeStampRedis` | timestamp |

### Diagnostics

`diagnostics.py` provides an HA "Download diagnostics" handler returning
the raw API response with these fields redacted:

- `viewToken`
- `latitude`, `longitude`
- `email.String`
- `MQTTPassword`, `MQTTUsername`, `MQTTCert`
- `delegateAccounts`, `delegatedAccounts`
- `associatedUserID`

### Polling, errors, recovery

- **Default cadence:** 60 s per sensor. Sensors report new samples
  every 60 s by default (settable on-device); shorter HA polling does
  not yield fresher data.
- **Backoff:** standard `DataUpdateCoordinator` exponential backoff on
  consecutive `UpdateFailed`s.
- **Auth failure** (response is empty 200 on a previously-working entry):
  raise `ConfigEntryAuthFailed` → HA triggers the reauth flow.
- **Offline** (response 5xx, connection error, or empty status line):
  raise `UpdateFailed`. Entities go unavailable. Coordinator keeps
  trying on cadence.
- **Stale** (`lastSampleTimeStampRedis` more than 15 min in the past):
  log a warning at INFO. Do not mark entities unavailable — a real
  sensor offline scenario, where the cloud has no new data to report,
  should still surface the last known value.

## Out of scope (v0.1+)

- Local API (firmware bug — see above)
- Historical data (not exposed by the API)
- Write operations (not exposed by the API)
- MQTT bridge config (the API exposes the *settings* but not a control
  surface, and the user's setup doesn't use it)
- Geofence / public-map awareness (`publicOnMap`, `latitude`,
  `longitude` — diagnostic value only)
- Alert-threshold management (the API exposes the JSON blob but read-only)

## Open questions

1. **viewToken rotation cadence** — unknown whether tokens expire on a
   schedule or only on user-triggered regeneration. Reauth flow handles
   both, so this is a documentation question, not a code question.
2. **Multiple sensors sharing one cloud account** — assumed
   independent. Worth confirming that one sensor going offline doesn't
   somehow affect another's reachability.
3. **Rate limit / throttling** — none observed in light testing, none
   documented. Default 60 s cadence is conservative. Worth load-testing
   before recommending shorter cadences.

## Phase plan

- **Phase 0 (done — 2026-05-26):** API research, architecture doc,
  repo scaffold, captured sample fixture. Tagged `v0.0.1-phase0`.
- **Phase 1:** `custom_components/visiblair/` scaffold with `api.py`,
  `coordinator.py`, `config_flow.py`, `__init__.py`, `manifest.json`,
  proof-of-wire CO₂ sensor. Tag `v0.1.0`.
- **Phase 2:** full sensor/binary_sensor/diagnostic coverage. Tag
  `v0.2.0`.
- **Phase 3:** options flow, reauth flow, diagnostics, brand assets,
  unit tests, mypy/ruff CI. Tag `v0.3.0`.
- **Phase 4:** docs polish, CHANGELOG, CONTRIBUTING, public-GitHub
  push, HACS default-registry submission.
