"""Config flow for the Siemens LOGO! Modbus TCP integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ADDR_INPUTS,
    CONF_INPUTS,
    CONF_OUTPUTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_INPUTS,
    DEFAULT_OUTPUTS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_INPUTS,
    MAX_OUTPUTS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REQUEST_TIMEOUT,
    UNIT_ID,
)
from .modbus_client import LogoModbusClient, LogoModbusError

_LOGGER = logging.getLogger(__name__)


def _number(minimum: int, maximum: int, unit: str | None = None) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(
        min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
    )
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _counts_schema(defaults: dict[str, Any]) -> dict[vol.Marker, Any]:
    return {
        vol.Required(
            CONF_OUTPUTS, default=defaults.get(CONF_OUTPUTS, DEFAULT_OUTPUTS)
        ): _number(0, MAX_OUTPUTS),
        vol.Required(
            CONF_INPUTS, default=defaults.get(CONF_INPUTS, DEFAULT_INPUTS)
        ): _number(0, MAX_INPUTS),
        vol.Required(
            CONF_SCAN_INTERVAL,
            default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ): _number(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, "s"),
    }


_INT_KEYS = (CONF_PORT, CONF_OUTPUTS, CONF_INPUTS, CONF_SCAN_INTERVAL)


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    """Number selectors return floats; store integers."""
    return {
        key: int(value) if key in _INT_KEYS else value
        for key, value in user_input.items()
    }


async def _async_test_connection(host: str, port: int) -> None:
    """Connect and read I1. Raises LogoModbusError on failure."""
    client = LogoModbusClient(host, port, unit_id=UNIT_ID, timeout=REQUEST_TIMEOUT)
    try:
        await client.read_discrete_inputs(ADDR_INPUTS, 1)
    finally:
        await client.close()


class LogoModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a LOGO!."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for host, port and I/O counts."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _normalize(user_input)
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            try:
                await _async_test_connection(host, port)
            except LogoModbusError as err:
                _LOGGER.debug("Connection test to %s:%s failed: %s", host, port, err)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"LOGO! ({host})",
                    data={**user_input, CONF_HOST: host},
                )

        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                vol.Required(
                    CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
                ): _number(1, 65535),
                **_counts_schema(defaults),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return LogoModbusOptionsFlow()


class LogoModbusOptionsFlow(OptionsFlow):
    """Change I/O counts and polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=_normalize(user_input))

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(_counts_schema(current))
        )
