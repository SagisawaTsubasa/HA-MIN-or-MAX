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

    def _ingest_value(self, val: float, ts=None):
        """将数值塞入窗口并重新计算，同步方法"""
        if ts is None:
            ts = dt_util.now()
        self._values.append((ts, val))
        self._recalculate()
        # 同步上下文中必须用 schedule_update_ha_state，不能用 async_write_ha_state
        self.schedule_update_ha_state()

    def _ingest_current_state(self):
        """读取当前源传感器状态并塞入窗口"""
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
            self._attr_native_unit_of_measurement = source_state.attributes.get("unit_of_measurement")
            self._ingest_value(val)
            _LOGGER.warning(
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
        _LOGGER.warning("[%s] 初始化开始", self.unique_id)

        source_state = self.hass.states.get(self._source)
        if source_state and source_state.attributes.get("friendly_name"):
            self._friendly_name_base = source_state.attributes["friendly_name"]
            _LOGGER.warning("[%s] friendly_name: %s", self.unique_id, self._friendly_name_base)

        # 恢复上次状态
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
            try:
                self._attr_state = round(float(last_state.state), 1)
                _LOGGER.warning("[%s] 恢复上次状态: %s", self.unique_id, self._attr_state)
            except ValueError:
                pass

        # 从 recorder 加载历史
        history_loaded = await self._async_load_history()
        if history_loaded and self._values:
            self._recalculate()
            self.schedule_update_ha_state()
            _LOGGER.warning(
                "[%s] 历史加载完成，当前 %s: %s",
                self.unique_id,
                self._type,
                self._attr_state,
            )

        # 摄入当前状态（第一次兜底）
        ingested = self._ingest_current_state()
        if not ingested:
            _LOGGER.warning("[%s] 初始摄入失败，等源传感器更新或延迟兜底", self.unique_id)

        # 注册状态变化监听
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source], self._async_source_changed
            )
        )
        _LOGGER.warning("[%s] 已注册状态变化监听", self.unique_id)

        # 注册定时清理
        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_cleanup, timedelta(minutes=5))
        )

        # 延迟1秒再次兜底
        async def _delayed_ingest(_):
            if self._attr_state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
                _LOGGER.warning("[%s] 延迟兜底：状态仍为未知，尝试再次摄入", self.unique_id)
                self._ingest_current_state()
            else:
                _LOGGER.warning("[%s] 延迟兜底：状态已就绪 %s", self.unique_id, self._attr_state)

        self.async_on_remove(async_call_later(self.hass, 1, _delayed_ingest))
        _LOGGER.warning("[%s] 初始化完成", self.unique_id)

    async def _async_load_history(self) -> bool:
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import state_changes_during_period

            now = dt_util.now()
            start = now - _to_timedelta(self._value, self._unit)
            instance = get_instance(self.hass)

            def _fetch():
                try:
                    return state_changes_during_period(
                        self.hass,
                        start,
                        now,
                        entity_ids=[self._source],
                        include_start_time_state=True,
                    )
                except TypeError:
                    return state_changes_during_period(
                        self.hass,
                        start,
                        now,
                        entity_id=self._source,
                    )

            result = await instance.async_add_executor_job(_fetch)
            _LOGGER.warning("[%s] recorder 返回类型: %s", self.unique_id, type(result).__name__)

            # 兼容不同返回格式：dict 或 list
            states_list = []
            if isinstance(result, dict) and self._source in result:
                states_list = result[self._source]
                _LOGGER.warning("[%s] dict 格式，%s 条记录", self.unique_id, len(states_list))
            elif isinstance(result, list):
                states_list = result
                _LOGGER.warning("[%s] list 格式，%s 条记录", self.unique_id, len(states_list))
            else:
                _LOGGER.warning("[%s] recorder 无数据或格式未知", self.unique_id)
                return False

            loaded = 0
            for state in states_list:
                if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
                    continue
                try:
                    val = float(state.state)
                    ts = state.last_changed or dt_util.now()
                    self._values.append((ts, val))
                    loaded += 1
                except (ValueError, TypeError):
                    continue

            _LOGGER.warning("[%s] 从 recorder 加载 %s 条有效历史", self.unique_id, loaded)
            return loaded > 0

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
            self._attr_native_unit_of_measurement = new_state.attributes.get("unit_of_measurement")
            self._ingest_value(val)
            _LOGGER.warning(
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
                    _LOGGER.warning("[%s] 窗口为空，塞入当前值兜底", self.unique_id)
                except ValueError:
                    pass

        self._recalculate()
        self.schedule_update_ha_state()

        if dropped > 0:
            _LOGGER.warning("[%s] 清理 %s 条过期数据，当前 %s: %s", self.unique_id, dropped, self._type, self._attr_state)

    def _recalculate(self):
        if not self._values:
            return
        values = [v for t, v in self._values]
        result = max(values) if self._type == "max" else min(values)
        self._attr_state = round(result, 1)
