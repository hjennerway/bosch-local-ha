"""Completed-wash timestamp and schedule status."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from .const import DOMAIN
from .entity import DishwasherEntity


async def async_setup_entry(hass, entry, async_add_entities):
    dishwasher = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LastRun(dishwasher), Status(dishwasher)])


class LastRun(DishwasherEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, dishwasher):
        super().__init__(dishwasher, "last_run", "Last completed wash", "mdi:dishwasher-alert")

    @property
    def native_value(self):
        return self.dishwasher.last_run


class Status(DishwasherEntity, SensorEntity):
    def __init__(self, dishwasher):
        super().__init__(dishwasher, "status", "Schedule status", "mdi:calendar-check")

    @property
    def native_value(self):
        if self.dishwasher.error:
            return "Attention required"
        if self.dishwasher.pending:
            return "Start requested"
        return "Scheduled" if self.dishwasher.armed else "Not scheduled"

    @property
    def extra_state_attributes(self):
        return {"error": self.dishwasher.error, "automatic": self.dishwasher.automatic,
                "program": self.dishwasher.program}
