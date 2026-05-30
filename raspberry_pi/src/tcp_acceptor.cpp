#include "tcp_acceptor.hpp"
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>
#include <cstdio>

TcpAcceptor::TcpAcceptor(int port) : m_port(port) {}

TcpAcceptor::~TcpAcceptor() {
    if (m_fd >= 0) close(m_fd);
}

int TcpAcceptor::start() {
    m_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (m_fd < 0) { perror("socket"); return -1; }

    int opt = 1;
    setsockopt(m_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(m_port);

    if (bind(m_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(m_fd);
        m_fd = -1;
        return -1;
    }

    if (listen(m_fd, SOMAXCONN) < 0) {
        perror("listen");
        close(m_fd);
        m_fd = -1;
        return -1;
    }

    printf("[acceptor] listening on :%d (fd=%d)\n", m_port, m_fd);
    return m_fd;
}

TcpAcceptor::AcceptResult TcpAcceptor::accept() {
    struct sockaddr_in client_addr;
    socklen_t addr_len = sizeof(client_addr);

    int client_fd = ::accept4(m_fd, (struct sockaddr *)&client_addr, &addr_len,
                               SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (client_fd < 0) {
        return {-1, ""};
    }

    char ip_buf[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &client_addr.sin_addr, ip_buf, sizeof(ip_buf));

    return {client_fd, std::string(ip_buf)};
}
