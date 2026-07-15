import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    BooleanSelector,
)

from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_TIME_WINDOW, CONF_MAX, CONF_MIN, DEFAULT_TIME_WINDOW

class MinMaxHistoryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            source = user_input[CONF_SOURCE_SENSOR]
            hours = user_input[CONF_TIME_WINDOW]
            await self.async_set_unique_id(f"{source}_{hours}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"{source.split('.')[-1]} {hours}h 极值",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_SOURCE_SENSOR): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_TIME_WINDOW, default=DEFAULT_TIME_WINDOW): NumberSelector(
                    NumberSelectorConfig(min=1, max=168, mode=NumberSelectorMode.BOX, unit_of_measurement="h")
                ),
                vol.Required(CONF_MAX, default=True): BooleanSelector(),
                vol.Required(CONF_MIN, default=True): BooleanSelector(),
            }),
        )
