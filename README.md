# VisiblAir for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Async, read-only Home Assistant integration for the
[VisiblAir](https://visiblair.com/) air-quality sensor cloud API.

Brings CO₂, temperature, humidity, VOC index, atmospheric pressure,
full-spectrum particulate matter (PM 0.1–10 µm), battery state and
sensor-health flags into Home Assistant for any VisiblAir sensor you
have a "Public view" share link for.

## Status

**Phase 0 (architecture)** — repo scaffolded, API surface mapped, design
decisions locked. Integration code lands in Phase 1.

See [docs/architecture.md](docs/architecture.md) for the full design,
including a frozen record of what the VisiblAir cloud API does and does
not expose.

## Features

Once Phase 1 ships:

- **One HA device per sensor**, configured by pasting (MAC, viewToken)
  from the VisiblAir cloud portal's "Public view" link
- **Every metric** the sensor reports, as standard HA sensor entities
  with correct device classes and units
- **Power state** (AC connected, charging) and **hardware-health flags**
  (PM fan/laser/RHT/gas-sensor errors, fan cleaning, fan-speed warning)
  as binary sensors
- **Diagnostic sensors** for firmware, last-calibration, last-sample
- **Configurable poll cadence** (30–600 s) per sensor via options flow
- **Reauth flow** for regenerated viewTokens
- **Diagnostics download** with credentials auto-redacted

## Why this integration exists

VisiblAir sells air-quality sensors with a clean public REST API for
reading the latest sample, but they do not ship a Home Assistant
integration. This fills that gap with a public-grade implementation:
defensive parsing, every metric mapped, exhaustive documentation of the
upstream API's quirks, no shortcuts.

## Why cloud-only

The VisiblAir hardware exposes an optional Local API
(`http://co2click-AABBCC.local:8080/state` with `Authorization: Bearer
<UUID>`) which would be the obviously-better target for a LAN-resident
HA install. **It is not viable on current firmware (1.7.2).** Enabling
the Local API toggle in the sensor's configuration menu causes the
sensor to disconnect from the VisiblAir cloud and loop endlessly trying
to upload data. If VisiblAir fixes the firmware, this integration will
add a local mode; until then, cloud-only.

## Installation

(Phase 4 will fill this in with HACS install instructions. For now,
this integration is not yet installable.)

## Configuration

Per sensor, you need:

1. The sensor's **Wi-Fi MAC address** (colon-separated, e.g.
   `AA:BB:CC:DD:EE:FF`)
2. The sensor's **viewToken** (an 8-character hex string from the
   VisiblAir portal's "Public view" page for that sensor)

Both values appear in the public viewer URL VisiblAir generates:
`https://public.visiblair.com/index.html?id=<MAC>&viewToken=<TOKEN>`

Each sensor is its own HA config entry. Add as many as you have.

## Compatibility

- **Home Assistant 2024.12.0+** (declared in `hacs.json`)
- **VisiblAir Model E** firmware 1.7.2 confirmed
- **VisiblAir Model E-Lite** should work but unconfirmed

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Related projects

- [aranet-cloud-homeassistant](https://github.com/jasonjhofmann/aranet-cloud-homeassistant)
  — sibling integration for Aranet Cloud sensors, same author, same design ethos
