"""VisiblAir sensor platform.

Phase 1 ships a single proof-of-wire CO₂ entity. Phase 2 will extend
this with the full sensor surface (temperature, humidity, VOC, pressure,
all PM sizes, battery, battery voltage) plus the binary_sensor and
diagnostic platforms.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import VisiblAirCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import VisiblAirConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VisiblAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VisiblAir sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities([VisiblAirCO2Sensor(coordinator)])


class VisiblAirCO2Sensor(CoordinatorEntity[VisiblAirCoordinator], SensorEntity):
    """CO₂ concentration for a single VisiblAir sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "co2"
    _attr_device_class = SensorDeviceClass.CO2
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION

    def __init__(self, coordinator: VisiblAirCoordinator) -> None:
        super().__init__(coordinator)
        data = coordinator.data
        self._attr_unique_id = f"{data.uuid}_co2"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data.uuid)},
            name=data.description or f"VisiblAir {data.uuid}",
            manufacturer=MANUFACTURER,
            model=f"Model {data.model}" if data.model else None,
            sw_version=data.firmware_version or None,
            connections={("mac", data.uuid.lower())},
        )

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.co2_ppm
