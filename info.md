# VisiblAir

Home Assistant integration for [VisiblAir](https://visiblair.com/) air-quality
sensors via the public Cloud REST API. Brings CO₂, temperature, humidity, VOC,
pressure, full-spectrum particulate matter (PM 0.1–10 µm), battery state and
sensor health into Home Assistant for any VisiblAir sensor you have a
"Public view" share link for.

## What it does

- One Home Assistant device per sensor, configured by pasting its (MAC,
  viewToken) pair from the VisiblAir cloud portal's "Public view" feature
- Exposes every metric the sensor reports as standard `sensor` entities:
  CO₂, temperature, humidity, VOC index, atmospheric pressure, particulate
  matter at every reported size (PM 0.1, 0.3, 0.5, 1, 2.5, 4, 5, 10 µm),
  battery percentage
- Surfaces power state (AC connected, charging) and hardware-health flags
  (fan failure, laser failure, RHT error, gas-sensor error, fan cleaning,
  fan-speed warning) as `binary_sensor` entities
- Diagnostic sensors for firmware version, last-calibration timestamp,
  last-sample timestamp
- Configurable poll cadence (30–600 s) per sensor
- Reauth flow if a sensor's viewToken is regenerated
- Diagnostics download with credentials auto-redacted

## What it doesn't do

- **Write** anything to your sensors. The Cloud REST API is read-only.
- Use the Local API. VisiblAir's optional Local API endpoint
  (`http://co2click-AABBCC.local:8080/state`) is **not viable on current
  firmware** — enabling it causes the sensor to disconnect from the cloud
  and loop endlessly trying to upload data. Cloud-only until VisiblAir
  fixes the firmware.
- Auto-discover. The Cloud API has no list/enumerate endpoint, so each
  sensor must be added explicitly with its (MAC, viewToken) pair.

## Setup

Per sensor, you need:

1. The sensor's **Wi-Fi MAC address** (colon-separated, e.g. `30:C6:F7:25:C4:A0`)
2. The sensor's **viewToken** (an 8-character hex string from the VisiblAir
   portal's "Public view" page for that sensor)

Both values appear in the public viewer URL VisiblAir generates:
`https://public.visiblair.com/index.html?id=<MAC>&viewToken=<TOKEN>`

Paste the MAC and viewToken into the integration's Add Sensor form. Repeat
for each additional sensor.

## Supported hardware

Tested end-to-end against VisiblAir Model E (firmware 1.7.2). Should work
with E-Lite as well — open an issue if you have one and it doesn't.

## More information

- [README](README.md)
- [Changelog](CHANGELOG.md)
- [Architecture doc](docs/architecture.md)
