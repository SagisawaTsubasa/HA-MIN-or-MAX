"""Config flow for Min/Max History."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_MAX,
    CONF_MIN,
    CONF_SOURCE_SENSOR,
    CONF_TIME_UNIT,
    CONF_TIME_WINDOW,
    DEFAULT_TIME_UNIT,
    DEFAULT_TIME_WINDOW,
    DOMAIN,
    TIME_UNITS,
    UNIT_SHORT,
)


def _build_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_SOURCE_SENSOR, default=d.get(CONF_SOURCE_SENSOR)): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_TIME_WINDOW, default=d.get(CONF_TIME_WINDOW, DEFAULT_TIME_WINDOW)
            ): NumberSelector(NumberSelectorConfig(min=1, max=999, mode=NumberSelectorMode.BOX)),
            vol.Required(
                CONF_TIME_UNIT, default=d.get(CONF_TIME_UNIT, DEFAULT_TIME_UNIT)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=TIME_UNITS,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="time_unit",
                )
            ),
            vol.Required(CONF_MAX, default=d.get(CONF_MAX, True)): BooleanSelector(),
            vol.Required(CONF_MIN, default=d.get(CONF_MIN, True)): BooleanSelector(),
        }
    )


class MinMaxHistoryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict = {}
        if user_input is not None:
            if not user_input.get(CONF_MAX) and not user_input.get(CONF_MIN):
                errors["base"] = "no_type_selected"
            else:
                source = user_input[CONF_SOURCE_SENSOR]
                amount = int(user_input[CONF_TIME_WINDOW])
                unit = user_input.get(CONF_TIME_UNIT, DEFAULT_TIME_UNIT)
                short = UNIT_SHORT.get(unit, unit)
                await self.async_set_unique_id(f"{source}_{amount}_{unit}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"{source.split('.')[-1]} {amount}{short} 极值",
                    data=user_input,
                )

        return self.async_show_form(step_id="user", data_schema=_build_schema(), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MinMaxHistoryOptionsFlow()


class MinMaxHistoryOptionsFlow(config_entries.OptionsFlow):
    """Edit source/window without deleting and recreating the entry."""

    async def async_step_init(self, user_input=None):
        current = dict(self.config_entry.data)
        if user_input is not None:
            if not user_input.get(CONF_MAX) and not user_input.get(CONF_MIN):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_build_schema(current),
                    errors={"base": "no_type_selected"},
                )
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=_build_schema(current))
