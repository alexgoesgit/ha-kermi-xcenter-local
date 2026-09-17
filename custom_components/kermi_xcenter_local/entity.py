"""Shared entity helpers for Kermi x-center."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import KermiDeviceData
from .const import DEVICE_TYPE_IFM, DOMAIN, MANUFACTURER
from .coordinator import KermiCoordinator


def device_info_for(device: KermiDeviceData, devices: dict[str, KermiDeviceData]) -> DeviceInfo:
    via: tuple[str, str] | None = None
    if device.device_type != DEVICE_TYPE_IFM:
        hub = next((d for d in devices.values() if d.device_type == DEVICE_TYPE_IFM), None)
        if hub:
            via = (DOMAIN, hub.device_id)
    data = {
        "identifiers": {(DOMAIN, device.device_id)},
        "manufacturer": MANUFACTURER,
        "name": device.name,
        "model": device.model,
        "sw_version": device.software_version,
        "serial_number": device.serial or None,
    }
    if via:
        data["via_device"] = via
    return DeviceInfo(**data)


class KermiEntity(CoordinatorEntity[KermiCoordinator]):
    """Base entity bound to one x-center device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KermiCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device_id}_{key}"

    @property
    def device_data(self) -> KermiDeviceData | None:
        return self.coordinator.data.get(self._device_id)

    @property
    def available(self) -> bool:
        return super().available and self.device_data is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        device = self.device_data
        if device is None:
            return None
        return device_info_for(device, self.coordinator.data)
