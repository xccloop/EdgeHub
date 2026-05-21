# epoll 工作原理详解

## 目录

1. [为什么需要 epoll](#1-为什么需要-epoll)
2. [epoll 核心数据结构](#2-epoll-核心数据结构)
3. [API 详解](#3-api-详解)
4. [边沿触发 vs 水平触发](#4-边沿触发-vs-水平触发)
5. [内核实现原理](#5-内核实现原理)
6. [本项目的 epoll 封装设计](#6-本项目的-epoll-封装设计)

---

## 1. 为什么需要 epoll

### 传统 I/O 模型的局限

**阻塞 I/O：**
```c
char buf[256];
int n = read(fd, buf, sizeof(buf));  // 阻塞直到有数据
```
问题：单 fd 还好，多 fd 时一个阻塞导致其他 fd 无法响应。

**非阻塞轮询：**
```c
fcntl(fd, F_SETFL, O_NONBLOCK);
while (1) {
    int n = read(fd1, buf, sizeof(buf));  // 忙轮询
    int m = read(fd2, buf, sizeof(buf));  // CPU 100%
}
```
问题：CPU 空转，浪费资源。

**select/poll：**
```c
fd_set rfds;
FD_ZERO(&rfds);
FD_SET(fd1, &rfds);
FD_SET(fd2, &rfds);
select(max_fd+1, &rfds, NULL, NULL, NULL);
```
问题：需要遍历所有 fd（O(n)），最大 fd 数量有限（FD_SETSIZE=1024）。

### epoll 的优势

| 特性 | select/poll | epoll |
|------|------------|-------|
| 时间复杂度 | O(n) 遍历所有 fd | O(1) 只返回就绪 fd |
| fd 数量限制 | 1024 (select), 无限制但慢 (poll) | 无限制（受系统内存约束） |
| 内核-用户态拷贝 | 每次 wait 拷贝整个 fd_set | 只拷贝就绪事件 |
| 触发模式 | 仅水平触发 | 支持水平触发 (LT) 和边沿触发 (ET) |
| fd 增删效率 | O(n) 重建集合 | O(1) 红黑树增删 |

---

## 2. epoll 核心数据结构

### 用户态 API 结构

```c
struct epoll_event {
    uint32_t     events;    // 事件类型：EPOLLIN/EPOLLOUT/EPOLLERR...
    epoll_data_t data;      // 用户数据（联合体）
};

typedef union epoll_data {
    void    *ptr;           // 通用指针
    int      fd;            // 文件描述符
    uint32_t u32;
    uint64_t u64;
} epoll_data_t;
```

### 内核态数据结构

```
epoll 实例
  ├── 红黑树 (rbtree)    ← 存储所有被监听的 fd
  │     key = [fd, file*]
  │     value = epitem { fd, events, callback }
  │
  └── 就绪链表 (rdllist) ← 存储已就绪的 epitem
        head → item1 → item2 → ... → tail
         ↑ 回调函数将就绪 item 插入此处
```

**epitem 结构（内核）**：
```c
struct epitem {
    struct rb_node      rbn;        // 红黑树节点
    struct list_head    rdllink;    // 就绪链表节点
    struct epoll_filefd ffd;        // {fd, file*}
    struct eventpoll   *ep;         // 所属 epoll 实例
    struct epoll_event  event;      // 用户注册的事件
    wait_queue_head_t   pwqlist;    // 等待队列（设备就绪时唤醒）
};
```

**eventpoll 结构（内核）**：
```c
struct eventpoll {
    struct mutex        mtx;        // 互斥锁
    wait_queue_head_t   wq;         // epoll_wait 的等待队列
    wait_queue_head_t   poll_wait;  // file->poll() 使用的等待队列
    struct list_head    rdllist;    // 就绪 fd 链表
    struct rb_root_cached rbr;      // 红黑树（缓存最近节点）
    struct epitem      *ovflist;    // 溢出列表（锁竞争时暂存）
};
```

---

## 3. API 详解

### 3.1 epoll_create1

```c
int epoll_create1(int flags);
```

- 创建 epoll 实例，返回 epoll fd
- `flags=0`：等价于旧版 epoll_create(size)，size 参数被忽略
- `flags=EPOLL_CLOEXEC`：设置 close-on-exec 标志（推荐）
- 返回值：成功返回 fd，失败返回 -1 并设置 errno

**内核操作**：
1. 分配 `struct eventpoll` 和 `struct file`
2. 初始化红黑树（空树）和就绪链表（空链表）
3. 返回指向 epoll 实例的 fd

### 3.2 epoll_ctl

```c
int epoll_ctl(int epfd, int op, int fd, struct epoll_event *event);
```

- `epfd`：epoll 实例 fd
- `op`：操作类型
  - `EPOLL_CTL_ADD`：添加 fd 到监听集合
  - `EPOLL_CTL_MOD`：修改已监听 fd 的事件掩码
  - `EPOLL_CTL_DEL`：从监听集合移除 fd
- `fd`：被监听的文件描述符
- `event`：要监听的事件（EPOLLIN/EPOLLOUT/EPOLLET 等）

**EPOLL_CTL_ADD 内核流程**：

```
1. 检查 fd 是否已在红黑树中（防重复添加）
2. 分配 struct epitem
3. 将 epitem 插入红黑树
4. 在目标文件上注册回调函数 ep_poll_callback
   → 调用 file->f_op->poll(file, &epq.pt)
   → 如果 fd 当前已就绪，直接回调一次
5. 返回 0
```

**关键：回调注册机制**

```c
// 简化版内核回调
static int ep_poll_callback(wait_queue_entry_t *wait, unsigned mode,
                             int sync, void *key)
{
    struct epitem *epi = container_of(wait, struct epitem, wait);
    // 1. 将 epitem 加入 eventpoll 的就绪链表
    list_add_tail(&epi->rdllink, &ep->rdllist);
    // 2. 唤醒 epoll_wait 的等待者
    wake_up(&ep->wq);
    return 1;
}
```

### 3.3 epoll_wait

```c
int epoll_wait(int epfd, struct epoll_event *events,
               int maxevents, int timeout);
```

- `events`：输出参数，存放就绪事件数组
- `maxevents`：最多返回的事件数
- `timeout`：超时毫秒（-1=永久阻塞，0=立即返回）

**内核流程**：

```
1. 检查就绪链表是否非空
   ├── 非空 → 跳过等待，直接进入步骤 4
   └── 为空 → 进入步骤 2

2. 将当前进程加入 eventpoll.wq 等待队列

3. 调度出去 (schedule_hrtimeout)，直到：
   ├── 回调函数唤醒（有 fd 就绪）
   ├── 超时到期
   └── 信号中断

4. 从就绪链表取出 epitem，拷贝 events 到用户空间

5. 可选：如果是水平触发 (LT)，将仍就绪的 fd 重新放回就绪链表

6. 返回拷贝的事件数量
```

**epoll_wait 只返回就绪事件——不遍历红黑树！** 这就是 O(1) 的秘诀。

---

## 4. 边沿触发 vs 水平触发

### 水平触发 (Level Triggered, LT) — 默认模式

```
数据到达 fd → 内核回调 → epitem 入就绪链表
epoll_wait 返回 → 用户 read 部分数据 → 仍有数据未读完
下一次 epoll_wait → 仍返回该 fd（因为缓冲未空）
```

**特点**：只要 fd 缓冲有数据，每次 epoll_wait 都会返回
**适用**：阻塞 fd，简单可靠，不会丢事件

### 边沿触发 (Edge Triggered, ET) — 本项目使用

```
数据到达 fd → 内核回调 → epitem 入就绪链表
epoll_wait 返回 → 用户 read 全部数据 → 缓冲空
新数据到达 → 再次回调 → 再次入就绪链表
```

**特点**：只在状态变化时通知一次，必须读到 EAGAIN 为止
**适用**：非阻塞 fd + while 循环读到空，高性能场景

### 为什么本项目使用 ET 模式

1. **减少 epoll_wait 返回次数**：不会因为没读完而反复返回同一 fd
2. **精确事件通知**：每次返回意味着"有新数据到达"
3. **配合非阻塞 fd**：串口 fd 已设置为 O_NONBLOCK

### ET 模式下的正确 read 方式

```c
// 错误：只读一次，可能数据没读完
int n = read(fd, buf, size);

// 正确：循环读到 EAGAIN 为止
while (1) {
    ssize_t n = read(fd, &c, 1);
    if (n < 0) {
        if (errno == EAGAIN) break;  // 缓冲已空
        // 真实错误
        break;
    }
    if (n == 0) break;  // EOF（串口一般不会）
    // 处理字符 c
}
```

---

## 5. 内核实现原理

### 5.1 事件通知路径

```
硬件中断 → 设备驱动 → tty_flip_buffer_push()
  → tty 线路规程 → n_tty_receive_buf()
  → 唤醒 tty 的等待队列
  → ep_poll_callback() 被调用
  → 将 epitem 加入 eventpoll.rdllist
  → 唤醒 epoll_wait 的等待者
  → 用户态 epoll_wait() 返回
```

### 5.2 epoll 的内存开销

每个被监听的 fd 占用约 1KB 内核内存：

```
epitem 结构体:     ~200 字节
红黑树节点开销:    ~48 字节
等待队列开销:      ~72 字节
内核文件引用:      ~400 字节
回调数据:          ~200 字节
─────────────────────────
合计:              ~1KB / fd
```

本系统只监听 1 个 UART fd，内存开销可忽略。

### 5.3 epoll 的惊群问题

多进程/线程同时 epoll_wait 同一 epfd 时，一个事件可能唤醒所有等待者，
但只有一个能处理，其他白唤醒（惊群）。

Linux 4.5+ 通过 `EPOLLEXCLUSIVE` 标志解决，但本系统单线程无此问题。

---

## 6. 本项目的 epoll 封装设计

### Epoll 类 API 简化

```cpp
class Epoll
{
    bool create(int max_events = 16);   // epoll_create1(EPOLL_CLOEXEC)
    bool add(int fd, uint32_t events);  // epoll_ctl(EPOLL_CTL_ADD)
    bool mod(int fd, uint32_t events);  // epoll_ctl(EPOLL_CTL_MOD)
    bool del(int fd);                   // epoll_ctl(EPOLL_CTL_DEL)
    int  wait(int timeout_ms = -1);     // epoll_wait
    int  ready_fd(int i) const;         // 就绪 fd 列表索引
};
```

### 事件循环

```cpp
Epoll ep;  ep.create(8);  ep.add(uart_fd, EPOLLIN);

while (1) {
    int n = ep.wait(100);  // 100ms 超时，兼顾后台任务

    for (int i = 0; i < n; i++) {
        int fd = ep.ready_fd(i);
        // 逐字符读取到行缓冲
        // 回车 → execute(line) → prompt()
    }

    // 超时期间可执行后台任务（状态监控、LED 闪烁等）
}
```

### 扩展指南

添加新的被监控 fd（如按键 GPIO、编码器）：

```cpp
// 1. 打开设备
int key_fd = open("/dev/input/event0", O_RDONLY | O_NONBLOCK);

// 2. 注册到 epoll
ep.add(key_fd, EPOLLIN);

// 3. 在事件循环中处理
if (fd == key_fd) { read_and_handle_key(); }
```
