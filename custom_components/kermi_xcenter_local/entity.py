"""Shared entity helpers for Kermi x-center."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo, async_get as async_get_device_registry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import KermiDeviceData
from .const import DEVICE_TYPE_IFM, DOMAIN, MANUFACTURER
from .coordinator import KermiCoordinator

_SUPPORTS_VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__


def _device_kwargs(device: KermiDeviceData) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, device.device_id)},
        "manufacturer": MANUFACTURER,
        "name": device.name,
        "model": device.model,
        "sw_version": device.software_version,
        "serial_number": device.serial or None,
    }


def async_register_hub_device(coordinator: KermiCoordinator) -> None:
    """Create the x-center hub first so child devices can set via_device_id."""
    hub = next((d for d in coordinator.data.values() if d.device_type == DEVICE_TYPE_IFM), None)
    if hub is None:
        coordinator.hub_registry_id = None
        return
    registry = async_get_device_registry(coordinator.hass)
    entry = registry.async_get_or_create(
        config_entry_id=coordinator.entry.entry_id,
        **_device_kwargs(hub),
    )
    coordinator.hub_registry_id = entry.id


def device_info_for(coordinator: KermiCoordinator, device: KermiDeviceData) -> DeviceInfo:
    data = _device_kwargs(device)
    if device.device_type != DEVICE_TYPE_IFM:
        if _SUPPORTS_VIA_DEVICE_ID and coordinator.hub_registry_id:
            data["via_device_id"] = coordinator.hub_registry_id
        elif not _SUPPORTS_VIA_DEVICE_ID:
            hub = next(
                (d for d in coordinator.data.values() if d.device_type == DEVICE_TYPE_IFM),
                None,
            )
            if hub:
                data["via_device"] = (DOMAIN, hub.device_id)
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
        return device_info_for(self.coordinator, device)
