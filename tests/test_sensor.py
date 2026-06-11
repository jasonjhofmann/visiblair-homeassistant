"""Sensor platform tests — values, units, disabled-by-default, diagnostics."""

from __future__ import annotations

import dataclasses

import pytest
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.visiblair.api import VisiblAirSensorData
from custom_components.visiblair.const import CONF_UUID, CONF_VIEW_TOKEN, DOMAIN
from custom_components.visiblair.sensor import device_info_for

from .conftest import (
    TEST_VIEW_TOKEN,
    build_mock_api,
    setup_integration,
    state_for,
    uid,
)

# Keys disabled by default (niche PM sizes + battery_voltage).
DISABLED_KEYS = {
    "pm_0_1",
    "pm_0_3",
    "pm_0_5",
    "pm_4_0",
    "pm_5_0",
    "battery_voltage",
}


async def test_sensor_values_and_units(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Core gauges surface with the expected value and unit."""
    cases = [
        ("co2", 523, "ppm"),
        ("temperature", 22.7, "°C"),
        ("humidity", 32.0, "%"),
        ("pm_2_5", 0.563, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
    ]
    for key, value, unit in cases:
        state = state_for(hass, "sensor", key)
        assert state is not None
        assert float(state.state) == pytest.approx(value)
        assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == unit


async def test_disabled_by_default(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Niche PM sizes + battery voltage are registered but disabled."""
    ent_reg = er.async_get(hass)
    for key in DISABLED_KEYS:
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, uid(key))
        assert entity_id is not None, key
        assert (
            ent_reg.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        assert hass.states.get(entity_id) is None


async def test_entity_counts(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """18 sensor entities registered; the 6 disabled ones have no state."""
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, init_integration.entry_id)
    sensors = [e for e in entries if e.domain == "sensor"]
    assert len(sensors) == 18
    enabled = [e for e in sensors if e.disabled_by is None]
    assert len(enabled) == 18 - len(DISABLED_KEYS)


async def test_unique_id_uses_entry_canonical_mac(
    hass: HomeAssistant, sample_data: VisiblAirSensorData
) -> None:
    """unique_ids derive from the entry's canonical MAC — byte-identical to before.

    The cloud echoes the uuid in whatever casing it stores; if entities
    derived their unique_id from that echo, a cloud-side casing change
    would orphan every registered entity. Lock the exact format (so
    existing installs never migrate) and prove a lowercase cloud echo
    changes nothing.
    """
    # The exact pre-0.7.0 unique_id, locked byte-for-byte.
    assert uid("co2") == "visiblair_AA:BB:CC:DD:EE:FF_co2"

    # Simulate the cloud changing its casing: API data carries lowercase.
    lowered = dataclasses.replace(sample_data, uuid="aa:bb:cc:dd:ee:ff")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=lowered.description,
        data={CONF_UUID: "AA:BB:CC:DD:EE:FF", CONF_VIEW_TOKEN: TEST_VIEW_TOKEN},
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    await setup_integration(hass, entry, build_mock_api(lowered))

    ent_reg = er.async_get(hass)
    assert ent_reg.async_get_entity_id(
        "sensor", DOMAIN, "visiblair_AA:BB:CC:DD:EE:FF_co2"
    )
    assert ent_reg.async_get_entity_id(
        "binary_sensor", DOMAIN, "visiblair_AA:BB:CC:DD:EE:FF_pm_fan_fail"
    )


async def test_device_registry_key_literals(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Lock the exact registry-keying bytes DeviceInfo emits today.

    Existing installs key their device on these literal tuples — any
    change (casing included) mints a NEW device and orphans the old one,
    so they are asserted byte-for-byte, not derived.
    """
    device_info = device_info_for(init_integration.runtime_data)
    assert device_info["identifiers"] == {("visiblair", "AA:BB:CC:DD:EE:FF")}
    assert device_info["connections"] == {("mac", "aa:bb:cc:dd:ee:ff")}

    device_reg = dr.async_get(hass)
    device = device_reg.async_get_device(
        identifiers={("visiblair", "AA:BB:CC:DD:EE:FF")}
    )
    assert device is not None
    assert device.connections == {("mac", "aa:bb:cc:dd:ee:ff")}


async def test_device_info_survives_lowercase_cloud_echo(
    hass: HomeAssistant, sample_data: VisiblAirSensorData
) -> None:
    """A lowercase cloud echo yields the exact same DeviceInfo registry keys.

    Same hazard as entity unique_ids, device-registry edition: if
    identifiers/connections derived from the cloud-echoed ``data.uuid``,
    a cloud-side casing change would mint a NEW device and orphan the
    registered one. They derive from the entry's canonical MAC instead.
    """
    lowered = dataclasses.replace(sample_data, uuid="aa:bb:cc:dd:ee:ff")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=lowered.description,
        data={CONF_UUID: "AA:BB:CC:DD:EE:FF", CONF_VIEW_TOKEN: TEST_VIEW_TOKEN},
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    await setup_integration(hass, entry, build_mock_api(lowered))

    # Byte-identical to the uppercase-echo literals above.
    device_info = device_info_for(entry.runtime_data)
    assert device_info["identifiers"] == {("visiblair", "AA:BB:CC:DD:EE:FF")}
    assert device_info["connections"] == {("mac", "aa:bb:cc:dd:ee:ff")}

    # The registry holds exactly one device for the entry — keyed on the
    # canonical tuples — so the casing flip minted nothing new.
    device_reg = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    assert len(devices) == 1
    assert devices[0].identifiers == {("visiblair", "AA:BB:CC:DD:EE:FF")}
    assert ("mac", "aa:bb:cc:dd:ee:ff") in devices[0].connections


async def test_firmware_is_diagnostic(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The firmware version sensor reports the version as a diagnostic."""
    state = state_for(hass, "sensor", "firmware_version")
    assert state is not None
    assert state.state == "1.7.2"

    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, uid("firmware_version"))
    assert ent_reg.async_get(entity_id).entity_category is EntityCategory.DIAGNOSTIC
