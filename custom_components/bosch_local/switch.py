"""Arm a schedule or enable the 48-hour NightWash rule."""
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN
from .entity import DishwasherEntity


async def async_setup_entry(hass, entry, async_add_entities):
    dishwasher = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ScheduleSwitch(dishwasher, False), ScheduleSwitch(dishwasher, True)])


class ScheduleSwitch(DishwasherEntity, SwitchEntity):
    def __init__(self, dishwasher, automatic):
        self.automatic = automatic
        super().__init__(dishwasher, "automatic" if automatic else "armed",
                         "Automatic NightWash" if automatic else "Schedule armed",
                         "mdi:calendar-sync" if automatic else "mdi:calendar-clock")

    @property
    def is_on(self):
        return self.dishwasher.automatic if self.automatic else self.dishwasher.armed

    async def async_turn_on(self, **kwargs):
        await self._set(True)

    async def async_turn_off(self, **kwargs):
        await self._set(False)

    async def _set(self, value):
        if self.automatic:
            await self.dishwasher.async_set_automatic(value)
        else:
            await self.dishwasher.async_arm(value)
