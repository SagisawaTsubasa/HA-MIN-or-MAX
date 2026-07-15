from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_SOURCE_SENSOR,
    CONF_TIME_WINDOW,
    CONF_TIME_UNIT,
    CONF_MAX,
    CONF_MIN,
    DEFAULT_TIME_UNIT,
)

_LOGGER = logging.getLogger(__name__)

UNIT_SECONDS = {
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,   # 30 days
    "year": 31536000,   # 365 days
}

def _to_seconds(value: int, unit: str) -> int:
    return value * UNIT_SECONDS.get(unit, 3600)

def _to_timedelta(value: int, unit: str) -> timedelta:
    return timedelta(seconds=_to_seconds(value, unit))

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities: AddEntitiesCallback):
    source = config_entry.data[CONF_SOURCE_SENSOR]
    value = config_entry.data[CONF_TIME_WINDOW]
    unit = config_entry.data.get(CONF_TIME_UNIT, DEFAULT_TIME_UNIT)
    create_max = config_entry.data[CONF_MAX]
    create_min = config_entry.data[CONF_MIN]

    entities = []
    if create_max:
        entities.append(MinMaxHistorySensor(hass, config_entry.entry_id, source, value, unit, "max"))
    if create_min:
        entities.append(MinMaxHistorySensor(hass, config_entry.entry_id, source, value, unit, "min"))

    async_add_entities(entities)

class MinMaxHistorySensor(SensorEntity, RestoreEntity):
    def __init__(self, hass, entry_id, source_entity, value, unit, stat_type):
        self.hass = hass
        self._entry_id = entry_id
        self._source = source_entity
        self._value = value
        self._unit = unit
        self._type = stat_type
        self._values = []
        self._attr_state = STATE_UNKNOWN
        self._attr_should_poll = False

    @property
    def name(self):
        short = {
            "minute": "m",
            "hour": "h",
            "day": "d",
            "week": "w",
            "month": "mo",
            "year": "y",
        }.get(self._unit, self._unit)
        return f"{self._source.split('.')[-1]} {self._value}{short} {self._type}"

    @property
    def unique_id(self):
        return f"{self._entry_id}_{self._type}"

    async def async_added_to_hass(self):
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
            try:
                self._attr_state = round(float(last_state.state), 1)
            except ValueError:
                pass

        await self._async_load_history()

        source_state = self.hass.states.get(self._source)
        if source_state:
            self._attr_native_unit_of_measurement = source_state.attributes.get('unit_of_measurement')
            if source_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
                try:
                    val = float(source_state.state)
                    self._values.append((dt_util.now(), val))
                    self._recalculate()
                except ValueError:
                    pass

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source], self._async_source_changed
            )
        )

        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_cleanup, timedelta(minutes=5))
        )

        self.async_write_ha_state()

    async def _async_load_history(self):
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import state_changes_during_period

            now = dt_util.now()
            start = now - _to_timedelta(self._value, self._unit)

            instance = get_instance(self.hass)

            def _fetch():
                return state_changes_during_period(
                    self.hass,
                    start,
                    now,
                    [self._source],
                    no_attributes=True,
                    include_start_time_state=True,
                )

            result = await instance.async_add_executor_job(_fetch)

            if result and self._source in result:
                for state in result[self._source]:
                    if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
                        continue
                    try:
                        val = float(state.state)
                        ts = state.last_changed or dt_util.now()
                        self._values.append((ts, val))
                    except (ValueError, TypeError):
                        continue

            self._recalculate()

        except Exception as e:
            _LOGGER.debug("Recorder history load failed: %s", e)

    @callback
    def _async_source_changed(self, event: Event):
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
            return

        try:
            val = float(new_state.state)
            now = dt_util.now()
            self._values.append((now, val))
            self._attr_native_unit_of_measurement = new_state.attributes.get('unit_of_measurement')
            self._recalculate()
            self.async_write_ha_state()
        except (ValueError, TypeError):
            pass

    @callback
    def _async_cleanup(self, now=None):
        cutoff = dt_util.now() - _to_timedelta(self._value, self._unit)
        self._values = [(t, v) for t, v in self._values if t > cutoff]

        if not self._values:
            source_state = self.hass.states.get(self._source)
            if source_state and source_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
                try:
                    val = float(source_state.state)
                    self._values.append((dt_util.now(), val))
                except ValueError:
                    pass

        self._recalculate()
        self.async_write_ha_state()

    def _recalculate(self):
        if not self._values:
            return

        values = [v for t, v in self._values]
        result = max(values) if self._type == "max" else min(values)
        self._attr_state = round(result, 1)
