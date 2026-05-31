# EdgeHub Phase 2 — Device Detail 实时波形图

日期: 2026-05-31 | 基线: Phase 1 全链路打通

---

## 一、Phase 1 现状

```
LS2K0300 (仿真) ──TCP 二进制帧──▶ 树莓派 4B ──WebSocket──▶ Windows FastAPI ──SSE──▶ Vue 3 仪表板
                        0xEB90+CRC16           epoll ET 模式        localhost:9529      Element Plus
```

### 已实现模块

| 模块 | 功能 | 状态 |
|------|------|:--:|
| 树莓派边缘服务器 | epoll 多路复用，管理多块板子的 TCP 连接 | ✅ |
| 二进制帧协议 | Magic 0xEB90 + Version + Length + Type + CRC-16/Modbus | ✅ |
| 帧解析状态机 | 6 状态滑动窗口，CRC 失败滑动恢复，Length 越界检测 | ✅ |
| 心跳超时检测 | 8s 阈值 × 24s 累计断连，EINTR 重试 | ✅ |
| WebSocket 广播 | Mongoose 广播 JSON，MG_SEND_MAX_QUEUE=64 | ✅ |
| Dashboard | 设备卡片网格，ONLINE/OFFLINE 状态灯，hover 浮起 | ✅ |
| DataStream | 按板子分标签页终端，逐条 80ms 丝滑滚动，跨页面保活 | ✅ |
| Settings | Pi 地址连接，蓝色渐变按钮，状态反馈 | ✅ |
| SSE 实时推送 | 全局单 EventSource → reactive store → 全页面共享 | ✅ |

### Telemetry 数据格式（自由 JSON，不限字段）

```json
{"board_id":"sim_01","speed":500,"kp":75,"ki":10,"kd":30,
 "imu":{"ax":0.01,"ay":0.02,"gz":-0.3},"encoder":1234,"temp":45.2}
```

---

## 二、Phase 2 目标

把 Device Detail 页变成**全自动实时波形展示**。

### 核心功能

1. **自动字段发现**: 扫描 Telemetry JSON 中所有数字字段，嵌套对象自动展开为 `imu.ax` 路径
2. **实时滚动波形**: 按 `(timestamp, value)` 存储，X 轴自适应数据范围
3. **可配置分组**: 默认分组规则 + Settings 页 JSON 编辑器自定义映射
4. **缩放与悬浮**: ECharts 内置滚轮/框选缩放 + tooltip 精确值
5. **板子切换**: Dashboard 卡片点击 → query param 传参 → 图表自动切换

### 不做

- 历史回放 / 波形导出（Phase 3 SQLite）
- 下行命令路由（Phase 3）

---

## 三、技术方案

### 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 图表库 | ECharts 5 + vue-echarts | WebGL 加速，`appendData` 增量渲染 |
| 数据模型 | `store.waveforms[boardId][fieldPath]: {ts: number, val: number}[]` | 时间戳+值对，非纯数字数组 |
| 分组配置 | Settings 页 JSON 编辑器 → localStorage | 用户可自定义字段→分组映射 |
| 路由 | Vue Router query params | `/device?board=sim_01` |

### 安装

```bash
npm install echarts vue-echarts
```

### 数据流

```
SSE telemetry
  → store.pending (80ms 逐条消费)
  → flattenFields() → { 'imu.ax': 0.01, 'speed': 500, ... }
  → 按分组规则分配到各组 { ts: Date.now(), val }
  → 每个分组一条 appendData → ECharts 增量渲染
```

### 自动字段展开

```typescript
function flattenFields(obj: Record<string, any>, prefix = ''): Record<string, number> {
  const result: Record<string, number> = {}
  for (const [key, val] of Object.entries(obj)) {
    if (typeof val === 'number' && isFinite(val)) result[prefix + key] = val
    else if (typeof val === 'object' && val !== null && !Array.isArray(val))
      Object.assign(result, flattenFields(val, prefix + key + '.'))
  }
  return result
}
```

跳过 `null`、`NaN`、`Infinity` 和非数字值，避免图表断线。

### 数据存储模型

每个字段存储 `{ts: number, val: number}[]` 而非纯数字数组，这样 ECharts 可以基于真实时间戳渲染，不依赖固定频率假设。

- **保留最近 600 个数据点**（覆盖 5Hz×120s 或 20Hz×30s，安全余量）
- ECharts 配置 `xAxis: { type: 'time' }` 自动处理时间轴
- X 轴范围 `min: 'dataMin', max: 'dataMax'` — 用户缩放后自动跟随实际数据范围，不硬编码 60s 窗口

