"""Binary sensors for Kermi x-center."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import KermiDeviceData
from .const import (
    DEVICE_TYPE_BUFFER,
    DEVICE_TYPE_HEAT_PUMP,
    DEVICE_TYPE_IFM,
)
from .coordinator import KermiConfigEntry
from .entity import KermiEntity


def _lookup(device: KermiDeviceData, wkn: str) -> Any:
    return device.values.get(wkn)


@dataclass(frozen=True, kw_only=True)
class KermiBinaryDescription(BinarySensorEntityDescription):
    wkn: str
    device_types: tuple[int, ...] = ()


BINARY_SENSORS: tuple[KermiBinaryDescription, ...] = (
    KermiBinaryDescription(
        key="is_heating",
        translation_key="is_heating",
        wkn="Rubin_IsHeatingState",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    KermiBinaryDescription(
        key="is_dhw",
        translation_key="is_dhw",
        wkn="Rubin_IsTweState",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    KermiBinaryDescription(
        key="is_cooling",
        translation_key="is_cooling",
        wkn="Rubin_IsCoolingState",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
    ),
    KermiBinaryDescription(
        key="is_defrosting",
        translation_key="is_defrosting",
        wkn="Rubin_IsDefrostingState",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        icon="mdi:snowflake-melt",
    ),
    KermiBinaryDescription(
        key="charging_pump",
        translation_key="charging_pump",
        wkn="Rubin_StorageChargingPumpState",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
    ),
    KermiBinaryDescription(
        key="pv_modulation",
        translation_key="pv_modulation",
        wkn="Rubin_PvIsActive",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        icon="mdi:solar-power",
    ),
    KermiBinaryDescription(
        key="summer_mode",
        translation_key="summer_mode",
        wkn="HeatingCircuit_SummerMode",
        device_types=(DEVICE_TYPE_BUFFER,),
        icon="mdi:weather-sunny",
    ),
    KermiBinaryDescription(
        key="dhw_oneshot",
        translation_key="dhw_oneshot",
        wkn="BufferSystem_OneTimeTwe",
        device_types=(DEVICE_TYPE_BUFFER,),
        icon="mdi:water-boiler",
    ),
    KermiBinaryDescription(
        key="heater_pv",
        translation_key="heater_pv",
        wkn="BufferSystem_HeaterIsPVActive",
        device_types=(DEVICE_TYPE_BUFFER,),
        entity_registry_enabled_default=False,
        icon="mdi:solar-power",
    ),
    KermiBinaryDescription(
        key="evu_lock",
        translation_key="evu_lock",
        wkn="DH_SGReady1",
        device_types=(DEVICE_TYPE_IFM,),
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:transmission-tower-off",
    ),
    KermiBinaryDescription(
        key="presence",
        translation_key="presence",
        wkn="System_IsPresent",
        device_types=(DEVICE_TYPE_IFM,),
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[KermiBinarySensor] = []
    for device_id, device in coordinator.data.items():
        for description in BINARY_SENSORS:
            if description.device_types and device.device_type not in description.device_types:
                continue
            if description.wkn not in device.values:
                continue
            entities.append(KermiBinarySensor(coordinator, device_id, description))
    async_add_entities(entities)


class KermiBinarySensor(KermiEntity, BinarySensorEntity):
    entity_description: KermiBinaryDescription

    def __init__(self, coordinator, device_id: str, description: KermiBinaryDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        device = self.device_data
        if device is None:
            return None
        value = _lookup(device, self.entity_description.wkn)
        if value is None:
            return None
        return bool(value)
