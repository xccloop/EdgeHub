# EdgeHub Phase 2 — Device Detail 实时波形图

日期: 2026-05-31
基线: Phase 1 全链路打通（`main` 分支）

---

## 一、Phase 1 现状

Phase 1 已经完成了从传感器板到 Windows 仪表板的全链路：

```
LS2K0300 (仿真) ──TCP 二进制帧──▶ 树莓派 4B ──WebSocket──▶ Windows FastAPI ──SSE──▶ Vue 3 仪表板
                        0xEB90+CRC16           epoll ET 模式        localhost:9529      Element Plus
```

### 已实现功能

| 模块 | 功能 | 状态 |
|------|------|:--:|
| **树莓派边缘服务器** | epoll 多路复用，管理多块板子的 TCP 连接 | ✅ |
| **二进制帧协议** | Magic 0xEB90 + Version + Length + Type + CRC-16/Modbus | ✅ |
| **帧解析状态机** | 6 状态滑动窗口，CRC 失败恢复，Length 越界检测 | ✅ |
| **心跳超时检测** | 8s 阈值 × 3 轮 = 24s 断连，带宽限期 | ✅ |
| **WebSocket 广播** | Mongoose 广播 JSON 到所有 PC 客户端 | ✅ |
| **Windows 仪表板** | Vue 3 + Element Plus + FastAPI + pywebview | ✅ |
| **Dashboard 页面** | 设备卡片网格，ONLINE/OFFLINE 状态，消息计数，hover 浮起 | ✅ |
| **DataStream 页面** | 按板子分标签页的终端面板，逐条丝滑滚动，切换页面数据不丢 | ✅ |
| **Settings 页面** | 输入 Pi IP:Port，连接/断开，蓝色渐变按钮 | ✅ |
| **SSE 实时推送** | 全局单一 EventSource → Vue reactive store → 所有页面共享 | ✅ |

### Telemetry 数据格式（自由 JSON）

```json
{
  "board_id": "sim_01",
  "type": "telemetry",
  "speed": 500,
  "kp": 75,
  "ki": 10,
  "kd": 30,
  "imu": {"ax": 0.01, "ay": 0.02, "gz": -0.3},
  "encoder": 1234,
  "temp": 45.2
}
```

任何数字字段都可以出现，不限 IMU。Phase 1 的 Device Detail 页目前是占位空状态。

---

## 二、Phase 2 目标

把 Device Detail 页从"Phase 2 占位"变成**全自动实时波形展示**。

### 核心功能

1. **自动字段发现**: 收到一条 telemetry 后，自动扫描 JSON 里所有数字字段，为每个字段生成一条波形。嵌套字段（如 `imu.ax`）自动展开。
2. **实时滚动波形**: 每条曲线保留最近 60s 的数据，X 轴自动滚动，新数据追加到右侧。
3. **数值分组**: 相关字段自动分到同一组图表（如 `imu.ax/ay/az` 共享一个图表，`speed` 单独一个图表，`kp/ki/kd` 共享一个图表）。
4. **缩放与悬浮**: ECharts 内置的缩放（滚轮/框选）和 tooltip（悬浮显示精确数值）。
5. **板子切换**: 从 Dashboard 点击设备卡片 → 跳转到 Device Detail → 自动显示该板子的波形。

### 不做

- 不实现板子列表/设备选择器（Dashboard 已承担这个角色，或者从 DataStream 标签切换）
- 不实现历史回放（Phase 3 SQLite）
- 不实现波形导出（Phase 3）

---

## 三、技术方案

### 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 图表库 | **ECharts 5** | 百度开源，WebGL 加速，大数据量性能好 |
| Vue 集成 | **vue-echarts** | 官方封装，`<v-chart>` 组件 |
| 数据管理 | 全局 `store` 扩展 | 新增 `store.waveforms: Map<boardId, Map<fieldPath, number[]>>` |
| 路由传参 | Vue Router query params | Dashboard 卡片点击 → `router.push('/device?board=sim_01')` |

### 安装

```bash
npm install echarts vue-echarts
```

### 数据流

```
SSE telemetry 事件
  → store.pending (全局消息队列)
  → 80ms 定时器逐条消费
  → store.perBoard[boardId] (日志缓冲，Phase 1 已有)
  → store.waveforms[boardId][fieldPath].push(value)  (新增)
  → ECharts 响应式更新图表
```

### 自动字段展开

```typescript
function flattenFields(obj: Record<string, any>, prefix = ''): Record<string, number> {
  const result: Record<string, number> = {}
  for (const [key, val] of Object.entries(obj)) {
    if (typeof val === 'number') result[prefix + key] = val
    else if (typeof val === 'object' && val !== null) {
      Object.assign(result, flattenFields(val, prefix + key + '.'))
    }
  }
  return result
}
```

对 `{"speed":500,"imu":{"ax":0.01,"ay":0.02,"gz":-0.3}}` 展开结果：
```
speed: 500
imu.ax: 0.01
imu.ay: 0.02
imu.gz: -0.3
```

### 自动分组

按照字段名的前缀分组到不同图表：