### 可配置分组规则

**默认分组**（内置，Phase 2 硬编码）：

| 字段模式 (regex) | 图表标题 | 示例字段 |
|---|---|---|
| `imu\..*` | IMU Sensors | imu.ax, imu.ay, imu.gz, imu.gx, imu.gy, imu.gz |
| `speed` | Speed | speed |
| `kp\|ki\|kd` | PID Parameters | kp, ki, kd |
| `encoder.*` | Encoder | encoder, encoder_left, encoder_right |
| `temp.*` | Temperature | temp, temp_motor |
| `voltage\|current\|power\b` | Power | voltage, current, power |
| `.*` | Other | 未匹配字段 |

**自定义分组**（Settings 页新增面板）：

```json
// localStorage key: edgehub_field_groups
[
  { "pattern": "voltage|current|power", "title": "Power" },
  { "pattern": "rpm|motor_speed",      "title": "Motor" },
  { "pattern": "pressure|altitude",    "title": "Environment" }
]
```

分组匹配逻辑：遍历规则列表，取第一个匹配的 regex；都不匹配归入 "Other"。用户可在 Settings 页编辑 JSON 即时生效，WebStorm/VSCode 也有 JSON 语法高亮和验证。

### ECharts 配置细节

```typescript
const option = {
  animation: false,
  grid: { top: 36, right: 20, bottom: 28, left: 52 },
  xAxis: { type: 'time', min: 'dataMin', max: 'dataMax' },
  yAxis: { type: 'value' },
  tooltip: { trigger: 'axis' },
  dataZoom: [{ type: 'inside' }],
  series: fields.map((name, i) => ({
    name,
    type: 'line',
    smooth: true,
    showSymbol: false,
    sampling: 'lttb',          // 点数 > 500 时自动降采样
    data: [],
  })),
}
```

- `animation: false` — 实时追加无需动画
- `showSymbol: false` — 不画数据点圆圈，减少 GPU 开销
- `sampling: 'lttb'` — Largest-Triangle-Three-Buckets 降采样，视觉保真度高

### appendData 与 dataZoom 交互

核心问题：用户缩放查看历史数据时，新数据追加会触发 X 轴自动复位到 `dataMax`。

解决方案：

```typescript
let userZoomed = false

chart.on('dataZoom', () => { userZoomed = true })
// 双击恢复自动滚动
chart.on('dblclick', () => { userZoomed = false; updateChart() })

function appendPoint(fieldName: string, ts: number, val: number) {
  chart.appendData({ seriesIndex, data: [[ts, val]] })
  if (!userZoomed) {
    chart.dispatchAction({ type: 'dataZoom', start: 0, end: 100 })
  }
}
```

用户缩放 → 停止自动滚动；双击图表 → 恢复自动跟随。

### 资源清理

1. **组件卸载**: `onUnmounted` 中调用 `chart.dispose()` 释放 ECharts 实例
2. **离线数据清理**: 定时检查 `store.devices`，板子 OFFLINE 超过 5 分钟后自动 `delete store.waveforms[boardId]`
3. **手动清除**: Device Detail 页增加 "Clear Waveforms" 按钮

```typescript
// api/index.ts — cleanup timer
setInterval(() => {
  const now = Date.now()
  for (const [bid, dev] of Object.entries(store.devices)) {
    if (dev.state === 'OFFLINE' && (now - dev.last_seen_ms) > 300000) {
      delete store.waveforms[bid]
    }
  }
}, 30000) // every 30s
```

### DataStream 环形缓冲（顺手修）

Phase 1 的 `store.perBoard[boardId]` 无限增长。Phase 2 加上限：

```typescript
function pushPerBoard(bid: string, entry: LogLine) {
  if (!store.perBoard[bid]) store.perBoard[bid] = []
  store.perBoard[bid].push(entry)
  if (store.perBoard[bid].length > 2000) {
    store.perBoard[bid].splice(0, 200)  // 环形丢弃头部
  }
}
```

---

## 四、UI 布局

