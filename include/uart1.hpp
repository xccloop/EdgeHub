#ifndef _uart1_hpp_
#define _uart1_hpp_

#include "zf_common_typedef.h"

// 初始化 UART1 (/dev/ttyS1), 波特率 115200, 8N1
int8 uart1_init(void);

// 关闭 UART1
void  uart1_close(void);

// 发送数据 (阻塞直到全部发出)
int8  uart1_send(const uint8 *data, uint32 len);

// 接收数据 (阻塞模式, 带超时 500ms, 返回实际接收字节数, 错误返回 -1)
int32 uart1_recv(uint8 *buf, uint32 max_len);

// 检查接收缓冲区中有多少字节可读 (非阻塞)
int32 uart1_available(void);

// 获取 UART1 文件描述符（供 epoll 使用）
int   uart1_get_fd(void);

#endif
