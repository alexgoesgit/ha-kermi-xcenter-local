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

from .auto import (
    KIND_BINARY,
    attributes,
    classify,
    curated_identifiers,
    is_problem,
    options_enabled,
    selectable,
)
from .client import KermiDatapoint, KermiDeviceData
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
    entities: list[BinarySensorEntity] = []
    for device_id, device in coordinator.data.items():
        for description in BINARY_SENSORS:
            if description.device_types and device.device_type not in description.device_types:
                continue
            if description.wkn not in device.values:
                continue
            entities.append(KermiBinarySensor(coordinator, device_id, description))

    create_all, include_settings = options_enabled(entry)
    if create_all:
        curated_wkns, curated_names = curated_identifiers()
        for device_id, device in coordinator.data.items():
            for datapoint in sorted(device.datapoints.values(), key=lambda dp: dp.sort):
                if classify(datapoint) != KIND_BINARY:
                    continue
                if not selectable(datapoint, curated_wkns, curated_names, include_settings):
                    continue
                entities.append(KermiAutoBinarySensor(coordinator, device_id, datapoint))

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


class KermiAutoBinarySensor(KermiEntity, BinarySensorEntity):
    """Any boolean datapoint without a curated description."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id: str, datapoint: KermiDatapoint) -> None:
        super().__init__(coordinator, device_id, f"dp_{datapoint.config_id}")
        self._config_id = datapoint.config_id
        self._attr_name = datapoint.name
        self._attr_extra_state_attributes = attributes(datapoint)
        if is_problem(datapoint):
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool | None:
        device = self.device_data
        if device is None:
            return None
        datapoint = device.datapoints.get(self._config_id)
        if datapoint is None or datapoint.value is None:
            return None
        value = datapoint.value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("ja", "ein", "true", "1"):
                return True
            if text in ("nein", "aus", "false", "0"):
                return False
            return None
        return bool(value)
