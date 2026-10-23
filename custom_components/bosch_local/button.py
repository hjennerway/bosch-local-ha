"""Clear a local schedule without publishing an invalid appliance state."""
from homeassistant.components.button import ButtonEntity
from .const import DOMAIN
from .entity import DishwasherEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Clear(hass.data[DOMAIN][entry.entry_id])])


class Clear(DishwasherEntity, ButtonEntity):
    def __init__(self, dishwasher):
        super().__init__(dishwasher, "clear", "Clear schedule", "mdi:calendar-remove")

    async def async_press(self):
        await self.dishwasher.async_clear()
