# VisiblAir for Home Assistant

<img src="https://raw.githubusercontent.com/jasonjhofmann/visiblair-homeassistant/main/custom_components/visiblair/brand/logo@2x.png" alt="VisiblAir" width="300">

[![release](https://img.shields.io/github/v/release/jasonjhofmann/visiblair-homeassistant?label=release&color=blue)](https://github.com/jasonjhofmann/visiblair-homeassistant/releases)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://hacs.xyz/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![CI](https://github.com/jasonjhofmann/visiblair-homeassistant/actions/workflows/ci.yml/badge.svg)](https://github.com/jasonjhofmann/visiblair-homeassistant/actions/workflows/ci.yml)

Read your [VisiblAir](https://visiblair.com/) air-quality sensors into Home
Assistant through the VisiblAir cloud API.

Each sensor becomes one Home Assistant device with 26 entities: carbon dioxide
(CO₂), temperature, humidity, volatile organic compound (VOC) index,
atmospheric pressure, the full particulate matter (PM) spectrum from 0.1 to
10 µm, battery and charge state, and diagnostics for firmware, sample times,
and the hardware fault flags the sensor reports about itself.

The integration is read-only. It calls the public viewer endpoint and writes
nothing to your VisiblAir account.

> Unofficial. Not affiliated with or endorsed by VisiblAir.

## Before you begin

You need the following:

- Home Assistant 2026.7.0 or later. That release introduced the
  `UnitOfDensity` and `UnitOfRatio` enums this integration uses, and it
  requires Python 3.14.
- A VisiblAir sensor that's powered on and syncing to the VisiblAir cloud.
- The sensor's MAC address and viewToken, which both appear in the sensor's
  Public view link.

Firmware 1.7.2 on the VisiblAir Model E is confirmed in production. The Model
E-Lite should work as well. If it doesn't,
[open an issue](https://github.com/jasonjhofmann/visiblair-homeassistant/issues).

## Install

### Install with HACS

VisiblAir is in the HACS default repository, so you don't need to add a custom
repository.

1. In HACS, search for **VisiblAir** and download it.
2. Restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jasonjhofmann&repository=visiblair-homeassistant&category=integration)

### Install manually

1. Copy `custom_components/visiblair/` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Add a sensor

Each sensor is its own config entry, so repeat these steps for every sensor you
want in Home Assistant.

1. In the VisiblAir portal, open the **Public view** share link for the sensor.
   The URL contains the two values you need:

   ```text
   https://public.visiblair.com/index.html?id=<MAC>&viewToken=<TOKEN>
   ```

2. In Home Assistant, go to **Settings > Devices & services > Add integration**
   and select **VisiblAir**.
3. Paste the `id=` value into **MAC address** and the `viewToken=` value into
   **viewToken**.
4. Click **Submit**.

Home Assistant validates both values against the live API before it saves the
entry, so a typo fails immediately instead of producing a dead device.

Treat the viewToken like a password. It grants read access to that sensor's
data, and the integration never writes it to the log at any level.

### Replace a viewToken

VisiblAir rotates viewTokens. When the current token stops working, Home
Assistant starts a reauthentication flow and prompts you for a new one.

To replace a token before it fails, select **⋮ > Reconfigure** on the config
entry and paste the new value. A config entry's MAC address is fixed, so use a
new entry if you want to track a different sensor.

## Entities

| Category | Entities |
| --- | --- |
| Environmental | CO₂, temperature, humidity, VOC index, atmospheric pressure |
| Particulate matter | PM 0.1, 0.3, 0.5, 1, 2.5, 4, 5, and 10 µm (8 entities) |
| Power | Battery percentage, AC connected, charging |
| Diagnostic | Firmware version, last sample, last calibration, battery voltage |
| Hardware health | PM fan fail, laser fail, RHT error, gas-sensor error, fan-speed warning, fan cleaning |

Every entity carries units, a state class, and a device class where Home
Assistant has one, so long-term statistics and the air-quality dashboard cards
work without extra configuration. Device classes exist for PM 1, PM 2.5, and
PM 10; the other five PM sizes report in µg/m³ without one.

Six entities are disabled by default: PM 0.1, 0.3, 0.5, 4, and 5 µm, and the
battery-voltage diagnostic. Enable any of them from the entity's settings if
you want them.

## Automation examples

Notify when CO₂ climbs above 1000 ppm:

```yaml
automation:
  - alias: "High CO2 in the living room"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.living_room_co2
        above: 1000
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "Living room CO2 is {{ states('sensor.living_room_co2') }} ppm."
```

Notify when the PM subsystem reports a fault:

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

## How data is updated

The integration polls the cloud every 60 seconds, which matches the factory
sample rate of a VisiblAir sensor. The cadence is fixed and isn't
user-configurable, following Home Assistant Core convention.

### Stale readings go unavailable

When a sensor powers off, the VisiblAir cloud keeps serving its last cached
reading. The poll still succeeds, so a successful fetch on its own doesn't
prove the value is current.

To handle that, every measurement and health entity goes `unavailable` once the
sample behind it is more than 15 minutes old. A powered-off sensor stops
reporting a frozen value as if it were live, and anything downstream stops
trusting it.

The firmware version, last sample, and last calibration entities are exempt
from the gate. They stay available so you can see how old the data is.

## Why there's no local mode

VisiblAir sensors expose an optional local API at
`http://co2click-<MAC-suffix>.local:8080/state`. For a LAN-resident Home
Assistant install that's the better target: same data, no cloud round trip.

It isn't usable on firmware 1.7.2. Turning on the Local API toggle in the
sensor's configuration menu makes the sensor drop its cloud connection and loop
forever trying to upload, and only a physical power cycle recovers it.

This integration will add a local mode once VisiblAir fixes the firmware. Until
then it's cloud-only.

## Limitations

- **Cloud-only.** You need internet access and a cloud-synced sensor. The
  on-device local API isn't usable on current firmware.
- **Read-only.** The integration uses the public viewer endpoint, so you can't
  change sensor settings from Home Assistant.
- **Fixed 60-second cadence.** Sub-minute resolution isn't available, and the
  sensor's own sample rate wouldn't supply it.
- **No discovery.** The cloud API has no endpoint that lists the sensors on an
  account, so each one has to be added by hand with its own MAC address and
  viewToken. That's also why there's one config entry per sensor.

## Troubleshoot

### The MAC address or viewToken was rejected

Copy both values again from a fresh Public view link in the VisiblAir portal.
The viewToken rotates. If it has changed, Home Assistant shows a
reauthentication prompt, or you can use **⋮ > Reconfigure**.

### Entities show `unavailable`

Two things cause this, and the diagnostics download tells you which:

- The poll itself failed. Check `coordinator.last_update_success` in the
  diagnostics JSON.
- The poll succeeded but the reading is stale. The sensor is off or out of
  cloud sync. Check the **Last sample** entity, which stays available.

### Download diagnostics

The integration tile has a **Download diagnostics** action that produces a
sanitized JSON snapshot for a bug report. The viewToken, the MAC address, and
every other sensitive field are redacted, so the file is safe to share
publicly.

### Turn on debug logging

Add the following to `configuration.yaml` and restart. To change the level
without restarting, call the `logger.set_level` action instead.

```yaml
logger:
  logs:
    custom_components.visiblair: debug
```

At `debug`, **Settings > System > Logs** shows:

- **Setup.** The sensor name, MAC address, and poll interval.
- **Each poll.** One `Polled <MAC>: CO2=… PM2.5=… battery=…` line per cycle, so
  you can confirm data is flowing.
- **Errors.** API transport and parse failures. Coordinator failures are logged
  once when they start and once when they recover, which is standard Home
  Assistant behavior.

## How the integration is built

- **Defensive parsing.** The cloud API returns `200 OK` with an empty body for
  any URL that isn't an exact route match, so a URL that doesn't exist looks
  like a working endpoint. The integration treats an empty
  body as a failure whatever the status code, parses JSON without trusting the
  misdeclared `text/plain` content type, and unwraps the Go-style
  `{"Float64": x, "Valid": false}` nullable numerics so an absent value becomes
  `None` instead of zero.
- **Description-driven entities.** All 26 entities come from one table. Adding
  a field that VisiblAir starts reporting is a one-row change, and a
  completeness test fails the build if the wiring is missed.
- **Enforced quality gates.** ruff (lint and format), mypy in strict mode, and
  pytest with a 95% coverage floor run on every push to `main` and every pull
  request. Actual line coverage is 100%. The suite covers the config, reauth,
  and reconfigure flows, entity states, the HTTP layer and its normalizer
  quirks, and diagnostics redaction.
- **Architecture record.** [docs/architecture.md](docs/architecture.md)
  documents the API surface, the catch-all route trap, the local-API firmware
  bug, the entity map, and the design decisions behind each.

The integration targets the Platinum tier of the Home Assistant Integration
Quality Scale. See
[`custom_components/visiblair/quality_scale.yaml`](custom_components/visiblair/quality_scale.yaml)
for per-rule status.

## Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, the local lint
and test commands, and the recipe for adding an entity.

## License

Apache 2.0. See [LICENSE](LICENSE).

The VisiblAir logo is bundled at `custom_components/visiblair/brand/` and
served through Home Assistant's Brands Proxy API. "VisiblAir" is a trademark of
its owner.

## Related projects

- [aranet-cloud-homeassistant](https://github.com/jasonjhofmann/aranet-cloud-homeassistant)
  reads Aranet Cloud sensors into Home Assistant.
- [sensoredlife-homeassistant](https://github.com/jasonjhofmann/sensoredlife-homeassistant)
  reads SensoredLife MarCELL cellular monitors into Home Assistant.
