"""Sensor platform for Kermi x-center."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .client import KermiDeviceData
from .const import (
    DEVICE_TYPE_BUFFER,
    DEVICE_TYPE_FRESH_WATER,
    DEVICE_TYPE_HEAT_PUMP,
    DEVICE_TYPE_IFM,
    ENERGY_MODE_MAP,
    HP_STATE_MAP,
    HP_STATUS_COOLING,
    HP_STATUS_DEFROST,
    HP_STATUS_DHW,
    HP_STATUS_HEATING,
    HP_STATUS_STANDBY,
    SMART_GRID_MAP,
)
from .coordinator import KermiConfigEntry
from .entity import KermiEntity


def _lookup(device: KermiDeviceData, wkn: str | None, display_names: tuple[str, ...]) -> Any:
    if wkn and wkn in device.values:
        return device.values[wkn]
    for name in display_names:
        if name in device.display_values:
            return device.display_values[name]
    return None


def _hp_status(device: KermiDeviceData) -> str:
    values = device.values
    if values.get("Rubin_IsDefrostingState") or values.get("Rubin_IsDefrosting"):
        return HP_STATUS_DEFROST
    if values.get("Rubin_IsTweState"):
        return HP_STATUS_DHW
    if values.get("Rubin_IsHeatingState"):
        return HP_STATUS_HEATING
    if values.get("Rubin_IsCoolingState"):
        return HP_STATUS_COOLING
    return HP_STATUS_STANDBY


def _mapped(mapping: dict[int, str]) -> Callable[[KermiDeviceData, Any], Any]:
    def _fn(_device: KermiDeviceData, value: Any) -> Any:
        if value is None:
            return None
        try:
            return mapping.get(int(value), str(value))
        except (TypeError, ValueError):
            return str(value)

    return _fn


def _clean_temp(_device: KermiDeviceData, value: Any) -> Any:
    if not isinstance(value, (int, float)):
        return value
    if value < -60 or value > 200:
        return None
    return round(float(value), 1)


def _round(digits: int) -> Callable[[KermiDeviceData, Any], Any]:
    def _fn(_device: KermiDeviceData, value: Any) -> Any:
        if not isinstance(value, (int, float)):
            return value
        return round(float(value), digits)

    return _fn


@dataclass(frozen=True, kw_only=True)
class KermiSensorDescription(SensorEntityDescription):
    """Sensor metadata plus how to find the datapoint."""

    wkn: str | None = None
    display_names: tuple[str, ...] = ()
    device_types: tuple[int, ...] = ()
    value_fn: Callable[[KermiDeviceData], Any] | None = None
    convert_fn: Callable[[KermiDeviceData, Any], Any] | None = None


SENSORS: tuple[KermiSensorDescription, ...] = (
    # Heat pump
    KermiSensorDescription(
        key="hp_status",
        translation_key="hp_status",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.ENUM,
        options=[
            HP_STATUS_STANDBY,
            HP_STATUS_HEATING,
            HP_STATUS_DHW,
            HP_STATUS_COOLING,
            HP_STATUS_DEFROST,
        ],
        value_fn=_hp_status,
        icon="mdi:heat-pump",
    ),
    KermiSensorDescription(
        key="hp_state",
        translation_key="hp_state",
        wkn="Rubin_CombinedHeatpumpState",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.ENUM,
        options=list(dict.fromkeys(HP_STATE_MAP.values())),
        convert_fn=_mapped(HP_STATE_MAP),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="outside_temp",
        translation_key="outside_temp",
        wkn="LuftTemperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_clean_temp,
    ),
    KermiSensorDescription(
        key="outside_temp_avg",
        translation_key="outside_temp_avg",
        wkn="Aussentemperatur_gemittelt",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="flow_temp",
        translation_key="flow_temp",
        wkn="Rubin_SecondaryOutletTemp",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="return_temp",
        translation_key="return_temp",
        wkn="Rubin_SecondaryInletTemp",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="electrical_power",
        translation_key="electrical_power",
        wkn="Rubin_CurrentPowerInverter",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        convert_fn=_round(3),
    ),
    KermiSensorDescription(
        key="thermal_power",
        translation_key="thermal_power",
        wkn="Rubin_CurrentOutputCapacity",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        convert_fn=_round(3),
    ),
    KermiSensorDescription(
        key="cop",
        translation_key="cop",
        wkn="Rubin_CurrentCOP",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        state_class=SensorStateClass.MEASUREMENT,
        convert_fn=_round(2),
        icon="mdi:chart-line",
    ),
    KermiSensorDescription(
        key="cop_heating",
        translation_key="cop_heating",
        wkn="Rubin_CurrentCOPHeating",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        state_class=SensorStateClass.MEASUREMENT,
        convert_fn=_round(2),
        icon="mdi:chart-line",
    ),
    KermiSensorDescription(
        key="cop_dhw",
        translation_key="cop_dhw",
        wkn="Rubin_CurrentCOPTwe",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        state_class=SensorStateClass.MEASUREMENT,
        convert_fn=_round(2),
        icon="mdi:chart-line",
    ),
    KermiSensorDescription(
        key="heating_power",
        translation_key="heating_power",
        wkn="Rubin_CurrentOutputCapacityHeating",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        convert_fn=_round(3),
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="dhw_power",
        translation_key="dhw_power",
        wkn="Rubin_CurrentOutputCapacityTwe",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        convert_fn=_round(3),
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="flow_rate",
        translation_key="flow_rate",
        wkn="Rubin_PulpActualValue",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="compressor_speed",
        translation_key="compressor_speed",
        wkn="Rubin_Link_Verdichterzahl",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="rps",
        convert_fn=_round(1),
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:fan",
    ),
    KermiSensorDescription(
        key="compressor_hours",
        translation_key="compressor_hours",
        wkn="Rubin_OperationHoursCompressor",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        convert_fn=_round(2),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    KermiSensorDescription(
        key="hot_gas_temp",
        translation_key="hot_gas_temp",
        wkn="Rubin_Link_B12_Heissgastemperatur",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="high_pressure",
        translation_key="high_pressure",
        wkn="Rubin_Link_P12_Hochdruck",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        convert_fn=_round(2),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="low_pressure",
        translation_key="low_pressure",
        wkn="Rubin_Link_P11_Niederdruck",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        convert_fn=_round(2),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="source_inlet_temp",
        translation_key="source_inlet_temp",
        wkn="Rubin_Link_B15_EnergiequellenEintrittstemperatur",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="source_outlet_temp",
        translation_key="source_outlet_temp",
        wkn="Rubin_Link_B14_EnergiequellenAustrittstemperatur",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="pv_available_power",
        translation_key="pv_available_power",
        wkn="Rubin_PvAvailablePower",
        device_types=(DEVICE_TYPE_HEAT_PUMP,),
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        convert_fn=_round(0),
        entity_registry_enabled_default=False,
    ),
    # Heating / DHW buffer
    KermiSensorDescription(
        key="buffer_temp",
        translation_key="buffer_temp",
        wkn="BufferSystem_HeatingTemperatureActual",
        device_types=(DEVICE_TYPE_BUFFER,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="buffer_setpoint",
        translation_key="buffer_setpoint",
        wkn="BufferSystem_HeatingSetpoint",
        device_types=(DEVICE_TYPE_BUFFER,),
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="dhw_temp",
        translation_key="dhw_temp",
        wkn="BufferSystem_TweTemperatureActual",
        device_types=(DEVICE_TYPE_BUFFER,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="dhw_setpoint",
        translation_key="dhw_setpoint",
        wkn="BufferSystem_TweSetpoint",
        device_types=(DEVICE_TYPE_BUFFER,),
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="heating_circuit_temp",
        translation_key="heating_circuit_temp",
        display_names=("Isttemperatur Heizkreis (Modul)",),
        device_types=(DEVICE_TYPE_BUFFER,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_clean_temp,
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="energy_mode",
        translation_key="energy_mode",
        wkn="HeatingCircuit_EnergyMode",
        device_types=(DEVICE_TYPE_BUFFER,),
        device_class=SensorDeviceClass.ENUM,
        options=list(ENERGY_MODE_MAP.values()),
        convert_fn=_mapped(ENERGY_MODE_MAP),
        icon="mdi:tune",
    ),
    KermiSensorDescription(
        key="heater_power",
        translation_key="heater_power",
        wkn="BufferSystem_HeaterRequestedElectricalPower",
        device_types=(DEVICE_TYPE_BUFFER,),
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        convert_fn=_round(0),
        entity_registry_enabled_default=False,
    ),
    KermiSensorDescription(
        key="mixer_position",
        translation_key="mixer_position",
        wkn="HeatingCircuit_MixerPosition",
        device_types=(DEVICE_TYPE_BUFFER,),
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        convert_fn=_round(0),
        entity_registry_enabled_default=False,
        icon="mdi:valve",
    ),
    # Fresh water station (many datapoints have no WellKnownName)
    KermiSensorDescription(
        key="freshwater_temp",
        translation_key="freshwater_temp",
        display_names=("Isttemperatur Warmwassertemperatur",),
        device_types=(DEVICE_TYPE_FRESH_WATER,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_clean_temp,
    ),
    KermiSensorDescription(
        key="freshwater_setpoint",
        translation_key="freshwater_setpoint",
        wkn="FriWaTurmalin_SetpointTemperature",
        device_types=(DEVICE_TYPE_FRESH_WATER,),
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="freshwater_power",
        translation_key="freshwater_power",
        display_names=("Aktuelle Zapfleistung",),
        device_types=(DEVICE_TYPE_FRESH_WATER,),
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        convert_fn=_round(2),
    ),
    KermiSensorDescription(
        key="freshwater_energy",
        translation_key="freshwater_energy",
        display_names=("Wärmemenge",),
        device_types=(DEVICE_TYPE_FRESH_WATER,),
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    KermiSensorDescription(
        key="freshwater_flow",
        translation_key="freshwater_flow",
        display_names=("Aktueller Durchfluss",),
        device_types=(DEVICE_TYPE_FRESH_WATER,),
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        convert_fn=_round(1),
    ),
    KermiSensorDescription(
        key="freshwater_circulation_temp",
        translation_key="freshwater_circulation_temp",
        display_names=("Isttemperatur Zirkulation",),
        device_types=(DEVICE_TYPE_FRESH_WATER,),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        convert_fn=_clean_temp,
        entity_registry_enabled_default=False,
    ),
    # IFM
    KermiSensorDescription(
        key="smart_grid",
        translation_key="smart_grid",
        wkn="DH_SmartGridState",
        device_types=(DEVICE_TYPE_IFM,),
        device_class=SensorDeviceClass.ENUM,
        options=list(dict.fromkeys(SMART_GRID_MAP.values())),
        convert_fn=_mapped(SMART_GRID_MAP),
        icon="mdi:transmission-tower",
    ),
)


def _applies(description: KermiSensorDescription, device: KermiDeviceData) -> bool:
    if description.device_types and device.device_type not in description.device_types:
        return False
    if description.value_fn is not None:
        return True
    return _lookup(device, description.wkn, description.display_names) is not None or bool(
        description.wkn and description.wkn in device.values
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[KermiSensor] = []
    for device_id, device in coordinator.data.items():
        for description in SENSORS:
            if _applies(description, device):
                entities.append(KermiSensor(coordinator, device_id, description))
    async_add_entities(entities)


class KermiSensor(KermiEntity, SensorEntity):
    """A single Kermi datapoint as a sensor."""

    entity_description: KermiSensorDescription

    def __init__(self, coordinator, device_id: str, description: KermiSensorDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        device = self.device_data
        if device is None:
            return None
        desc = self.entity_description
        if desc.value_fn is not None:
            value = desc.value_fn(device)
        else:
            value = _lookup(device, desc.wkn, desc.display_names)
        if desc.convert_fn is not None:
            value = desc.convert_fn(device, value)
        return value
