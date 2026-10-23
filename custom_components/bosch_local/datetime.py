"""Timezone-aware local schedule time."""
from homeassistant.components.datetime import DateTimeEntity
from .const import DOMAIN
from .entity import DishwasherEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Start(hass.data[DOMAIN][entry.entry_id])])


class Start(DishwasherEntity, DateTimeEntity):
    def __init__(self, dishwasher):
        super().__init__(dishwasher, "start", "Scheduled start", "mdi:clock-start")

    @property
    def native_value(self):
        return self.dishwasher.start

    async def async_set_value(self, value):
        await self.dishwasher.async_set_start(value)
