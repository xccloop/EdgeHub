#include "epoll.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <unistd.h>

bool Epoll::create(int max_events)
{
    if (epfd_ >= 0) destroy();

    epfd_ = epoll_create1(0);
    if (epfd_ < 0)
    {
        perror("epoll: epoll_create1 failed");
        return false;
    }

    max_events_ = max_events;
    events_ = (struct epoll_event*)calloc(max_events_, sizeof(struct epoll_event));
    if (!events_)
    {
        perror("epoll: calloc events failed");
        close(epfd_);
        epfd_ = -1;
        return false;
    }

    printf("epoll: instance created, fd=%d, max_events=%d\n", epfd_, max_events_);
    return true;
}

void Epoll::destroy()
{
    if (events_)
    {
        free(events_);
        events_ = nullptr;
    }
    if (epfd_ >= 0)
    {
        close(epfd_);
        printf("epoll: instance destroyed (fd=%d)\n", epfd_);
        epfd_ = -1;
    }
    max_events_ = 0;
    ready_count_ = 0;
}

bool Epoll::add(int fd, uint32_t events)
{
    if (epfd_ < 0 || fd < 0) return false;

    struct epoll_event ev;
    memset(&ev, 0, sizeof(ev));
    ev.events   = events;
    ev.data.fd  = fd;

    if (epoll_ctl(epfd_, EPOLL_CTL_ADD, fd, &ev) < 0)
    {
        fprintf(stderr, "epoll: add fd=%d failed: %s\n", fd, strerror(errno));
        return false;
    }
    printf("epoll: fd=%d added (events=0x%x)\n", fd, events);
    return true;
}

bool Epoll::mod(int fd, uint32_t events)
{
    if (epfd_ < 0 || fd < 0) return false;

    struct epoll_event ev;
    memset(&ev, 0, sizeof(ev));
    ev.events   = events;
    ev.data.fd  = fd;

    if (epoll_ctl(epfd_, EPOLL_CTL_MOD, fd, &ev) < 0)
    {
        fprintf(stderr, "epoll: mod fd=%d failed: %s\n", fd, strerror(errno));
        return false;
    }
    return true;
}

bool Epoll::del(int fd)
{
    if (epfd_ < 0 || fd < 0) return false;

    if (epoll_ctl(epfd_, EPOLL_CTL_DEL, fd, nullptr) < 0)
    {
        fprintf(stderr, "epoll: del fd=%d failed: %s\n", fd, strerror(errno));
        return false;
    }
    printf("epoll: fd=%d removed\n", fd);
    return true;
}

int Epoll::wait(int timeout_ms)
{
    if (epfd_ < 0 || !events_) return -1;

    ready_count_ = epoll_wait(epfd_, events_, max_events_, timeout_ms);
    if (ready_count_ < 0)
    {
        if (errno == EINTR) return 0;  // 被信号中断，视为无事件
        perror("epoll: epoll_wait failed");
    }
    return ready_count_;
}

int Epoll::ready_fd(int i) const
{
    if (i < 0 || i >= ready_count_ || !events_) return -1;
    return events_[i].data.fd;
}

uint32_t Epoll::ready_events(int i) const
{
    if (i < 0 || i >= ready_count_ || !events_) return 0;
    return events_[i].events;
}
