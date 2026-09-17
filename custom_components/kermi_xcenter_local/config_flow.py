"""Config flow for Kermi x-center."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .client import KermiAuthError, KermiClient, KermiConnectionError, KermiError
from .const import DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    }
)


async def _validate(hass: HomeAssistant, host: str, password: str, port: int) -> None:
    client = KermiClient(host, password, port)
    try:
        await client.async_login()
    except KermiAuthError as err:
        raise InvalidAuth from err
    except (KermiConnectionError, KermiError, OSError, TimeoutError) as err:
        raise CannotConnect from err
    finally:
        await client.async_close()


class KermiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kermi x-center."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            password = user_input[CONF_PASSWORD]
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()
            try:
                await _validate(self.hass, host, password, port)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Kermi ({host})",
                    data={CONF_HOST: host, CONF_PASSWORD: password, CONF_PORT: port},
                )

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if hasattr(self, "_get_reauth_entry"):
            reauth_entry = self._get_reauth_entry()
        else:
            reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert reauth_entry is not None
        if user_input is not None:
            host = reauth_entry.data[CONF_HOST]
            port = int(reauth_entry.data.get(CONF_PORT, DEFAULT_PORT))
            password = user_input[CONF_PASSWORD]
            try:
                await _validate(self.hass, host, password, port)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_PASSWORD: password},
                )
                await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return KermiOptionsFlow()


class KermiOptionsFlow(OptionsFlow):
    """Scan interval options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            int(DEFAULT_SCAN_INTERVAL.total_seconds()),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=10, max=600)
                    )
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
