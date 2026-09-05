"""Min/Max history sensor — rolling-window extreme of a source sensor."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_MAX,
    CONF_MIN,
    CONF_SOURCE_SENSOR,
    CONF_TIME_UNIT,
    CONF_TIME_WINDOW,
    DEFAULT_TIME_UNIT,
    DOMAIN,
    UNIT_SECONDS,
    UNIT_SHORT,
)

_LOGGER = logging.getLogger(__name__)

# Cap on retained samples per entity. Beyond it, adjacent samples are merged
# pairwise (keeping each pair's extreme and the newer timestamp), which bounds
# memory and per-event CPU regardless of the source update rate.
MAX_SAMPLES = 20000


def _window_start(now: datetime, value: int, unit: str) -> datetime:
    """Start of the window ending at ``now`` (calendar-true for month/year)."""
    if unit == "month":
        return now - relativedelta(months=value)
    if unit == "year":
        return now - relativedelta(years=value)
    return now - timedelta(seconds=value * UNIT_SECONDS.get(unit, 3600))


async def _async_fetch_history(
    hass: HomeAssistant, source: str, start: datetime
) -> list[tuple[datetime, float]]:
    """Fetch recorder samples since ``start`` — one query shared by max/min."""
    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import state_changes_during_period

        def _fetch():
            return state_changes_during_period(
                hass,
                start,
                dt_util.now(),
                entity_id=source,
                include_start_time_state=True,
                no_attributes=True,  # states only; attribute history is dead weight here
            )

        result = await get_instance(hass).async_add_executor_job(_fetch)
    except (HomeAssistantError, ImportError) as err:
        _LOGGER.error("读取 recorder 历史失败: %s", err, exc_info=True)
        return []

    if isinstance(result, dict):
        states_list = result.get(source, [])
    elif isinstance(result, list):
        states_list = result
    else:
        return []

    samples: list[tuple[datetime, float]] = []
    for state in states_list:
        if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
            continue
        try:
            samples.append((dt_util.as_utc(state.last_changed), float(state.state)))
        except (ValueError, TypeError):
            continue
    samples.sort(key=lambda item: item[0])
    return samples


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = {**config_entry.data, **config_entry.options}
    source = data[CONF_SOURCE_SENSOR]
    value = int(data[CONF_TIME_WINDOW])
    unit = data.get(CONF_TIME_UNIT, DEFAULT_TIME_UNIT)
    create_max = data[CONF_MAX]
    create_min = data[CONF_MIN]

    # One recorder query shared by both entities instead of one each.
    start = _window_start(dt_util.now(), value, unit)
    samples = await _async_fetch_history(hass, source, start)

    entities = []
    if create_max:
        entities.append(
            MinMaxHistorySensor(hass, config_entry, source, value, unit, "max", samples)
        )
    if create_min:
        entities.append(
            MinMaxHistorySensor(hass, config_entry, source, value, unit, "min", samples)
        )
    async_add_entities(entities)


class MinMaxHistorySensor(SensorEntity, RestoreEntity):
    """Rolling-window extreme (max or min) of a source sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        source_entity: str,
        value: int,
        unit: str,
        stat_type: str,
        initial_samples: list[tuple[datetime, float]] | None = None,
    ) -> None:
        self.hass = hass
        self._config_entry = config_entry
        self._source = source_entity
        self._value = value
        self._unit = unit
        self._type = stat_type
        self._values: list[tuple[datetime, float]] = []
        self._initial_samples = initial_samples or []
        self._stale = False
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = None

    @property
    def name(self) -> str:
        """Follow the source sensor's friendly_name instead of caching it."""
        source_state = self.hass.states.get(self._source)
        base = source_state.attributes.get("friendly_name") if source_state else None
        if not base:
            base = self._source.split(".")[-1]
        short = UNIT_SHORT.get(self._unit, self._unit)
        return f"{base} {self._value}{short} {self._type}"

    @property
    def unique_id(self) -> str:
        return f"{self._config_entry.entry_id}_{self._type}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            name=self._config_entry.title,
            manufacturer="Min/Max History",
            model="Rolling window extreme",
        )

    @property
    def extra_state_attributes(self) -> dict:
        return {"stale": self._stale, "samples": len(self._values)}

    # ------------------------------------------------------------------
    # Sample management
    # ------------------------------------------------------------------

    def _ingest_value(self, val: float, ts: datetime | None = None) -> None:
        if ts is None:
            ts = dt_util.utcnow()
        self._values.append((ts, val))
        if len(self._values) > MAX_SAMPLES:
            self._downsample()
        self._recalculate()

    def _downsample(self) -> None:
        """Merge adjacent sample pairs to bound memory and CPU.

        Keeping each pair's extreme preserves the max/min metric exactly;
        keeping the newer timestamp bounds how long an old value can linger
        in the window.
        """
        keep_extreme = max if self._type == "max" else min
        vals = self._values
        merged: list[tuple[datetime, float]] = []
        for i in range(0, len(vals) - 1, 2):
            t1, v1 = vals[i]
            t2, v2 = vals[i + 1]
            merged.append((max(t1, t2), keep_extreme(v1, v2)))
        if len(vals) % 2:
            merged.append(vals[-1])
        self._values = merged
        _LOGGER.debug(
            "[%s] 样本超过 %d 条，降采样至 %d 条",
            self.unique_id,
            MAX_SAMPLES,
            len(merged),
        )

    def _recalculate(self) -> None:
        if not self._values:
            return
        if self._type == "max":
            result = max(v for _, v in self._values)
        else:
            result = min(v for _, v in self._values)
        # Keep the source precision instead of forcing one decimal.
        self._attr_native_value = result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        _LOGGER.debug("[%s] entity_id=%s 初始化开始", self.unique_id, self.entity_id)

        # 1. 恢复上次状态：作为窗口样本参与计算，而不是仅作展示值，
        #    否则随后 _recalculate 会立刻把它覆盖掉。
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                restored = float(last_state.state)
                ts = (
                    dt_util.as_utc(last_state.last_changed)
                    if last_state.last_changed
                    else dt_util.utcnow()
                )
                self._values.append((ts, restored))
                self._attr_native_value = restored
                unit = last_state.attributes.get("unit_of_measurement")
                if unit:
                    self._attr_native_unit_of_measurement = unit
                _LOGGER.debug("[%s] 恢复上次状态: %s", self.unique_id, restored)
            except (ValueError, TypeError):
                pass

        # 2. 合并平台 setup 时共享查询到的 recorder 历史
        if self._initial_samples:
            merged: dict[datetime, float] = {}
            for ts, val in sorted(
                self._values + self._initial_samples, key=lambda item: item[0]
            ):
                merged[ts] = val
            self._values = list(merged.items())
            self._recalculate()
            _LOGGER.debug(
                "[%s] 历史加载完成 %d 条，当前 %s: %s",
                self.unique_id,
                len(self._values),
                self._type,
                self._attr_native_value,
            )

        # 3. 摄入当前源传感器状态
        self._ingest_current_state()

        # 4. 注册监听
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source], self._async_source_changed
            )
        )
        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_cleanup, timedelta(minutes=5))
        )

        # 5. 写入状态机（无值时延迟兜底一次）
        if self._attr_native_value is not None:
            self.async_write_ha_state()
            _LOGGER.debug("[%s] 初始状态已写入: %s", self.unique_id, self._attr_native_value)
        else:

            async def _delayed_ingest(_):
                if self._attr_native_value is None:
                    if self._ingest_current_state() and self._attr_native_value is not None:
                        self.async_write_ha_state()
                        _LOGGER.debug(
                            "[%s] 延迟兜底写入: %s",
                            self.unique_id,
                            self._attr_native_value,
                        )

            self.async_on_remove(async_call_later(self.hass, 2, _delayed_ingest))

        _LOGGER.debug("[%s] 初始化完成", self.unique_id)

    def _ingest_current_state(self) -> bool:
        source_state = self.hass.states.get(self._source)
        if not source_state:
            _LOGGER.debug("[%s] 源传感器 %s 不存在", self.unique_id, self._source)
            return False
        if source_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
            _LOGGER.debug("[%s] 源传感器当前为 %s", self.unique_id, source_state.state)
            return False
        try:
            val = float(source_state.state)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "[%s] 源传感器状态无法解析: %s", self.unique_id, source_state.state
            )
            return False
        unit = source_state.attributes.get("unit_of_measurement")
        if unit:
            self._attr_native_unit_of_measurement = unit
        ts = (
            dt_util.as_utc(source_state.last_changed)
            if source_state.last_changed
            else dt_util.utcnow()
        )
        self._ingest_value(val, ts)
        return True

    # ------------------------------------------------------------------
    # Runtime callbacks
    # ------------------------------------------------------------------

    @callback
    def _async_source_changed(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
            return
        try:
            val = float(new_state.state)
        except (ValueError, TypeError):
            _LOGGER.debug("[%s] 无效状态值: %s", self.unique_id, new_state.state)
            return

        # 单位变化时清空窗口：新旧单位的样本混在一起求极值没有意义
        new_unit = new_state.attributes.get("unit_of_measurement")
        if new_unit and new_unit != self._attr_native_unit_of_measurement:
            if self._values:
                _LOGGER.warning(
                    "[%s] 源传感器单位变化 %s -> %s，清空窗口历史重新累计",
                    self.unique_id,
                    self._attr_native_unit_of_measurement,
                    new_unit,
                )
            self._values = []
            self._stale = False
            self._attr_native_unit_of_measurement = new_unit

        ts = (
            dt_util.as_utc(new_state.last_changed)
            if new_state.last_changed
            else dt_util.utcnow()
        )
        last = self._values[-1] if self._values else None
        if last is not None and last[0] == ts:
            # 纯属性更新或重复上报：last_changed 不变，同一时刻样本已存在
            if last[1] == val:
                return
            self._values[-1] = (ts, val)
            self._recalculate()
            self.async_write_ha_state()
            return

        self._stale = False
        self._ingest_value(val, ts)
        self.async_write_ha_state()
        _LOGGER.debug(
            "[%s] 事件触发: %s -> %s = %s",
            self.unique_id,
            val,
            self._type,
            self._attr_native_value,
        )

    @callback
    def _async_cleanup(self, now=None) -> None:
        cutoff = _window_start(dt_util.utcnow(), self._value, self._unit)
        old_len = len(self._values)
        self._values = [(t, v) for t, v in self._values if t > cutoff]
        dropped = old_len - len(self._values)

        prev_stale = self._stale
        if not self._values:
            # 源传感器停报超过窗口：保留当前读数兜底并标注 stale，
            # 而不是无声地把它伪装成窗口内样本。
            source_state = self.hass.states.get(self._source)
            if source_state and source_state.state not in (
                STATE_UNKNOWN,
                STATE_UNAVAILABLE,
                None,
            ):
                try:
                    val = float(source_state.state)
                    ts = (
                        dt_util.as_utc(source_state.last_changed)
                        if source_state.last_changed
                        else dt_util.utcnow()
                    )
                    self._values.append((ts, val))
                    self._stale = True
                    _LOGGER.debug("[%s] 窗口为空，塞入当前值兜底 (stale)", self.unique_id)
                except (ValueError, TypeError):
                    pass
        else:
            self._stale = False

        prev_value = self._attr_native_value
        self._recalculate()
        # 值与 stale 标记都没变时不再重复写状态
        if self._attr_native_value != prev_value or self._stale != prev_stale:
            self.async_write_ha_state()

        if dropped:
            _LOGGER.debug(
                "[%s] 清理 %s 条过期数据，当前 %s: %s",
                self.unique_id,
                dropped,
                self._type,
                self._attr_native_value,
            )
