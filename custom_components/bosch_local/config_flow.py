"""Configure appliance-specific IDs without guessing them."""
import json
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN


class BoschLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up a local dishwasher scheduler."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                programs = json.loads(user_input["programs"])
                if not isinstance(programs, dict) or not programs or any(
                    not isinstance(name, str) or not name.strip()
                    or isinstance(uid, bool) or not isinstance(uid, int) or uid <= 0
                    for name, uid in programs.items()
                ):
                    raise ValueError
                topic = user_input["topic"].strip().rstrip("/")
                if not topic or any(c in topic for c in "+#\x00"):
                    raise ValueError
            except (ValueError, TypeError):
                errors["base"] = "invalid_config"
            else:
                await self.async_set_unique_id(topic)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Dishwasher", data={
                    **user_input, "programs": programs, "topic": topic,
                })
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required("topic", default="bosch_local/dishwasher"): str,
            vol.Required("programs", default='{"NightWash": 8202}'): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)),
            vol.Required("operation_state_entity", default="sensor.bosch_schedule_operation"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")),
            vol.Required("door_entity", default="sensor.bosch_schedule_door"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional("last_run_entity", default="input_datetime.dishwasher_last_run_reference"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="input_datetime")),
        }))