| 字段模式 | 图表标题 | 示例字段 |
|----------|----------|----------|
| `imu.*` | IMU Sensors | imu.ax, imu.ay, imu.gz, imu.gx, imu.gy, imu.gz |
| `speed` | Speed | speed |
| `kp\|ki\|kd` | PID Parameters | kp, ki, kd |
| `encoder*` | Encoder | encoder, encoder_left, encoder_right |
| `temp*` | Temperature | temp, temp_motor |
| 其他 | Other | 未匹配到的任何数字字段 |

每个组生成一个独立的 ECharts 折线图。

### ECharts 配置（单个图表）

```typescript
{
  animation: false,           // 关闭动画，实时追加更流畅
  grid: { top: 40, right: 20, bottom: 30, left: 50 },
  xAxis: { type: 'time', max: 'dataMax', min: (dataMax - 60000) }, // 滚动窗口 60s
  yAxis: { type: 'value' },
  tooltip: { trigger: 'axis' },
  dataZoom: [{ type: 'inside' }],  // 滚轮缩放
  series: [
    { name: 'imu.ax', type: 'line', smooth: true, showSymbol: false, data: [...] },
    { name: 'imu.ay', type: 'line', smooth: true, showSymbol: false, data: [...] },
    { name: 'imu.gz', type: 'line', smooth: true, showSymbol: false, data: [...] },
  ]
}
```

### 性能设计

- 每个字段保留最近 **300 个数据点**（60s × 5Hz = 300 点），超出的丢弃
- 使用 ECharts 的 `appendData` API 增量追加，不触发全量重渲染
- `animation: false` 关闭动画避免累积延迟
- 最多支持 20 个字段 × 20 个图表 = 400 条实时曲线（远超实际需求）

### 路由联动

Dashboard 设备卡片改为可点击：

```vue
<!-- Dashboard.vue 设备卡片 -->
<div class="device-card" @click="router.push('/device?board=' + dev.board_id)">
```

Device Detail 页读取 query param 自动切换：

```typescript
// DeviceDetail.vue
const route = useRoute()
const activeBoard = computed(() => route.query.board as string || '')
```

---

## 四、UI 布局

Device Detail 页翻新后的布局：

```
┌─────────────────────────────────────────────────────┐
│  Device Detail                          sim_01  ●    │
│  ─────────────────────────────────────────────────  │
│                                                     │
│  ┌── IMU Sensors ────────────────────────────────┐  │
│  │  ╱╲  ╱╲                                     │  │
│  │ ╱  ╲╱  ╲╱╲   imu.ax (blue)                  │  │
│  │          ╲╱  ╲  imu.ay (orange)              │  │
│  │               ╲  imu.gz (green)              │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌── Speed ──────────────────────────────────────┐  │
│  │  ─────────────────────────                   │  │
│  │ ╱                                              │  │
│  │╱               speed (blue)                    │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌── PID Parameters ─────────────────────────────┐  │
│  │  ─── kp ─── ki ─── kd                        │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌── Encoder ────────────────────────────────────┐  │
│  │  ╱╲╱╲╱╲╱╲                                    │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

顶部有板子切换器（可选），下方按字段组排列图表，每个图表 200px 高，自适应宽度。

---

## 五、文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `frontend/src/views/DeviceDetail.vue` | 重写，替换占位页 |
| 新增 | `frontend/src/components/WaveChart.vue` | 单个 ECharts 图表组件 |
| 修改 | `frontend/src/api/index.ts` | `store` 新增 `waveforms` 字段 + 分发逻辑 |
| 修改 | `frontend/src/views/Dashboard.vue` | 设备卡片加点击跳转路由 |
| 修改 | `frontend/package.json` | 新增 `echarts` `vue-echarts` 依赖 |
| 修改 | `frontend/src/router/index.ts` | DeviceDetail 路由支持 query param |

### 不需要改后端

Telemetry payload 已经是 JSON，FastAPI 已经原样转发。自动字段展开在前端完成。树莓派代码零改动。

---

## 六、测试验证

| 测试 | 方法 | 预期 |
|------|------|------|
| 单字段波形 | 仿真发 `{"speed":500}` | 1 个图表，1 条线，speed 值随时间变化 |
| 多字段波形 | 仿真发完整 telemetry | 生成 IMU(3条) + Speed(1条) + PID(3条) 三组图表 |
| 嵌套字段 | 仿真发 `{"imu":{"ax":0.1,"ay":0.2}}` | 自动展开为 `imu.ax` `imu.ay` 两条线 |
| 滚动窗口 | 跑模拟器 > 60s | X 轴自动平移，老数据滚出左边 |
| 板子切换 | Dashboard 点卡片 | 跳转 Device Detail，图表自动切换对应板子 |
| 多板独立 | 同时跑 sim_01 + sim_02 | 切板子时波形数据独立不混淆 |

---

## 七、Phase 3 展望（不在本阶段）

- 下行命令路由 (PC → Pi → Board)
- SQLite 历史存储 + 回放
- 波形导出 CSV/PNG
- TLS 加密
- 固件 OTA
