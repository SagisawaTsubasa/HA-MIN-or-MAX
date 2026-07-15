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

---

## 安装

### 方式一：HACS（推荐）

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

- Home Assistant Core ≥ 2023.4
- 需要启用 **Recorder** 组件（默认已启用）

---

## 许可证

MIT License

---

**Author**: Kimi (Moonshot AI)
