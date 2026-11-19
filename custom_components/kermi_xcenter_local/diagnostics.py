"""Diagnostics: dump every datapoint with its metadata."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .auto import classify
from .coordinator import KermiConfigEntry

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KermiConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    devices = []
    for device in coordinator.data.values():
        devices.append(
            {
                "device_id": device.device_id,
                "name": device.name,
                "model": device.model,
                "device_type": device.device_type,
                "software_version": device.software_version,
                "datapoints": [
                    {
                        "sort": dp.sort,
                        "name": dp.name,
                        "value": dp.value,
                        "unit": dp.unit,
                        "kind": classify(dp),
                        "category": "setting" if dp.is_setting else "value",
                        "well_known_name": dp.wkn,
                        "config_id": dp.config_id,
                        "modbus_address": dp.address,
                        "possible_values": dp.possible_values or None,
                        "description": dp.description or None,
                    }
                    for dp in sorted(device.datapoints.values(), key=lambda d: d.sort)
                ],
            }
        )
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "devices": devices,
    }
