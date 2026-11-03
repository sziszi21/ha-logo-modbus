"""Base entity for the Siemens LOGO! Modbus TCP integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import LogoCoordinator


class LogoEntity(CoordinatorEntity[LogoCoordinator]):
    """Common base: one device per config entry."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LogoCoordinator, key: str, name: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=f"LOGO! ({coordinator.host})",
        )
