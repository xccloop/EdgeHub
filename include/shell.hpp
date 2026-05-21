#ifndef SHELL_HPP
#define SHELL_HPP

#include "zf_common_typedef.h"

// 命令处理函数签名：argc=参数个数, argv=参数数组（argv[0]是命令名本身）
typedef void (*shell_cmd_handler_t)(int argc, char **argv);

// 命令注册表项
struct ShellCmd
{
    const char          *name;      // 命令名（小写）
    const char          *help;      // 帮助文本（一行）
    shell_cmd_handler_t  handler;   // 处理函数
};

// 串口交互命令 Shell — 基于 epoll 的事件驱动架构
class Shell
{
public:
    // max_cmds: 最大可注册命令数
    Shell(int max_cmds = 32);

    ~Shell();

    // 注册一条命令（返回 true 成功，false 表已满或重名）
    bool register_cmd(const char *name, const char *help,
                      shell_cmd_handler_t handler);

    // 解析并执行一行命令输入
    // line: 原始输入行（末尾可带 \r\n，内部会 strip）
    void execute(const char *line);

    // 打印命令提示符 "kyl-epoll> " 到串口（stdout）
    void prompt();

    // 打印所有已注册命令的帮助信息到串口
    void print_help();

    // 获取已注册命令数量
    int cmd_count() const { return cmd_count_; }

private:
    ShellCmd  *cmds_;
    int        max_cmds_;
    int        cmd_count_;

    // 按命令名查找，返回索引，找不到返回 -1
    int find_cmd(const char *name);
};

#endif
