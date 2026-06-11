# VisiblAir Home Assistant integration — architecture

Frozen design record as of Phase 0 (2026-05-26). Captures the upstream
API surface, the constraints that shape the integration, and the
specific decisions locked before Phase 1 code begins.

The goal of this document is that someone (future-us, a contributor)
reading it cold should not need to re-do the API discovery work we did
to reach these conclusions.

> **Note (post-Phase-4 update):** the entity-naming table in
> [§ Entity map](#entity-map) below reflects the *current* shipped naming
> (after the v0.4.0 µm-suffix-removal correction), not the original
> Phase-0 draft. The config-flow, parsing-fallback, health-flag, and
> diagnostics sections have likewise been updated to match shipped
> behavior (options-flow removal in v0.5.0; tri-state health flags and
> the parse-to-None nested fallback in v0.7.0). The API-surface research
> is unchanged from the frozen record. See [CHANGELOG.md](../CHANGELOG.md)
> for the iteration history.

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
  `AA:BB:CC:DD:EE:FF`. (Spelled `uuid` in the REST API.)
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
*parse to a value* — they arrive as strings, so an empty string counts
as absent and the nested `lastSampleDataRedis` value is consulted (not
only when the key itself is missing). Fields that only appear in the
nested blob (`PMFanFail`, `PMLaserFail`, `PMRhtError`,
`PMGasSensorError`, `PMFanCleaning`, `PMFanSpeedWarning`,
`firmwareVersion`) are parsed from it directly. The hardware-health and
power flags are tri-state: when the blob is missing or unparseable they
are *unreported* (`None`) and their binary sensors go **unavailable** —
never defaulted to `false`, which would mask a real fault as "no
fault".

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
│       ├── config_flow.py   (add-sensor + reauth + reconfigure)
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

- `unique_id`: the sensor MAC (e.g. `AA:BB:CC:DD:EE:FF`)
- `data`:
  - `uuid`: MAC as written
  - `view_token`: the 8-char hex string

Config flow validates the credentials by hitting the live API once
during the add flow; rejects on empty body or non-JSON content.

A **reauth flow** triggers when the API begins returning empty bodies
for a previously-working entry (token rotated by the user from the
VisiblAir portal). The flow prompts for a new `view_token` only — MAC
stays put.

There is **no options flow**. An earlier revision exposed
`scan_interval` (30–600 s), but it was removed in v0.5.0: HA Core
convention is that the integration owns its poll cadence, so the
interval is fixed at 60 s (`DEFAULT_SCAN_INTERVAL`), matching the
sensors' factory sample rate. A **reconfigure flow** lets the user
update the viewToken without removing the entry.

### Coordinator

One `DataUpdateCoordinator` instance per config entry (per sensor),
polling at the fixed 60-second cadence (not user-configurable).
Coordinator calls into the API wrapper, normalizes the response
(parsing the nested `lastSampleDataRedis` JSON string), and exposes a
typed `VisiblAirSensorData` snapshot to the platform entities.

The API wrapper raises domain-specific exceptions
(`VisiblAirAuthError`, `VisiblAirOfflineError`,
`VisiblAirParseError`) that map cleanly to `UpdateFailed` /
`ConfigEntryAuthFailed`.

### Entity map

All entities are children of a single HA device per sensor. Device info
populated from the API response (`description`, `model`,
`firmwareVersion`, MAC as identifier).

#### Sensor entities

Entity-key suffix shown below is the segment after `visiblair_{uuid}_`
in `unique_id`, and the entity-ID slug component (e.g.
`sensor.<device>_visiblair_pm_0_1`).

| Entity key | Source field | Unit | Device class |
|---|---|---|---|
| `co2` | `lastSampleCo2` | `ppm` | `carbon_dioxide` |
| `temperature` | `lastSampleTemperature` | `°C` | `temperature` |
| `humidity` | `lastSampleHumidity` | `%` | `humidity` |
| `voc_index` | `lastSampleVocIndex.Int64` | (none) | `aqi` (closest match) |
| `pressure` | `lastSamplePressure.Float64` | `hPa` | `atmospheric_pressure` |
| `pm_0_1` | `lastSamplePm01.Float64` | `µg/m³` | (no HA class) |
| `pm_0_3` | `lastSamplePm03.Float64` | `µg/m³` | (no HA class) |
| `pm_0_5` | `lastSamplePm05.Float64` | `µg/m³` | (no HA class) |
| `pm_1_0` | `lastSamplePm10.Float64` | `µg/m³` | `pm1` |
| `pm_2_5` | `lastSamplePm25.Float64` | `µg/m³` | `pm25` |
| `pm_4_0` | nested `lastSampleDataRedis.pm40` | `µg/m³` | (no HA class) |
| `pm_5_0` | `lastSamplePm50.Float64` | `µg/m³` | (no HA class) |
| `pm_10_0` | `lastSamplePm100.Float64` | `µg/m³` | `pm10` |
| `battery` | `lastSampleBattPct.Float64` | `%` | `battery` |
| `battery_voltage` | `lastSampleBattVoltage.Float64` | `V` | `voltage` (diagnostic) |

**Naming-collision note:** the upstream API uses `pm10` for PM 1.0 µm
and `pm100` for PM 10.0 µm — the trailing digit is a decimal-position
quirk. HA entity keys translate to the decimal-um form
(`pm_1_0`, `pm_10_0`, …) to avoid clashing with HA's `pm1`/`pm10`
device-class names that have different physical meanings.

**Display-name note (v0.4.0):** entity *display names* are bare numerics
(`PM 1.0`, `PM 10.0`) with no `µm` suffix. The Unicode `µ` was
slugifying to `m`, producing ugly entity-ID slugs like `pm_1_mm`. The
unit context is conveyed by the `µg/m³` unit and the PM-spectrum
grouping in the dashboard; the size is self-evident.

#### Binary sensor entities

Sourced from the nested `lastSampleDataRedis` blob (with top-level
fallbacks for the power pair). The hardware-health flags carry the
`diagnostic` entity category; `ac_connected`/`charging` are
user-relevant and do not. All eight are tri-state: when the flag is
unreported (blob missing/unparseable) the entity is **unavailable**
rather than `off` — see the parsing rules above.

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

`diagnostics.py` provides an HA "Download diagnostics" handler. It does
**not** return the raw API response — it returns a normalised snapshot:
config-entry metadata, coordinator status (cadence, last-update result),
and the typed `VisiblAirSensorData` latest reading. These fields are
redacted at any depth (the raw-payload keys are listed defensively, in
case a future revision ever attaches the raw response):

- `view_token` / `viewToken`
- `uuid` / `unique_id` (the sensor MAC, including its embedding in the
  coordinator name)
- `latitude`, `longitude`
- `email`
- `MQTTPassword`, `MQTTUsername`, `MQTTCert`, `MQTTEndpoint`, `MQTTTopic`
- `delegateAccounts`, `delegatedAccounts`
- `associatedUserID`

### Polling, errors, recovery

- **Default cadence:** 60 s per sensor. Sensors report new samples
  every 60 s by default (settable on-device); shorter HA polling does
  not yield fresher data.
- **Backoff:** standard `DataUpdateCoordinator` exponential backoff on
  consecutive `UpdateFailed`s.
- **Auth failure** (response is empty 200 on a previously-working entry):
  because the catch-all answers *any* server-side anomaly with the same
  empty 200, a single occurrence is treated as a transient `UpdateFailed`;
  only after 3 consecutive auth-classified failures does the coordinator
  raise `ConfigEntryAuthFailed` → HA triggers the reauth flow. The counter
  (persisted in `hass.data`, so it survives setup retries) resets on the
  first successful poll.
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

## Phase plan (historical)

All phases complete as of 2026-05-26. The README, CHANGELOG, and
integration code are now the source of truth for current behavior;
this list is retained for historical context only.

- **Phase 0 (2026-05-26, tag `v0.0.1-phase0`):** API research,
  architecture doc, repo scaffold, captured sample fixture.
- **Phase 1 (tag `v0.1.0`):** `custom_components/visiblair/` scaffold
  with `api.py`, `coordinator.py`, `config_flow.py`, `__init__.py`,
  `manifest.json`, proof-of-wire CO₂ sensor.
- **Phase 2 (tag `v0.2.0`):** full sensor/binary_sensor/diagnostic
  coverage — 26 entities per sensor.
- **Phase 3 (tag `v0.3.0`):** options flow, reauth flow, diagnostics,
  brand-asset placeholder, 18 unit tests, mypy-strict + ruff CI.
- **Phase 4 (tag `v0.4.0`):** docs polish, SECURITY.md, issue
  templates, PM display-name correction. Public GitHub push + HACS
  default-registry submission follow as separate publishing actions.
