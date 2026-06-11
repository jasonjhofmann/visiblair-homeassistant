"""Sensor + diagnostic entities for a VisiblAir sensor.

Driven by :data:`SENSOR_DESCRIPTIONS` — one row per metric exposed to HA.
Adding a new field that VisiblAir starts reporting is a one-row change.

Diagnostic entities (firmware version, last-calibration timestamp, last-
sample timestamp, battery voltage) are co-located here with
``entity_category=EntityCategory.DIAGNOSTIC`` rather than split into a
separate platform — this matches modern HA convention (diagnostic
sensors are sensors, not their own platform).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import VisiblAirSensorData
from .const import DOMAIN, MANUFACTURER
from .coordinator import VisiblAirCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import VisiblAirConfigEntry

# Coordinator-backed, read-only entities — no per-entity update fan-out.
# 0 = unlimited (the coordinator already serialises the single fetch).
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class VisiblAirSensorEntityDescription(SensorEntityDescription):
    """Sensor description with a typed value extractor.

    ``value_fn`` pulls the relevant attribute off a
    :class:`~.api.VisiblAirSensorData` snapshot. Returning ``None`` is
    legitimate for fields the device doesn't populate (e.g. the wind
    sensors on indoor model E variants) — HA renders these as
    ``unavailable`` rather than crashing.
    """

    value_fn: Callable[[VisiblAirSensorData], Any]


# Particulate-matter device-class mapping.
#
# HA exposes device classes only for PM 1.0, 2.5, and 10.0 µm. The other PM
# sizes VisiblAir reports (0.1, 0.3, 0.5, 4.0, 5.0 µm) get no device class
# — they still graph and record fine, just without HA's built-in icon/colour
# semantics.
#
# *NB:* the API names are decimal-position-encoded — `pm10` in the API is
# PM 1.0 µm, `pm100` is PM 10.0 µm. We standardise on `pm_X_Y` entity keys
# (entity-id will be e.g. `..._pm_2_5`) for unambiguous display.
SENSOR_DESCRIPTIONS: tuple[VisiblAirSensorEntityDescription, ...] = (
    # ---- environmental gauges --------------------------------------------
    VisiblAirSensorEntityDescription(
        key="co2",
        translation_key="co2",
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        suggested_display_precision=0,
        value_fn=lambda d: d.co2_ppm,
    ),
    VisiblAirSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda d: d.temperature_c,
    ),
    VisiblAirSensorEntityDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda d: d.humidity_pct,
    ),
    VisiblAirSensorEntityDescription(
        key="voc_index",
        translation_key="voc_index",
        # Sensirion VOC index is a unitless 0–500 scale (relative). No HA
        # device class is a perfect fit — `AQI` is close in spirit but
        # implies a published scale, which VOC index isn't.
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.voc_index,
    ),
    VisiblAirSensorEntityDescription(
        key="pressure",
        translation_key="pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.HPA,
        suggested_display_precision=1,
        value_fn=lambda d: d.pressure_hpa,
    ),
    # ---- particulate matter ----------------------------------------------
    VisiblAirSensorEntityDescription(
        key="pm_0_1",
        translation_key="pm_0_1",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=2,
        # Niche PM size — off by default; PM1/2.5/10 are the standard ones.
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.pm_0_1_um,
    ),
    VisiblAirSensorEntityDescription(
        key="pm_0_3",
        translation_key="pm_0_3",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.pm_0_3_um,
    ),
    VisiblAirSensorEntityDescription(
        key="pm_0_5",
        translation_key="pm_0_5",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.pm_0_5_um,
    ),
    VisiblAirSensorEntityDescription(
        key="pm_1_0",
        translation_key="pm_1_0",
        device_class=SensorDeviceClass.PM1,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=2,
        value_fn=lambda d: d.pm_1_0_um,
    ),
    VisiblAirSensorEntityDescription(
        key="pm_2_5",
        translation_key="pm_2_5",
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=2,
        value_fn=lambda d: d.pm_2_5_um,
    ),
    VisiblAirSensorEntityDescription(
        key="pm_4_0",
        translation_key="pm_4_0",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.pm_4_0_um,
    ),
    VisiblAirSensorEntityDescription(
        key="pm_5_0",
        translation_key="pm_5_0",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.pm_5_0_um,
    ),
    VisiblAirSensorEntityDescription(
        key="pm_10_0",
        translation_key="pm_10_0",
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=2,
        value_fn=lambda d: d.pm_10_0_um,
    ),
    # ---- power -----------------------------------------------------------
    VisiblAirSensorEntityDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda d: d.battery_pct,
    ),
    # ---- diagnostic ------------------------------------------------------
    VisiblAirSensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        # Diagnostic detail — off by default; the battery % is the primary one.
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.battery_voltage,
    ),
    VisiblAirSensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.firmware_version or None,
    ),
    VisiblAirSensorEntityDescription(
        key="last_sample",
        translation_key="last_sample",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.last_sample_at,
    ),
    VisiblAirSensorEntityDescription(
        key="last_calibration",
        translation_key="last_calibration",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.last_calibration_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VisiblAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register every sensor entity defined in SENSOR_DESCRIPTIONS."""
    coordinator = entry.runtime_data
    async_add_entities(
        VisiblAirSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


class VisiblAirSensor(CoordinatorEntity[VisiblAirCoordinator], SensorEntity):
    """One metric from a VisiblAir sensor's latest reading."""

    _attr_has_entity_name = True
    entity_description: VisiblAirSensorEntityDescription

    def __init__(
        self,
        coordinator: VisiblAirCoordinator,
        description: VisiblAirSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        # unique_id derives from the entry's canonical (uppercase) MAC,
        # NOT the cloud-echoed coordinator.data.uuid — identical bytes
        # today, but immune to a cloud-side casing change orphaning
        # every registered entity.
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.canonical_uuid}_{description.key}"
        )
        self._attr_device_info = device_info_for(coordinator.data)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)


def device_info_for(data: VisiblAirSensorData) -> DeviceInfo:
    """Shared DeviceInfo factory — imported by binary_sensor.py too.

    The MAC is the sensor's UUID; ``format_mac`` canonicalises to HA's
    standard lowercase colon-separated form so DHCP/Zeroconf discovery
    from other integrations can match this device.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, data.uuid)},
        name=data.description or f"VisiblAir {data.uuid}",
        manufacturer=MANUFACTURER,
        model=f"Model {data.model}" if data.model else None,
        sw_version=data.firmware_version or None,
        connections={(CONNECTION_NETWORK_MAC, format_mac(data.uuid))},
    )


__all__ = [
    "SENSOR_DESCRIPTIONS",
    "VisiblAirSensor",
    "VisiblAirSensorEntityDescription",
    "device_info_for",
]
