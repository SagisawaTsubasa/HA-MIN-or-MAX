from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval, async_call_later
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
    "month": 2592000,
    "year": 31536000,
}

UNIT_SHORT = {
    "minute": "m",
    "hour": "h",
    "day": "d",
    "week": "w",
    "month": "mo",
    "year": "y",
}

def _to_timedelta(value: int, unit: str) -> timedelta:
    return timedelta(seconds=value * UNIT_SECONDS.get(unit, 3600))

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
        self._friendly_name_base = None

    @property
    def name(self):
        if self._friendly_name_base:
            base = self._friendly_name_base
        else:
            source_state = self.hass.states.get(self._source)
            if source_state and source_state.attributes.get("friendly_name"):
                base = source_state.attributes["friendly_name"]
            else:
                base = self._source.split(".")[-1]
        short = UNIT_SHORT.get(self._unit, self._unit)
        return f"{base} {self._value}{short} {self._type}"

    @property
    def unique_id(self):
        return f"{self._entry_id}_{self._type}"

    def _ingest_current_state(self):
        source_state = self.hass.states.get(self._source)
        if not source_state:
            _LOGGER.warning("[%s] 源传感器 %s 不存在", self.unique_id, self._source)
            return False

        if source_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
            _LOGGER.warning(
                "[%s] 源传感器当前为 %s，跳过",
                self.unique_id,
                source_state.state,
            )
            return False

        try:
            val = float(source_state.state)
            now = dt_util.now()
            self._values.append((now, val))
            self._attr_native_unit_of_measurement = source_state.attributes.get("unit_of_measurement")
            self._recalculate()
            self.async_write_ha_state()
            _LOGGER.info(
                "[%s] 摄入当前值 %s -> %s = %s",
                self.unique_id,
                val,
                self._type,
                self._attr_state,
            )
            return True
        except ValueError:
            _LOGGER.warning(
                "[%s] 源传感器状态无法解析为数字: %s",
                self.unique_id,
                source_state.state,
            )
            return False

    async def async_added_to_hass(self):
        source_state = self.hass.states.get(self._source)
        if source_state and source_state.attributes.get("friendly_name"):
            self._friendly_name_base = source_state.attributes["friendly_name"]
            _LOGGER.info("[%s] friendly_name: %s", self.unique_id, self._friendly_name_base)

        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
            try:
                self._attr_state = round(float(last_state.state), 1)
            except ValueError:
                pass

        history_loaded = await self._async_load_history()
        if history_loaded and self._values:
            self._recalculate()
            self.async_write_ha_state()
            _LOGGER.info(
                "[%s] 历史加载完成，当前 %s: %s",
                self.unique_id,
                self._type,
                self._attr_state,
            )

        self._ingest_current_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source], self._async_source_changed
            )
        )

        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_cleanup, timedelta(minutes=5))
        )

        async def _delayed_ingest(_):
            if self._attr_state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
                _LOGGER.info("[%s] 延迟兜底：状态仍为未知，尝试再次摄入", self.unique_id)
                self._ingest_current_state()

        self.async_on_remove(async_call_later(self.hass, 1, _delayed_ingest))

    async def _async_load_history(self) -> bool:
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import state_changes_during_period

            now = dt_util.now()
            start = now - _to_timedelta(self._value, self._unit)
            instance = get_instance(self.hass)

            # 兼容不同 HA 版本的 API 签名
            # 新版: entity_ids (list), include_start_time_state
            # 旧版: entity_id (str), 无 include_start_time_state
            def _fetch():
                try:
                    # 先尝试新版 API
                    return state_changes_during_period(
                        self.hass,
                        start,
                        now,
                        entity_ids=[self._source],
                        include_start_time_state=True,
                    )
                except TypeError:
                    # fallback 旧版 API：entity_id 传字符串，无 include_start_time_state
                    return state_changes_during_period(
                        self.hass,
                        start,
                        now,
                        entity_id=self._source,
                    )

            result = await instance.async_add_executor_job(_fetch)

            if result and self._source in result:
                loaded = 0
                for state in result[self._source]:
                    if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
                        continue
                    try:
                        val = float(state.state)
                        ts = state.last_changed or dt_util.now()
                        self._values.append((ts, val))
                        loaded += 1
                    except (ValueError, TypeError):
                        continue
                _LOGGER.info("[%s] 从 recorder 加载 %s 条历史", self.unique_id, loaded)
                return True
            _LOGGER.info("[%s] recorder 无历史数据", self.unique_id)
            return False

        except Exception as e:
            _LOGGER.error("[%s] 读取 recorder 历史失败: %s", self.unique_id, e)
            return False

    @callback
    def _async_source_changed(self, event: Event):
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
            return

        try:
            val = float(new_state.state)
            now = dt_util.now()
            self._values.append((now, val))
            self._attr_native_unit_of_measurement = new_state.attributes.get("unit_of_measurement")
            self._recalculate()
            self.async_write_ha_state()
            _LOGGER.debug(
                "[%s] 事件触发: %s -> %s = %s",
                self.unique_id,
                val,
                self._type,
                self._attr_state,
            )
        except (ValueError, TypeError):
            _LOGGER.warning(
                "[%s] 收到无效状态值: %s",
                self.unique_id,
                new_state.state,
            )

    @callback
    def _async_cleanup(self, now=None):
        cutoff = dt_util.now() - _to_timedelta(self._value, self._unit)
        old_len = len(self._values)
        self._values = [(t, v) for t, v in self._values if t > cutoff]
        dropped = old_len - len(self._values)

        if not self._values:
            source_state = self.hass.states.get(self._source)
            if source_state and source_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
                try:
                    val = float(source_state.state)
                    self._values.append((dt_util.now(), val))
                    _LOGGER.info("[%s] 窗口为空，塞入当前值兜底", self.unique_id)
                except ValueError:
                    pass

        self._recalculate()
        self.async_write_ha_state()

        if dropped > 0:
            _LOGGER.debug("[%s] 清理 %s 条过期数据，当前 %s: %s", self.unique_id, dropped, self._type, self._attr_state)

    def _recalculate(self):
        if not self._values:
            return
        values = [v for t, v in self._values]
        result = max(values) if self._type == "max" else min(values)
        self._attr_state = round(result, 1)
