"""Binary sensors for the LOGO! digital inputs."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LogoConfigEntry, LogoCoordinator
from .entity import LogoEntity

PARALLEL_UPDATES = 0  # Read-only, served by the coordinator.


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one binary sensor per configured input."""
    coordinator = entry.runtime_data
    async_add_entities(
        LogoInputBinarySensor(coordinator, n)
        for n in range(1, coordinator.input_count + 1)
    )


class LogoInputBinarySensor(LogoEntity, BinarySensorEntity):
    """LOGO! digital input In."""

    def __init__(self, coordinator: LogoCoordinator, number: int) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, f"i{number}", f"I{number}")
        self._number = number

    @property
    def is_on(self) -> bool | None:
        """Return the state of In."""
        inputs = self.coordinator.data.inputs
        if self._number > len(inputs):
            return None
        return inputs[self._number - 1]