```
┌──────────────────────────────────────────────────────┐
│  Device Detail                         sim_01  ●      │
│  [Clear Waveforms]                                    │
│  ──────────────────────────────────────────────────── │
│                                                       │
│  ┌── IMU Sensors ──────────────────────────────────┐ │
│  │  ╱╲  ╱╲                                       │ │
│  │ ╱  ╲╱  ╲╱╲   imu.ax (blue)                    │ │
│  │          ╲╱  ╲  imu.ay (orange)                │ │
│  │               ╲  imu.gz (green)                │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌── Speed ────────────────────────────────────────┐ │
│  │  ─────────────────────────                     │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌── PID Parameters ───────────────────────────────┐ │
│  │  ─── kp ─── ki ─── kd                          │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌── Encoder ──────────────────────────────────────┐ │
│  │  ╱╲╱╲╱╲╱╲                                      │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

每个图表 200px 高，自适应宽度。顶部带 Clear Waveforms 按钮。

---

## 五、Settings 页新增：字段分组配置

在 Settings 页现有 Connection 卡片下方新增一个卡片：

```
┌── Field Grouping ─────────────────────────────────────┐
│  Customize which fields appear in which chart group.  │
│  ┌──────────────────────────────────────────────────┐ │
│  │ [                                                │ │
│  │   {"pattern":"voltage|current","title":"Power"}, │ │
│  │   {"pattern":"rpm","title":"Motor"}              │ │
│  │ ]                                                │ │
│  └──────────────────────────────────────────────────┘ │
│  [Apply]  [Reset to Default]                          │
└───────────────────────────────────────────────────────┘
```

- JSON 文本编辑区（Element Plus `<el-input type="textarea">`）
- Apply 按钮：解析 JSON，校验格式，存储到 localStorage
- Reset to Default：清除自定义规则，恢复默认分组

---

## 六、文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `src/views/DeviceDetail.vue` | 波形图表页，替换占位 |
| 新增 | `src/components/WaveChart.vue` | 单个图表组件（含 appendData + dataZoom 交互） |
| 修改 | `src/api/index.ts` | store 新增 waveforms、离线清理、环形缓冲 |
| 修改 | `src/views/Dashboard.vue` | 卡片点击 → router push |
| 修改 | `src/views/Settings.vue` | 新增字段分组 JSON 编辑器 |
| 修改 | `frontend/package.json` | 新增 echarts, vue-echarts |
| 修改 | `src/router/index.ts` | /device 路由支持 query.board |

**后端零改动**。树莓派代码不用动。

---

## 七、测试验证

| 测试 | 方法 | 预期 |
|------|------|------|
| 单字段波形 | 仿真推送 `{"speed":500}` | 1 条线实时更新 |
| 多字段+分组 | 推送完整 telemetry | IMU/Speed/PID 三组图表各含对应曲线 |
| 嵌套展开 | 推送 `{"imu":{"ax":0.1,"ay":0.2}}` | `imu.ax` `imu.ay` 两条线 |
| 高频数据 | 模拟 20Hz 推送 2 分钟 | 600 点上限正常工作，不撞墙 |
| dataZoom 交互 | 滚轮缩放后等新数据 | 视图不跳回，双击恢复 |
| 板子切换 | Dashboard 点卡片 | 图表自动切换板子数据 |
| 离线清理 | 模拟器停 6 分钟 | `store.waveforms` 中对应板子数据被移除 |
| 分组配置 | Settings 加自定义规则 | Device Detail 图表按新规则分组 |
| 字段容错 | 推送 `{"speed":null}` → 恢复数字 | 曲线断点跳过不崩溃 |
| 正弦测试 | Python 脚本推送正弦波 | 圆滑曲线，峰值谷值清晰可见 |

### 正弦波测试脚本（Python）

```python
"""向 Windows FastAPI 本地 SSE 推送正弦波 telemetry 用于验证波形图。"""
import time, math, json, requests

API = "http://127.0.0.1:9529"
BOARD = "test_wave"

# 先触发连接
requests.post(f"{API}/api/connect", json={"host": "192.168.1.112", "port": 9528})

t0 = time.time()
while True:
    t = time.time() - t0
    data = {
        "board_id": BOARD,
        "speed": 500 + 100 * math.sin(t * 0.5),
        "kp": 75 + 10 * math.sin(t * 0.3),
        "imu": {
            "ax": 0.1 * math.sin(t * 2),
            "ay": 0.05 * math.cos(t * 1.8),
            "gz": -0.3 + 0.15 * math.sin(t * 1.5),
        },
    }
    # 直接写入 FastAPI SSE 的 WebSocket 上行通道不可用；
    # 替代方案：通过模拟器走树莓派中转（已验证可用）
    # 或者启动一个小型 TCP 客户端直接发二进制帧到 Pi 9527
    time.sleep(0.05)  # 20Hz
```

---

## 八、Phase 3 展望

- 下行命令路由 (PC → Pi → Board)
- SQLite 历史存储 + 回放
- 波形导出 CSV/PNG
- TLS 加密
