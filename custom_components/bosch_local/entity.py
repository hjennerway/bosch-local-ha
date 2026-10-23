"""Common entity metadata and push updates."""
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.core import callback
from .const import DOMAIN


class DishwasherEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, dishwasher, key, name, icon):
        self.dishwasher = dishwasher
        self._attr_unique_id = f"{dishwasher.entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dishwasher.entry.entry_id)},
            name="Bosch Local Dishwasher", manufacturer="Bosch",
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.dishwasher.listeners.add(self._updated)
        self.async_on_remove(lambda: self.dishwasher.listeners.discard(self._updated))

    @callback
    def _updated(self):
        self.async_write_ha_state()
