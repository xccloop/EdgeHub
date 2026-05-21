/**
 * Kyl-Epoll: 龙芯 LS2K0300 智能车 epoll 可交互串口命令系统
 *
 * 架构：
 *   UART1 (/dev/ttyS1)  <-->  Epoll 事件循环  <-->  Shell 命令解析器
 *
 * 工作流：
 *   1. 初始化 UART1 (115200 8N1)
 *   2. 用 epoll_create1 创建 epoll 实例
 *   3. 注册 UART1 fd 到 epoll (EPOLLIN)
 *   4. 主循环 epoll_wait(100ms) 等待事件
 *   5. 有数据 → 逐字符读入行缓冲 → 回车后 execute(line) → prompt()
 *   6. 无超时 → 继续循环（可扩展做后台任务）
 */

#include "zf_common_headfile.h"
#include "uart1.hpp"
#include "epoll.hpp"
#include "shell.hpp"
#include "commands.hpp"

#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <errno.h>

#define INPUT_BUF_SIZE  256     // 命令行最大长度
#define EPOLL_TIMEOUT_MS 100    // epoll_wait 超时（ms），兼顾后台任务

int main()
{
    printf("\n");
    printf("========================================\n");
    printf("  Kyl-Epoll  Interactive Shell\n");
    printf("  Board:  LS2K0300 (loongarch64)\n");
    printf("  UART1:  /dev/ttyS1 @ 115200 8N1\n");
    printf("  Build:  %s %s\n", __DATE__, __TIME__);
    printf("========================================\n\n");

    // ---- 1. 初始化 UART1 ----
    if (uart1_init() != 0)
    {
        fprintf(stderr, "FATAL: uart1_init failed, exiting\n");
        return 1;
    }
    int uart_fd = uart1_get_fd();

    // ---- 2. 创建 epoll 实例 ----
    Epoll ep;
    if (!ep.create(8))
    {
        fprintf(stderr, "FATAL: epoll create failed, exiting\n");
        uart1_close();
        return 1;
    }

    // ---- 3. 注册 UART1 fd ----
    if (!ep.add(uart_fd, EPOLLIN))
    {
        fprintf(stderr, "FATAL: epoll add uart1 failed, exiting\n");
        uart1_close();
        return 1;
    }

    // ---- 4. 初始化命令 Shell ----
    Shell shell(32);
    register_builtin_commands(shell);

    // ---- 5. 行缓冲 ----
    char line_buf[INPUT_BUF_SIZE];
    int  line_pos = 0;
    memset(line_buf, 0, sizeof(line_buf));

    shell.prompt();

    // ---- 6. 事件循环 ----
    int loop_count = 0;
    while (1)
    {
        int nfds = ep.wait(EPOLL_TIMEOUT_MS);

        // --- 处理就绪事件 ---
        for (int i = 0; i < nfds; i++)
        {
            int fd = ep.ready_fd(i);
            uint32_t ev = ep.ready_events(i);

            // UART1 有数据可读
            if (fd == uart_fd && (ev & EPOLLIN))
            {
                char c;
                // 逐字符读取（避免行缓冲被截断）
                while (1)
                {
                    ssize_t n = read(uart_fd, &c, 1);
                    if (n <= 0)
                    {
                        // 无更多数据（EAGAIN）或出错
                        if (n < 0 && errno == EAGAIN) break;
                        break;
                    }

                    // 字符回显（终端体验）
                    if (c != '\r' && c != '\n')
                    {
                        write(uart_fd, &c, 1);   // 回显
                    }
                    else if (c == '\r')
                    {
                        write(uart_fd, "\r\n", 2); // 回车换行
                    }

                    // 处理回车/换行 → 执行命令
                    if (c == '\r' || c == '\n')
                    {
                        line_buf[line_pos] = '\0';
                        if (line_pos > 0)
                        {
                            shell.execute(line_buf);
                        }
                        line_pos = 0;
                        memset(line_buf, 0, sizeof(line_buf));
                        shell.prompt();
                    }
                    // 退格处理
                    else if (c == 0x7F || c == '\b')
                    {
                        if (line_pos > 0)
                        {
                            line_pos--;
                            line_buf[line_pos] = '\0';
                            // VT100 退格序列: \b \s \b
                            write(uart_fd, "\b \b", 3);
                        }
                    }
                    // 普通可打印字符
                    else if (c >= 0x20 && c <= 0x7E)
                    {
                        if (line_pos < INPUT_BUF_SIZE - 1)
                        {
                            line_buf[line_pos++] = c;
                        }
                    }
                }
            }

            // 异常事件
            if (ev & (EPOLLERR | EPOLLHUP))
            {
                fprintf(stderr, "epoll: fd=%d error/hangup (events=0x%x)\n", fd, ev);
                // UART 断开 → 尝试重新初始化
                if (fd == uart_fd)
                {
                    ep.del(uart_fd);
                    uart1_close();
                    sleep(1);
                    if (uart1_init() == 0)
                    {
                        uart_fd = uart1_get_fd();
                        ep.add(uart_fd, EPOLLIN);
                        printf("UART1 reconnected\n");
                        shell.prompt();
                    }
                }
            }
        }

        // --- 后台任务（无事件时执行，可用于状态更新等） ---
        loop_count++;
        if (loop_count % 100 == 0)
        {
            // 每 10 秒（100 * 100ms）可以做一些周期性检查
            // 例如：按键扫描、LED 闪烁、传感器轮询等
        }
    }

    // 清理（理论上不会到这里）
    ep.destroy();
    uart1_close();
    return 0;
}
