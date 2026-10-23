"""Local scheduling and wash history for the existing HCPY MQTT bridge."""
from pathlib import Path

from homeassistant.components.http import StaticPathConfig

from .const import DOMAIN, PLATFORMS
from .coordinator import Dishwasher


async def async_setup(hass, config):
    """Serve the card shipped inside the HACS-managed integration directory."""
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            "/bosch_local/bosch-local-card.js",
            str(Path(__file__).parent / "frontend" / "bosch-local-card.js"),
            False,
        )
    ])
    return True


async def async_setup_entry(hass, entry):
    dishwasher = Dishwasher(hass, entry)
    await dishwasher.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = dishwasher
    entry.async_on_unload(dishwasher.async_close)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    dishwasher.async_listen()
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False
