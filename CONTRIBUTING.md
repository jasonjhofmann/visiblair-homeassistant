# Contributing

Issues and pull requests welcome — this integration is community-built.

## Reporting a bug

Open an issue with:

1. **The version of the integration** (visible on the integration tile,
   or in `manifest.json`).
2. **Your Home Assistant Core + OS version** (Settings → About).
3. **A diagnostics download** from the integration tile (⋮ menu →
   Download diagnostics). The viewToken is automatically redacted
   before the snapshot is built, so it's safe to paste verbatim.
4. **What you expected vs. what happened**, plus relevant log lines
   from Settings → System → Logs filtered to
   `custom_components.visiblair`.

## Suggesting an entity

If your VisiblAir sensor reports a metric the integration doesn't yet
expose — or you'd like an existing field surfaced differently —
open an issue with:

- A diagnostics download (see above) so we can see the raw payload shape
- What you expect the entity to look like (display name, device class,
  unit, state class)

Adding a new sensor or binary-sensor is almost always:

1. One new field on `VisiblAirSensorData` in
   `custom_components/visiblair/api.py` plus a normaliser line
2. One row in `SENSOR_DESCRIPTIONS` (or `BINARY_SENSOR_DESCRIPTIONS`)
3. One entry in `DATACLASS_FIELD_TO_ENTITY_KEY` in
   `tests/test_entities.py` (the test fails closed if you forget)
4. One translation key in `strings.json` *and* `translations/en.json`

## Development setup

```bash
git clone https://github.com/jasonjhofmann/visiblair-homeassistant
cd visiblair-homeassistant

# Run the test suite (uv handles the Python + dependency install).
# The tests use pytest-homeassistant-custom-component, which pulls in a
# pinned Home Assistant; CI gates coverage at >=95%.
uv run --python 3.13 --with pytest-homeassistant-custom-component --with pytest-cov \
  python -m pytest tests/ --cov=custom_components.visiblair --cov-report=term-missing

# Lint
uv run --python 3.13 --with ruff ruff check custom_components/ tests/
uv run --python 3.13 --with ruff ruff format --check custom_components/ tests/

# Type-check
uv run --python 3.13 --with mypy --with homeassistant --with aiohttp --with voluptuous \
  mypy custom_components/visiblair/
```

All three commands run on CI via `.github/workflows/ci.yml`. PRs need
to pass cleanly.

## Code style

- Modern HA patterns: `entry.runtime_data` (not `hass.data[DOMAIN][…]`),
  PEP 695 `type` statements (the project targets Python 3.13 to match
  HA Core), description-driven entity tables.
- Ruff and mypy strict are the gate. The pyproject.toml at the repo root
  has the exact configuration.
- Comments: only when WHY is non-obvious. Don't restate what the code does.

## Testing against a live HA box

```bash
# Copy the integration into your HA config dir
scp -r custom_components/visiblair root@<your-ha-host>:/homeassistant/custom_components/

# Restart Home Assistant (Settings → System → Restart, or)
ssh root@<your-ha-host> "ha core restart"
```

Then add a VisiblAir sensor via Settings → Devices & Services →
Add Integration → VisiblAir.

## License

Contributions are accepted under the same Apache 2.0 license as the rest
of the project.
