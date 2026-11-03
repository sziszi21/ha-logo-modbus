"""The Siemens LOGO! Modbus TCP integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .coordinator import LogoConfigEntry, LogoCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: LogoConfigEntry) -> bool:
    """Set up a LOGO! from a config entry."""
    coordinator = LogoCoordinator(hass, entry)
    try:
        # Raises ConfigEntryNotReady (and HA retries) if the LOGO! is unreachable.
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await coordinator.client.close()
        raise

    entry.runtime_data = coordinator
    _async_remove_stale_entities(hass, entry, coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LogoConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


@callback
def _async_remove_stale_entities(
    hass: HomeAssistant, entry: LogoConfigEntry, coordinator: LogoCoordinator
) -> None:
    """Remove entities for Q/I numbers no longer configured (counts lowered)."""
    wanted = {f"{entry.entry_id}_q{n}" for n in range(1, coordinator.output_count + 1)}
    wanted |= {f"{entry.entry_id}_i{n}" for n in range(1, coordinator.input_count + 1)}
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id not in wanted:
            registry.async_remove(reg_entry.entity_id)


async def _async_update_listener(hass: HomeAssistant, entry: LogoConfigEntry) -> None:
    """Reload the entry when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)
