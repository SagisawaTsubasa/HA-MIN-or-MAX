# Min/Max History

一个 Home Assistant 自定义集成，用于为任意传感器在指定时间窗口内自动生成 **最大值** 和 **最小值** 实体。

> **主程序**: Kimi (Moonshot AI)  
> 本集成由 Kimi 根据用户需求设计并编写，支持 UI 配置、滑动窗口维护、重启后历史恢复。

---

## 功能

- ✅ **UI 配置** — 无需编辑 YAML，在 Home Assistant 的「设置 → 设备与服务 → 添加集成」中直接添加
- ✅ **灵活时间单位** — 支持 分钟 / 小时 / 天 / 周 / 月 / 年 作为时间窗口单位
- ✅ **滑动窗口** — 自动清理过期数据，只保留指定时间窗口内的记录
- ✅ **重启恢复** — 启动时尝试从 Recorder 数据库读取历史数据，无需等待窗口填满
- ✅ **多实例** — 同一个传感器可以添加多次（如 1h / 24h / 7d），互不冲突
- ✅ **中文界面** — 自带简体中文翻译
- ✅ **friendly_name 继承** — 生成的实体名自动使用源传感器的显示名称
- ✅ **多版本 HA 兼容** — 自动适配新旧版 API 与返回格式

---

## 安装

### 方式一：HACS

1. 打开 HACS → 自定义存储库
2. 添加本仓库地址，类别选 **Integration**
3. 安装后重启 Home Assistant

### 方式二：手动安装

1. 下载本仓库
2. 将 `custom_components/min_max_history/` 文件夹复制到 Home Assistant 的 `config/custom_components/` 目录下
3. 重启 Home Assistant

---

## 使用

1. 进入 **设置 → 设备与服务 → 添加集成**
2. 搜索 **Min/Max History**
3. 选择源传感器（如温度传感器）
4. 设置时间窗口数值
5. 选择时间单位（分钟 / 小时 / 天 / 周 / 月 / 年）
6. 勾选需要创建的实体（最大值 / 最小值）
7. 提交后自动创建实体

### 示例：配合 Mushroom Chip 卡片显示 24h 极值

```yaml
type: custom:mushroom-chips-card
chips:
  - type: template
    content: "{{ states('sensor.bedroom_24h_max') }}°C"
    icon: mdi:arrow-up-bold
    icon_color: "#1e90ff"
    tap_action:
      action: none
  - type: template
    content: "{{ states('sensor.bedroom_24h_min') }}°C"
    icon: mdi:arrow-down-bold
    icon_color: "#1e90ff"
    tap_action:
      action: none
```

---

## 兼容性

- Home Assistant Core ≥ 2024.11（与 hacs.json 声明一致）
- 需要启用 **Recorder** 组件（默认已启用）

---

## 许可证

MIT License

---

**Author**: Kimi (Moonshot AI)

## 更新日志 / Changelog

### 1.3.1
- 修复：补充 `translations/en.json`——HA 运行时只读 translations 目录，此前英文界面无法获得流程文案（strings.json 不参与运行时）  
  Fixed: added `translations/en.json` — HA runtime only reads the translations directory, so English users never got the flow strings
- 优化：新建条目标题去掉硬编码中文（改为语言中性的 `max/min` 后缀）  
  Improved: new entry titles drop the hardcoded Chinese suffix (language-neutral `max/min`)
- 清理：ruff check 告警清零（import 排序、未用导入、`logging.exception` 规范、嵌套 if 合并；不含 ruff format 重排）  
  Chores: ruff check warnings cleared (import order, unused imports, logging.exception style, nested if; no reformat)
- 评估记录：实体名刻意保持动态跟随源传感器 friendly_name，与 `_attr_has_entity_name` 的设备名前缀语义冲突，故不引入（审计遗留项 L5 的结论）  
  Note: entity names intentionally follow the source sensor's friendly_name, which conflicts with `_attr_has_entity_name` device-prefix semantics — audit item L5 closed as won't-fix

### 1.3.0（2026-09-05 审计修复批次）
- 采样上限 20000 + 相邻对降采样、恢复值入窗、relativedelta 日历窗口等审计修复  
  September audit fixes: sample cap with pairwise downsampling, restore-into-window, relativedelta calendar windows
