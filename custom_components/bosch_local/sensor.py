"""Completed-wash timestamp and schedule status."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import DishwasherEntity


async def async_setup_entry(hass, entry, async_add_entities):
    dishwasher = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        LastRun(dishwasher), Status(dishwasher), AutomationReadiness(dishwasher),
        SourceCheck(dishwasher, "door"), SourceCheck(dishwasher, "operation"),
    ])


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
        diagnostics = self.dishwasher.automation_diagnostics()
        return {"error": self.dishwasher.error, "automatic": self.dishwasher.automatic,
                "program": self.dishwasher.program,
                "automatic_summary": diagnostics["summary"],
                "automatic_reasons": diagnostics["reasons"]}


class AutomationReadiness(DishwasherEntity, SensorEntity):
    """Explain every condition preventing a new automatic NightWash schedule."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, dishwasher):
        super().__init__(dishwasher, "automation_readiness", "Automatic NightWash status", "mdi:list-status")

    @property
    def native_value(self):
        return self.dishwasher.automation_diagnostics()["summary"]

    @property
    def extra_state_attributes(self):
        return self.dishwasher.automation_diagnostics()


class SourceCheck(DishwasherEntity, SensorEntity):
    """Keep missing and unavailable inputs visible rather than hiding the check."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, dishwasher, key):
        self.key = key
        name = "Door for scheduled wash" if key == "door" else "Dishwasher activity"
        super().__init__(dishwasher, f"{key}_check", name, "mdi:check-decagram-outline")

    @property
    def native_value(self):
        return self.extra_state_attributes["explanation"]

    @property
    def extra_state_attributes(self):
        return self.dishwasher.automation_diagnostics()["checks"][self.key]
