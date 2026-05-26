"""Binary-sensor entities — power state + hardware-health flags.

Two flavours:

* **Power state** — `ac_connected`, `charging`. User-relevant; not diagnostic.
* **Hardware health** — fan/laser/sensor fault flags reported by the PM
  subsystem. All flagged ``entity_category=DIAGNOSTIC`` so they live in
  the Diagnostic section of the device page.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import VisiblAirSensorData
from .const import DOMAIN
from .coordinator import VisiblAirCoordinator
from .sensor import device_info_for

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import VisiblAirConfigEntry


@dataclass(frozen=True, kw_only=True)
class VisiblAirBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary-sensor description with a typed boolean extractor."""

    value_fn: Callable[[VisiblAirSensorData], bool]


BINARY_SENSOR_DESCRIPTIONS: tuple[VisiblAirBinarySensorEntityDescription, ...] = (
    # ---- power state -----------------------------------------------------
    VisiblAirBinarySensorEntityDescription(
        key="ac_connected",
        translation_key="ac_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda d: d.ac_connected,
    ),
    VisiblAirBinarySensorEntityDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.charging,
    ),
    # ---- hardware health (diagnostic) ------------------------------------
    VisiblAirBinarySensorEntityDescription(
        key="pm_fan_fail",
        translation_key="pm_fan_fail",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.pm_fan_fail,
    ),
    VisiblAirBinarySensorEntityDescription(
        key="pm_laser_fail",
        translation_key="pm_laser_fail",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.pm_laser_fail,
    ),
    VisiblAirBinarySensorEntityDescription(
        key="pm_rht_error",
        translation_key="pm_rht_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.pm_rht_error,
    ),
    VisiblAirBinarySensorEntityDescription(
        key="pm_gas_sensor_error",
        translation_key="pm_gas_sensor_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.pm_gas_sensor_error,
    ),
    VisiblAirBinarySensorEntityDescription(
        key="pm_fan_cleaning",
        translation_key="pm_fan_cleaning",
        # No device class — this is informational (sensor is doing routine
        # housekeeping), not a problem.
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:fan-clock",
        value_fn=lambda d: d.pm_fan_cleaning,
    ),
    VisiblAirBinarySensorEntityDescription(
        key="pm_fan_speed_warning",
        translation_key="pm_fan_speed_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.pm_fan_speed_warning,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VisiblAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register every binary-sensor entity defined in BINARY_SENSOR_DESCRIPTIONS."""
    coordinator = entry.runtime_data
    async_add_entities(
        VisiblAirBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class VisiblAirBinarySensor(
    CoordinatorEntity[VisiblAirCoordinator], BinarySensorEntity
):
    """A single boolean health/power flag for a VisiblAir sensor."""

    _attr_has_entity_name = True
    entity_description: VisiblAirBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: VisiblAirCoordinator,
        description: VisiblAirBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        data = coordinator.data
        self._attr_unique_id = f"{DOMAIN}_{data.uuid}_{description.key}"
        self._attr_device_info = device_info_for(data)

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)
