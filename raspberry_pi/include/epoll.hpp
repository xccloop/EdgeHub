#pragma once
#include <sys/epoll.h>
#include <vector>

class Epoll {
public:
    Epoll(int max_events = 64);
    ~Epoll();

    int fd() const { return m_epfd; }

    bool add(int fd, uint32_t events);
    bool mod(int fd, uint32_t events);
    bool del(int fd);

    // Returns number of ready events, -1 on error.
    int wait(struct epoll_event *events, int max_events, int timeout_ms);

private:
    int m_epfd;
    int m_max_events;
};
