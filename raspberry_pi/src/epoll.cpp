#include "epoll.hpp"
#include <unistd.h>
#include <fcntl.h>
#include <cstdio>

Epoll::Epoll(int max_events)
    : m_max_events(max_events)
{
    m_epfd = epoll_create1(EPOLL_CLOEXEC);
    if (m_epfd < 0) {
        perror("epoll_create1");
    }
}

Epoll::~Epoll() {
    if (m_epfd >= 0) {
        close(m_epfd);
    }
}

bool Epoll::add(int fd, uint32_t events) {
    struct epoll_event ev;
    ev.events = events;
    ev.data.fd = fd;
    if (epoll_ctl(m_epfd, EPOLL_CTL_ADD, fd, &ev) < 0) {
        perror("epoll_ctl ADD");
        return false;
    }
    return true;
}

bool Epoll::mod(int fd, uint32_t events) {
    struct epoll_event ev;
    ev.events = events;
    ev.data.fd = fd;
    if (epoll_ctl(m_epfd, EPOLL_CTL_MOD, fd, &ev) < 0) {
        perror("epoll_ctl MOD");
        return false;
    }
    return true;
}

bool Epoll::del(int fd) {
    if (epoll_ctl(m_epfd, EPOLL_CTL_DEL, fd, nullptr) < 0) {
        perror("epoll_ctl DEL");
        return false;
    }
    return true;
}

int Epoll::wait(struct epoll_event *events, int max_events, int timeout_ms) {
    return epoll_wait(m_epfd, events, max_events, timeout_ms);
}
