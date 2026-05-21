#include "uart1.hpp"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <termios.h>
#include <sys/ioctl.h>

#define UART1_DEV       "/dev/ttyS1"
#define UART1_BAUDRATE  B115200

static int uart1_fd = -1;

//-----------------------------------------------------------------------------
// 初始化 UART1: 115200 8N1 无流控
//-----------------------------------------------------------------------------
int8 uart1_init(void)
{
    uart1_fd = open(UART1_DEV, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (uart1_fd < 0)
    {
        perror("uart1: open " UART1_DEV " failed");
        return -1;
    }

    struct termios opts;
    if (tcgetattr(uart1_fd, &opts) != 0)
    {
        perror("uart1: tcgetattr failed");
        close(uart1_fd);
        uart1_fd = -1;
        return -1;
    }

    // 设置波特率
    cfsetispeed(&opts, UART1_BAUDRATE);
    cfsetospeed(&opts, UART1_BAUDRATE);

    // 8N1, 无硬件流控, 无 modem 控制
    opts.c_cflag &= ~PARENB;        // 无校验
    opts.c_cflag &= ~CSTOPB;        // 1 停止位
    opts.c_cflag &= ~CSIZE;
    opts.c_cflag |= CS8;            // 8 数据位
    opts.c_cflag &= ~CRTSCTS;       // 无硬件流控
    opts.c_cflag |= CREAD | CLOCAL; // 启用接收, 忽略 modem 信号

    // 原始模式
    opts.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
    opts.c_iflag &= ~(IXON | IXOFF | IXANY); // 无软件流控
    opts.c_iflag &= ~(INLCR | ICRNL | IGNCR);
    opts.c_oflag &= ~OPOST;

    // VMIN=0, VTIME=5 → 500ms 超时
    opts.c_cc[VMIN]  = 0;
    opts.c_cc[VTIME] = 5;

    if (tcsetattr(uart1_fd, TCSANOW, &opts) != 0)
    {
        perror("uart1: tcsetattr failed");
        close(uart1_fd);
        uart1_fd = -1;
        return -1;
    }

    // 清空收发缓冲
    tcflush(uart1_fd, TCIOFLUSH);

    printf("uart1: /dev/ttyS1 opened, 115200 8N1\n");
    return 0;
}

//-----------------------------------------------------------------------------
// 关闭 UART1
//-----------------------------------------------------------------------------
void uart1_close(void)
{
    if (uart1_fd >= 0)
    {
        close(uart1_fd);
        uart1_fd = -1;
        printf("uart1: closed\n");
    }
}

//-----------------------------------------------------------------------------
// 发送数据 (阻塞直到全部发出)
//-----------------------------------------------------------------------------
int8 uart1_send(const uint8 *data, uint32 len)
{
    if (uart1_fd < 0 || data == NULL || len == 0)
        return -1;

    uint32 total = 0;
    while (total < len)
    {
        ssize_t n = write(uart1_fd, data + total, len - total);
        if (n < 0)
        {
            if (errno == EAGAIN || errno == EINTR)
                continue;
            perror("uart1: send error");
            return -1;
        }
        total += (uint32)n;
    }
    return 0;
}

//-----------------------------------------------------------------------------
// 接收数据 (阻塞模式, 超时 500ms)
// 返回实际接收字节数, 超时返回 0, 错误返回 -1
//-----------------------------------------------------------------------------
int32 uart1_recv(uint8 *buf, uint32 max_len)
{
    if (uart1_fd < 0 || buf == NULL || max_len == 0)
        return -1;

    ssize_t n = read(uart1_fd, buf, max_len);
    if (n < 0)
    {
        if (errno == EAGAIN || errno == EINTR)
            return 0;   // 超时或无数据
        perror("uart1: recv error");
        return -1;
    }
    return (int32)n;
}

//-----------------------------------------------------------------------------
// 获取 UART1 文件描述符（供 epoll 使用）
//-----------------------------------------------------------------------------
int uart1_get_fd(void)
{
    return uart1_fd;
}

//-----------------------------------------------------------------------------
// 检查接收缓冲区可用字节数 (非阻塞)
//-----------------------------------------------------------------------------
int32 uart1_available(void)
{
    if (uart1_fd < 0)
        return -1;

    int bytes = 0;
    if (ioctl(uart1_fd, FIONREAD, &bytes) != 0)
        return -1;
    return (int32)bytes;
}
