# 实际问题与解决方案

本文档记录 Kyl-Epoll 项目开发过程中遇到的实际问题及其排查和解决过程。

## 目录

1. [项目迁移后 CMake 路径失效](#1-项目迁移后-cmake-路径失效)
2. [EPOLLET 边沿触发丢数据](#2-epollet-边沿触发丢数据)
3. [串口回显卡顿](#3-串口回显卡顿)
4. [UART 断开重连](#4-uart-断开重连)
5. [退格键处理](#5-退格键处理)
6. [交叉编译兼容性](#6-交叉编译兼容性)
7. [多 fd 并发访问编码器](#7-编码器破坏性读取问题)

---

## 1. 项目迁移后 CMake 路径失效

### 问题

项目从 `/home/lq/Desktop/_ls2k0300/` 移动到 `/home/lq/Desktop/EPOLL/_ls2k0300/` 后，
编译失败：

```
CMake Error: toolchain not found at
  /home/lq/Desktop/_ls2k0300/tools/loongson-gnu-toolchain-8.3...
```

### 原因

`toolchain_path.cmake` 中硬编码了旧路径。该文件由 `build.sh` 第 604 行自动生成：

```bash
cat > "${TOOLCHAIN_CMAKE_MACRO_FILE}" << EOF
set(CMAKE_TOOLCHAIN_PATH "${toolchain_path}" CACHE PATH "..." FORCE)
EOF
```

其中 `toolchain_path` = `${TOOLS_DIR}/${TOOLCHAIN_DIR_NAME}`，`TOOLS_DIR` = `${SCRIPT_DIR}/tools`。

### 解决

1. 手动修正 `toolchain_path.cmake` 为新路径
2. `tools` 目录是符号链接 → `/home/lq/Desktop/car/tools`，工具链实际存在
3. 运行 `build.sh` 会自动重新生成正确的路径（但首次编译前需要修正）

### 预防

- 不在 CMakeLists.txt 中硬编码绝对路径，全部使用 `${CMAKE_SOURCE_DIR}` 和相对路径
- `build.sh` 已正确处理相对路径，只要不删除 `toolchain_path.cmake` 就不会出问题

---

## 2. EPOLLET 边沿触发丢数据

### 问题

测试时发现：发送长命令 "echo hello world this is a very long message" 时，
Shell 只收到了 "echo hello" 就被截断了。

### 原因

epoll ET 模式只在**状态变化**时通知一次。如果一次 `read()` 没读完缓冲区的所有数据，
剩余数据不会触发新的 epoll_wait 返回。必须循环 read 直到返回 EAGAIN。

错误代码：
```c
// ❌ 只读一次，缓冲区剩余数据被"遗忘"
char buf[256];
int n = read(uart_fd, buf, sizeof(buf)-1);
```

### 解决

正确代码（本项目采用）：
```c
// ✅ 循环读到 EAGAIN 为止
while (1) {
    ssize_t n = read(uart_fd, &c, 1);
    if (n < 0) {
        if (errno == EAGAIN) break;  // 缓冲区已空
        break;
    }
    if (n == 0) break;
    // 处理字符 c
}
```

### 知识点

- ET 模式必须配合**非阻塞 fd**（O_NONBLOCK），否则 read 会阻塞
- 循环 read 是 ET 模式的强制要求，否则数据会丢失
- LT 模式无此问题，但会频繁唤醒 epoll_wait

---

## 3. 串口回显卡顿

### 问题

用户通过 `screen /dev/ttyUSB0 115200` 连接板子串口时，输入字符后回显有
明显延迟（> 100ms），体验很差。

### 原因

最初的实现中，数据到达后没有立即回显，而是等到整行处理完成才 printf 返回。
加上 epoll_wait 有 100ms 超时，导致用户感觉"输入没反应"。

### 解决

每个字符到达后立即回显：

```c
// 数据到达时即刻回显（逐字符）
write(uart_fd, &c, 1);

// 回车时输出 \r\n
if (c == '\r') write(uart_fd, "\r\n", 2);

// 退格时输出 VT100 序列
if (c == 0x7F) write(uart_fd, "\b \b", 3);
```

### VT100 退格序列解释

```
\b  → 光标左移一格
' ' → 用空格覆盖旧字符
\b  → 光标再左移一格（回到原位）
```

这样用户看到的是字符被"擦除"，而屏幕缓冲区不会留下残影。

---

## 4. UART 断开重连

### 问题

串口线意外拔出或 ttyUSB 断开后，程序检测到 fd 上出现 EPOLLERR/EPOLLHUP，
但之后无法自动恢复通信。

### 原因

- fd 上的错误事件不会自动消失
- close() 后 fd 失效，需要重新 open()
- 如果没有自动重连逻辑，只能手动重启程序

### 解决

在 epoll 事件循环中监控 `EPOLLERR | EPOLLHUP`：

```c
if (ev & (EPOLLERR | EPOLLHUP)) {
    if (fd == uart_fd) {
        ep.del(uart_fd);          // 从 epoll 移除
        uart1_close();            // 关闭 fd
        sleep(1);                 // 等待硬件稳定
        if (uart1_init() == 0) {  // 重新初始化
            uart_fd = uart1_get_fd();
            ep.add(uart_fd, EPOLLIN);
            printf("UART1 reconnected\n");
        }
    }
}
```

---

## 5. 退格键处理

### 问题

板子上的终端收到退格键时，Shell 的行为因终端程序而异：
- `screen` 发送 `0x7F` (DEL)
- 某些终端发送 `0x08` (BS)
- 输入 `Ctrl+H` 也发送 `0x08`

### 解决

同时处理两种退格码：

```c
else if (c == 0x7F || c == '\b')
{
    if (line_pos > 0) {
        line_pos--;
        line_buf[line_pos] = '\0';
        write(uart_fd, "\b \b", 3);  // VT100 清除
    }
}
```

---

## 6. 交叉编译兼容性

### 问题

- `sys/sysinfo.h` 中 `struct sysinfo` 的字段名在 glibc 和 musl 之间不同
  - glibc: `uptime`, `loads`, `totalram` 等
  - musl: 同样字段但 `mem_unit` 可能缺失
- LoongArch 工具链使用 glibc 2.28+，兼容主流字段名

### 解决

使用条件编译（虽然本项目未实际遇到）：
```c
#if __GLIBC__
    si.totalram  // glibc
#else
    si.mem_total // musl/alternative
#endif
```

### 验证

编译后在板子上运行，确认 `status` 和 `uptime` 命令输出正确数值。

---

## 7. 编码器破坏性读取问题（历史）

### 背景

`/dev/zf_encoder_quad_1` 和 `/dev/zf_encoder_quad_2` 的 `read()` 是破坏性读取——
每次 read 后内核计数器归零，只返回"自上次 read 以来的增量"。

### 影响

如果 ISR (每 10ms 调用 `Motor_Control()`) 和主循环同时读编码器，ISR 每 10ms
"吃掉"计数，导致主循环只能拿到 10ms 内的微小增量（-2 ~ 0），看起来像噪声。

### 排查过程

1. 怀疑编码器硬件故障 → 交换左右编码器插头测试 → 问题跟随移动
2. 用 `cat /proc/interrupts` 确认 GPIO 中断正常触发
3. 注释 ISR 中的 `Motor_Control()` → 编码器读数正常 → 确认为读取竞争问题

### 解决

- **epoll 系统中**：只在 epoll 事件循环中独占读取编码器，不在 ISR 中读取
- **生产代码中**：ISR 读取并累积，主循环通过共享变量获取，不直接 read 设备

### 教训

- 破坏性读取的设备必须单点访问
- 怀疑硬件前先排查软件竞争条件
- `/proc/interrupts` 是诊断 GPIO/编码器中断的金标准
