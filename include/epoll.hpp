#ifndef EPOLL_HPP
#define EPOLL_HPP

#include <sys/epoll.h>
#include <cstdint>

// epoll 封装 — 简化 Linux epoll API 用于嵌入式交互系统
class Epoll
{
public:
    // 创建 epoll 实例，max_events 为预分配的事件槽数量
    // 返回 true 成功，false 失败（打印 perror）
    bool create(int max_events = 16);

    // 销毁 epoll 实例
    void destroy();

    // 注册 fd 到 epoll 监听（默认 EPOLLIN 边沿触发）
    bool add(int fd, uint32_t events = EPOLLIN | EPOLLET);

    // 修改已注册 fd 的监听事件
    bool mod(int fd, uint32_t events);

    // 从 epoll 移除 fd
    bool del(int fd);

    // 等待事件，返回就绪 fd 数量，-1 表示错误
    // timeout_ms: -1 永久阻塞, 0 立即返回, >0 超时毫秒
    int wait(int timeout_ms = -1);

    // 获取第 i 个就绪事件对应的 fd（wait 后调用）
    int ready_fd(int i) const;

    // 获取第 i 个就绪事件的 events 标志位
    uint32_t ready_events(int i) const;

    // 获取 epoll 自身的 fd（可加入另一个 epoll 实例）
    int get_fd() const { return epfd_; }

    // 获取上次 wait 返回的就绪数量
    int ready_count() const { return ready_count_; }

private:
    int               epfd_       = -1;
    int               max_events_ = 0;
    struct epoll_event *events_   = nullptr;
    int               ready_count_ = 0;
};

#endif
