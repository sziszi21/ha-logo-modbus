"""Switches for the LOGO! outputs.

Each switch writes flag Mn and shows the real state of output Qn.
The LOGO! program must contain Qn = Mn OR <physical logic>.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import LogoConfigEntry, LogoCoordinator
from .entity import LogoEntity
from .modbus_client import LogoModbusError

PARALLEL_UPDATES = 0  # The client serializes requests itself.


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one switch per configured output."""
    coordinator = entry.runtime_data
    async_add_entities(
        LogoOutputSwitch(coordinator, n) for n in range(1, coordinator.output_count + 1)
    )


class LogoOutputSwitch(LogoEntity, SwitchEntity):
    """LOGO! output Qn, controlled through flag Mn."""

    def __init__(self, coordinator: LogoCoordinator, number: int) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, f"q{number}", f"Q{number}")
        self._number = number
        self._attr_extra_state_attributes = {"control_flag": f"M{number}"}

    @property
    def is_on(self) -> bool | None:
        """Return the real state of Qn."""
        outputs = self.coordinator.data.outputs
        if self._number > len(outputs):
            return None
        return outputs[self._number - 1]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set flag Mn."""
        await self._async_write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear flag Mn."""
        await self._async_write(False)

    async def _async_write(self, value: bool) -> None:
        try:
            await self.coordinator.async_set_flag(self._number, value)
        except LogoModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={
                    "flag": f"M{self._number}",
                    "host": self.coordinator.host,
                    "error": str(err),
                },
            ) from err
