#pragma once
#include <string>

class TcpAcceptor {
public:
    TcpAcceptor(int port);
    ~TcpAcceptor();

    int fd() const { return m_fd; }
    int port() const { return m_port; }

    // Start listening. Returns fd on success, -1 on failure.
    int start();

    // Accept one connection. Returns client_fd and IP, or {-1, ""}.
    struct AcceptResult {
        int fd;
        std::string ip;
    };
    AcceptResult accept();

private:
    int m_fd = -1;
    int m_port;
};
