"""DataUpdateCoordinator for Kermi x-center."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import KermiAuthError, KermiClient, KermiConnectionError, KermiDeviceData, KermiError
from .const import DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN, MIN_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type KermiConfigEntry = ConfigEntry[KermiCoordinator]


class KermiCoordinator(DataUpdateCoordinator[dict[str, KermiDeviceData]]):
    """Polls the x-center for all device datapoints."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        scan = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds()),
        )
        try:
            interval = timedelta(seconds=float(scan))
        except (TypeError, ValueError):
            interval = DEFAULT_SCAN_INTERVAL
        if interval < MIN_SCAN_INTERVAL:
            interval = MIN_SCAN_INTERVAL

        try:
            super().__init__(
                hass, _LOGGER, name=DOMAIN, update_interval=interval, config_entry=entry
            )
        except TypeError:
            super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=interval)
        self.entry = entry
        self.client = KermiClient(
            host=entry.data[CONF_HOST],
            password=entry.data[CONF_PASSWORD],
            port=int(entry.data.get(CONF_PORT, DEFAULT_PORT)),
        )

    async def async_shutdown(self) -> None:
        await self.client.async_close()
        shutdown = getattr(super(), "async_shutdown", None)
        if shutdown is not None:
            await shutdown()

    async def _async_update_data(self) -> dict[str, KermiDeviceData]:
        try:
            return await self.client.async_update()
        except KermiAuthError as err:
            raise ConfigEntryAuthFailed("Kermi login rejected") from err
        except (KermiConnectionError, KermiError) as err:
            raise UpdateFailed(str(err)) from err
