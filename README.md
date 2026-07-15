# Min/Max History

一个 Home Assistant 自定义集成，用于为任意传感器在指定时间窗口内自动生成 **最大值** 和 **最小值** 实体。

> **主程序**: Kimi (Moonshot AI)  
> 本集成由 Kimi 根据用户需求设计并编写，支持 UI 配置、滑动窗口维护、重启后历史恢复。

---

## 功能

- ✅ **UI 配置** — 无需编辑 YAML，在 Home Assistant 的「设置 → 设备与服务 → 添加集成」中直接添加
- ✅ **滑动窗口** — 自动清理过期数据，只保留指定时间窗口内的记录
- ✅ **重启恢复** — 启动时尝试从 Recorder 数据库读取历史数据，无需等待窗口填满
- ✅ **多实例** — 同一个传感器可以添加多次（如 1h / 24h / 7d），互不冲突
- ✅ **中文界面** — 自带简体中文翻译

---

## 安装

### 方式一：HACS（推荐）

1. 打开 HACS → 自定义存储库
2. 添加本仓库地址，类别选 **Integration**
3. 安装后重启 Home Assistant

### 方式二：手动安装

1. 下载本仓库的 `custom_components/min_max_history/` 文件夹
2. 将其复制到 Home Assistant 的 `config/custom_components/` 目录下
3. 重启 Home Assistant

---

## 使用

1. 进入 **设置 → 设备与服务 → 添加集成**
2. 搜索 **Min/Max History**
3. 选择源传感器（如温度传感器）
4. 设置时间窗口（小时）
5. 勾选需要创建的实体（最大值 / 最小值）
6. 提交后自动创建实体，可在开发者工具中查看

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

## 文件结构

```
custom_components/min_max_history/
├── __init__.py          # 入口
├── manifest.json        # 集成元数据
├── const.py             # 常量定义
├── config_flow.py       # UI 配置流程
├── sensor.py            # 核心传感器逻辑
├── strings.json         # 英文翻译
└── translations/
    └── zh-Hans.json     # 简体中文翻译
```

---

## 技术细节

- 使用 `async_track_state_change_event` 监听源传感器变化
- 使用 `async_track_time_interval` 每 5 分钟清理过期数据
- 启动时通过 `state_changes_during_period` 从 Recorder 恢复历史
- 继承 `RestoreEntity` 以在重启后保留最后已知状态
- 支持 `unique_id`，可在 UI 中重命名和分配区域

---

## 兼容性

- Home Assistant Core ≥ 2023.4（依赖 `async_forward_entry_setups`）
- 需要启用 **Recorder** 组件（默认已启用）

---

## 许可证

MIT License

---

**Author**: Kimi (Moonshot AI)  
**Repository**: https://github.com/yourusername/min_max_history
