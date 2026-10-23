"""Program selection never writes to the appliance."""
from homeassistant.components.select import SelectEntity
from .const import DOMAIN
from .entity import DishwasherEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Program(hass.data[DOMAIN][entry.entry_id])])


class Program(DishwasherEntity, SelectEntity):
    def __init__(self, dishwasher):
        super().__init__(dishwasher, "program", "Scheduled program", "mdi:dishwasher")
        self._attr_options = list(dishwasher.programs)

    @property
    def current_option(self):
        return self.dishwasher.program

    async def async_select_option(self, option):
        await self.dishwasher.async_select(option)
