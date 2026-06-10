# VisiblAir for Home Assistant

[![release](https://img.shields.io/github/v/release/jasonjhofmann/visiblair-homeassistant?label=release&color=blue)](https://github.com/jasonjhofmann/visiblair-homeassistant/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![CI](https://github.com/jasonjhofmann/visiblair-homeassistant/actions/workflows/ci.yml/badge.svg)](https://github.com/jasonjhofmann/visiblair-homeassistant/actions/workflows/ci.yml)

Async, read-only Home Assistant integration for the
[VisiblAir](https://visiblair.com/) air-quality sensor cloud API.

Each VisiblAir sensor becomes one HA device with **26 entities**:
CO₂, temperature, humidity, VOC index, atmospheric pressure, the full
PM 0.1 – 10 µm spectrum (8 sizes), battery state and charge status,
plus diagnostic readouts for firmware, last sample, last calibration,
and a hardware-health flag per PM-subsystem fault VisiblAir reports.

## Install

### Via HACS (recommended)

1. In HACS → ⋮ → **Custom repositories**, add
   `https://github.com/jasonjhofmann/visiblair-homeassistant` as type
   **Integration**.
2. Search HACS for **VisiblAir** and download it.
3. Restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → VisiblAir**.

### Manual

1. Copy `custom_components/visiblair/` to `<config>/custom_components/`.
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → VisiblAir**.

## Setup

You add **one HA config entry per sensor**. For each one you need its
**MAC address** and **viewToken** — both visible in the VisiblAir cloud
portal's "Public view" share link for that sensor:

```
https://public.visiblair.com/index.html?id=<MAC>&viewToken=<TOKEN>
                                          ^^^^^               ^^^^^
```

Paste those into the Add VisiblAir Sensor form. The integration
validates them against the live API before saving. Repeat for each
sensor.

To change a sensor's viewToken later (without removing it), use the
entry's **⋮ → Reconfigure** action.

## Removing the integration

This integration follows standard Home Assistant removal — no extra steps.

1. Go to **Settings → Devices & Services**.
2. Click the **VisiblAir** entry for the sensor you want to remove.
3. Use the **⋮** (three-dot) menu and choose **Delete**.

Deleting a config entry removes that sensor's device, all its entities, and
its stored credentials. To remove the integration's code as well, delete it
via **HACS → VisiblAir → ⋮ → Remove** (or delete
`custom_components/visiblair/` for a manual install) and restart Home
Assistant. Nothing is written to your VisiblAir account — the integration is
read-only.

## What you get per sensor

| Category | Entities |
|---|---|
| Environmental | CO₂, temperature, humidity, VOC index, atmospheric pressure |
| Particulate matter | PM 0.1, 0.3, 0.5, 1, 2.5, 4, 5, 10 µm (8 entities; HA device classes on PM 1/2.5/10) |
| Power | battery (%), AC connected, charging |
| Diagnostic | firmware version, last sample, last calibration, battery voltage |
| Hardware health | PM fan fail, laser fail, RHT error, gas-sensor error, fan-speed warning, fan cleaning |

All entities have proper device classes, units, and state classes —
HA's long-term statistics, energy/air-quality dashboards, and graph
extrapolation all work out of the box.

## Use cases

- **Air-quality dashboards & alerts** — CO₂, PM 2.5, VOC index, temperature
  and humidity feed HA's air-quality cards and threshold automations.
- **Ventilation control** — drive a fan or ERV from CO₂ / PM 2.5.
- **Sensor-fleet health** — battery %, AC/charging state, and the PM
  fan/laser/sensor fault flags let you alert before a sensor degrades.

## Example automations

Notify when CO₂ climbs above 1000 ppm:

```yaml
automation:
  - alias: "High CO₂ — Living Room"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.living_room_co2
        above: 1000
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "Living Room CO₂ is {{ states('sensor.living_room_co2') }} ppm."
```

Alert on a PM-subsystem fault (a fan/laser problem flag turning on):

```yaml
automation:
  - alias: "VisiblAir sensor fault"
    triggers:
      - trigger: state
        entity_id: binary_sensor.living_room_pm_fan_fail
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "A VisiblAir PM sensor reported a fault."
```

## Polling

Polled at a fixed **60-second cadence**, matching VisiblAir sensors'
factory sample rate. Not user-configurable per HA Core conventions —
the integration owns its cadence.

## Why cloud-only

VisiblAir sensors expose an optional **Local API** at
`http://co2click-<MAC-suffix>.local:8080/state` that would be the
obviously-better target for a LAN-resident HA install — same data,
no cloud round-trip. **It is not viable on current firmware (1.7.2).**
Enabling the Local API toggle in the sensor's configuration menu causes
the sensor to disconnect from the VisiblAir cloud and loop endlessly
trying to upload data, requiring a physical power cycle to recover.

This integration adds a local mode the moment VisiblAir fixes the
firmware. Until then: cloud-only.

## Known limitations

- **Cloud-only.** Requires internet access and a cloud-synced sensor; the
  on-device Local API isn't usable on current firmware (see above).
- **Read-only.** Only the public viewer endpoint is used — you can't change
  sensor settings from Home Assistant.
- **Fixed 60 s cadence.** Sub-minute resolution isn't available (and the
  sensor's own sample rate wouldn't supply it).
- **Niche PM sizes disabled by default.** PM 0.1/0.3/0.5/4.0/5.0 µm and the
  battery-voltage diagnostic are off by default — enable them per entity if
  you want them. PM 1/2.5/10 µm are on.
- **One config entry per sensor.** Each sensor is added individually with its
  own MAC + viewToken.

## Quality bar

This integration aims to be public-grade reference quality:

- **Defensive parsing.** The cloud API returns `200 OK` with an empty
  body for any URL that isn't an exact route match — a trap for
  developers who think they've discovered an endpoint. We treat empty
  body as failure regardless of HTTP status, parse JSON without
  trusting the (mis-stated) `text/plain` Content-Type, and explicitly
  handle the Go-style `{"Float64": x, "Valid": false}` nullable-numeric
  wrappers so absent values become `None`, not zero.
- **Description-driven entities.** All 26 entities are generated from
  one table; adding a new field VisiblAir starts reporting is a
  one-row change, kept honest by a wiring-map completeness test that
  fails if you forget.
- **Lint + type-check + test gates.** ruff (lint + format), mypy strict,
  and pytest (with a ≥95% coverage gate) run on every push to main and
  every PR via GitHub Actions. The suite covers the config / reauth /
  reconfigure flows, entity states, the API HTTP layer + normaliser quirks,
  and diagnostics redaction — at 100% line coverage.
- **Frozen architecture record.** See [docs/architecture.md](docs/architecture.md)
  for the API surface, the catch-all trap, the local-API firmware bug
  details, the entity map, and every design decision.

## Diagnostics

The integration tile has a **Download diagnostics** action that produces
a sanitised JSON snapshot you can paste into a bug report. The
`viewToken`, the sensor's MAC address, and all other
potentially-sensitive fields are auto-redacted; safe to share publicly.

## Compatibility

- **Home Assistant 2025.1.0+** (declared in `hacs.json`)
- **VisiblAir Model E** firmware 1.7.2 confirmed in production
- **VisiblAir Model E-Lite** should work — open an issue if it doesn't

## Troubleshooting

**"MAC + viewToken was rejected"** — re-copy both values from a fresh
Public-view link in the VisiblAir portal; the viewToken rotates. If it
changed, the integration shows a reauthentication prompt (or use **⋮ →
Reconfigure**).

**Entities show `unavailable`** — open **Download diagnostics** and check
`coordinator.last_update_success`. A sensor that's offline or out of cloud
sync stops returning data; the credentials are auto-redacted in the dump.

**Enabling debug logs** — add this to `configuration.yaml` and restart (or
call the `logger.set_level` service for a no-restart change):

```yaml
logger:
  logs:
    custom_components.visiblair: debug
```

At `debug` you'll see, in `Settings → System → Logs`:

- **Setup** — the sensor name, MAC, and poll interval.
- **Each poll** — `Polled <MAC>: CO2=… PM2.5=… battery=…` once per cycle, so
  you can confirm data is flowing.
- **Errors** — API transport/parse failures (coordinator failures are logged
  once on failure and once on recovery, HA's standard behaviour).

The viewToken is **never** logged at any level.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, the local lint
& test commands, and the "add a new entity" recipe.

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Related projects

- [aranet-cloud-homeassistant](https://github.com/jasonjhofmann/aranet-cloud-homeassistant)
  — sibling integration for Aranet Cloud sensors, same author, same design ethos.
