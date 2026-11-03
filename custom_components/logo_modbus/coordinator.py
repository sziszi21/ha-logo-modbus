"""Data update coordinator for the Siemens LOGO! Modbus TCP integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ADDR_FLAGS,
    ADDR_INPUTS,
    ADDR_OUTPUTS,
    CONF_INPUTS,
    CONF_OUTPUTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_INPUTS,
    DEFAULT_OUTPUTS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    REQUEST_TIMEOUT,
    UNIT_ID,
)
from .modbus_client import LogoModbusClient, LogoModbusError

_LOGGER = logging.getLogger(__name__)

type LogoConfigEntry = ConfigEntry[LogoCoordinator]


@dataclass(slots=True)
class LogoData:
    """One poll's worth of LOGO! state."""

    outputs: list[bool] = field(default_factory=list)  # Q1..Qn
    inputs: list[bool] = field(default_factory=list)  # I1..In


class LogoCoordinator(DataUpdateCoordinator[LogoData]):
    """Polls the Q and I blocks of one LOGO!."""

    config_entry: LogoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: LogoConfigEntry) -> None:
        """Initialize the coordinator."""
        config = {**entry.data, **entry.options}
        self.host: str = config[CONF_HOST]
        self.port: int = config.get(CONF_PORT, DEFAULT_PORT)
        self.output_count: int = config.get(CONF_OUTPUTS, DEFAULT_OUTPUTS)
        self.input_count: int = config.get(CONF_INPUTS, DEFAULT_INPUTS)
        scan_interval: int = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.host}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = LogoModbusClient(
            self.host, self.port, unit_id=UNIT_ID, timeout=REQUEST_TIMEOUT
        )

    async def _async_update_data(self) -> LogoData:
        """Read Q (coils) and I (discrete inputs) from the LOGO!."""
        data = LogoData()
        try:
            if self.output_count:
                data.outputs = await self.client.read_coils(
                    ADDR_OUTPUTS, self.output_count
                )
            if self.input_count:
                data.inputs = await self.client.read_discrete_inputs(
                    ADDR_INPUTS, self.input_count
                )
        except LogoModbusError as err:
            raise UpdateFailed(f"Error communicating with LOGO! {self.host}: {err}") from err
        return data

    async def async_set_flag(self, number: int, value: bool) -> None:
        """Write flag M<number> (1-based) and refresh right away.

        `async_refresh` (not the debounced `async_request_refresh`) so the
        switch follows the real Qn immediately even after quick repeated taps.
        """
        try:
            await self.client.write_coil(ADDR_FLAGS + number - 1, value)
        finally:
            await self.async_refresh()

    async def async_shutdown(self) -> None:
        """Stop polling and close the connection."""
        await super().async_shutdown()
        await self.client.close()
