import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    DOMAIN,
    CONF_SOURCE_SENSOR,
    CONF_TIME_WINDOW,
    CONF_TIME_UNIT,
    CONF_MAX,
    CONF_MIN,
    DEFAULT_TIME_WINDOW,
    DEFAULT_TIME_UNIT,
    TIME_UNITS,
)

UNIT_SHORT = {
    "minute": "m",
    "hour": "h",
    "day": "d",
    "week": "w",
    "month": "mo",
    "year": "y",
}

class MinMaxHistoryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            source = user_input[CONF_SOURCE_SENSOR]
            hours = int(user_input[CONF_TIME_WINDOW])
            unit = user_input.get(CONF_TIME_UNIT, DEFAULT_TIME_UNIT)
            short = UNIT_SHORT.get(unit, unit)
            await self.async_set_unique_id(f"{source}_{hours}_{unit}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"{source.split('.')[-1]} {hours}{short} 极值",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_SOURCE_SENSOR): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_TIME_WINDOW, default=DEFAULT_TIME_WINDOW): NumberSelector(
                    NumberSelectorConfig(min=1, max=999, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_TIME_UNIT, default=DEFAULT_TIME_UNIT): SelectSelector(
                    SelectSelectorConfig(
                        options=TIME_UNITS,
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="time_unit",
                    )
                ),
                vol.Required(CONF_MAX, default=True): BooleanSelector(),
                vol.Required(CONF_MIN, default=True): BooleanSelector(),
            }),
        )
