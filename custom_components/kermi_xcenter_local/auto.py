"""Turn every x-center datapoint into an entity.

The curated descriptions in sensor.py / binary_sensor.py give the important
datapoints nice names, translations and device classes. Everything else is
classified here from the metadata the API already delivers: DatapointType,
Unit and PossibleValues.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)

from .client import KermiDatapoint
from .const import (
    CONF_ALL_DATAPOINTS,
    CONF_INCLUDE_SETTINGS,
    DEFAULT_ALL_DATAPOINTS,
    DEFAULT_INCLUDE_SETTINGS,
    DP_TYPE_BOOL,
    DP_TYPE_FLOAT,
    DP_TYPE_INT,
    DP_TYPE_STRING,
)

_LOGGER = logging.getLogger(__name__)

KIND_BINARY = "binary"
KIND_ENUM = "enum"
KIND_NUMERIC = "numeric"
KIND_TEXT = "text"

# Unit string from the API -> (device class, HA unit)
_UNITS: dict[str, tuple[SensorDeviceClass | None, str]] = {
    "°C": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "K": (None, "K"),  # temperature *difference*, not an absolute value
    "kW": (SensorDeviceClass.POWER, UnitOfPower.KILO_WATT),
    "W": (SensorDeviceClass.POWER, UnitOfPower.WATT),
    "kWh": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR),
    "Wh": (SensorDeviceClass.ENERGY, UnitOfEnergy.WATT_HOUR),
    "%": (None, PERCENTAGE),
    "h": (SensorDeviceClass.DURATION, UnitOfTime.HOURS),
    "min": (SensorDeviceClass.DURATION, UnitOfTime.MINUTES),
    "s": (SensorDeviceClass.DURATION, UnitOfTime.SECONDS),
    "bar": (SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    "l/min": (SensorDeviceClass.VOLUME_FLOW_RATE, UnitOfVolumeFlowRate.LITERS_PER_MINUTE),
    "V": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
    "A": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
    "Hz": (SensorDeviceClass.FREQUENCY, UnitOfFrequency.HERTZ),
    "rpm": (None, "rpm"),
    "rps": (None, "rps"),
}

# Monotonic counters: these must not be averaged in statistics.
_TOTAL_UNITS = {"h", "kWh", "Wh"}
_TOTAL_WORDS = ("betriebsstunden", "laufzeit", "anzahl", "wärmemenge", "starts")

_PROBLEM_WORDS = ("störung", "stoerung", "alarm", "fehler", "warnung")


def options_enabled(entry) -> tuple[bool, bool]:
    """Return (create all datapoints, include settings)."""
    opts = entry.options
    return (
        bool(opts.get(CONF_ALL_DATAPOINTS, DEFAULT_ALL_DATAPOINTS)),
        bool(opts.get(CONF_INCLUDE_SETTINGS, DEFAULT_INCLUDE_SETTINGS)),
    )


def curated_identifiers() -> tuple[set[str], set[str]]:
    """WellKnownNames and DisplayNames already handled by a curated entity.

    Imported lazily: sensor.py and binary_sensor.py import this module.
    """
    from .binary_sensor import BINARY_SENSORS
    from .sensor import SENSORS

    wkns: set[str] = set()
    names: set[str] = set()
    for description in SENSORS:
        if description.wkn:
            wkns.add(description.wkn)
        names.update(description.display_names)
    for description in BINARY_SENSORS:
        wkns.add(description.wkn)
    return wkns, names


def classify(datapoint: KermiDatapoint) -> str:
    """Decide which platform and presentation a datapoint gets."""
    if datapoint.data_type == DP_TYPE_BOOL or isinstance(datapoint.value, bool):
        return KIND_BINARY
    if datapoint.possible_values:
        return KIND_ENUM
    if datapoint.data_type in (DP_TYPE_INT, DP_TYPE_FLOAT):
        return KIND_NUMERIC
    if datapoint.data_type == DP_TYPE_STRING:
        return KIND_TEXT
    return KIND_NUMERIC if isinstance(datapoint.value, (int, float)) else KIND_TEXT


def selectable(
    datapoint: KermiDatapoint,
    curated_wkns: set[str],
    curated_names: set[str],
    include_settings: bool,
) -> bool:
    """Skip datapoints that a curated entity already covers."""
    if not include_settings and datapoint.is_setting:
        return False
    if datapoint.wkn and datapoint.wkn in curated_wkns:
        return False
    if datapoint.name in curated_names:
        return False
    return True


def enum_options(datapoint: KermiDatapoint) -> list[str]:
    """Distinct labels, order preserved — HA rejects duplicates."""
    return list(dict.fromkeys(datapoint.possible_values.values()))


def enum_label(datapoint: KermiDatapoint, value: Any) -> str | None:
    """Map a raw value onto its German label from PossibleValues."""
    if value is None:
        return None
    if isinstance(value, bool):
        key = "True" if value else "False"
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        key = str(int(value))
    else:
        key = str(value).strip()
    label = datapoint.possible_values.get(key)
    if label is not None:
        return label
    # Some datapoints already report the label itself.
    if key in datapoint.possible_values.values():
        return key
    return None


def numeric_traits(
    datapoint: KermiDatapoint,
) -> tuple[SensorDeviceClass | None, str | None, SensorStateClass | None]:
    """Device class, unit and state class for a plain numeric datapoint."""
    device_class, unit = _UNITS.get(datapoint.unit, (None, datapoint.unit or None))
    name = datapoint.name.lower()
    if datapoint.unit in _TOTAL_UNITS or any(word in name for word in _TOTAL_WORDS):
        state_class = SensorStateClass.TOTAL_INCREASING
    else:
        state_class = SensorStateClass.MEASUREMENT
    # A counter without a unit (e.g. "Anzahl der Verdichterstarts") would be
    # rejected by the statistics engine if we also claimed a device class.
    if unit is None and device_class is not None:
        device_class = None
    return device_class, unit, state_class


def is_problem(datapoint: KermiDatapoint) -> bool:
    name = datapoint.name.lower()
    return any(word in name for word in _PROBLEM_WORDS)


def attributes(datapoint: KermiDatapoint) -> dict[str, Any]:
    """Static metadata, handy for mapping an entity back onto Modbus."""
    data: dict[str, Any] = {
        "datapoint_config_id": datapoint.config_id,
        "datapoint_category": "setting" if datapoint.is_setting else "value",
    }
    if datapoint.wkn:
        data["well_known_name"] = datapoint.wkn
    if datapoint.address:
        data["modbus_address"] = datapoint.address
    return data


def plausible(datapoint: KermiDatapoint, number: float) -> bool:
    """Drop the sentinel readings the x-center uses for 'no sensor'."""
    if datapoint.unit == "°C":
        return -100.0 < number < 400.0
    return abs(number) < 1e9
