#include "shell.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cctype>

Shell::Shell(int max_cmds)
    : max_cmds_(max_cmds), cmd_count_(0)
{
    cmds_ = (ShellCmd*)calloc(max_cmds_, sizeof(ShellCmd));
    if (!cmds_)
    {
        fprintf(stderr, "Shell: calloc failed\n");
        max_cmds_ = 0;
    }
}

Shell::~Shell()
{
    if (cmds_)
    {
        free(cmds_);
        cmds_ = nullptr;
    }
}

bool Shell::register_cmd(const char *name, const char *help,
                         shell_cmd_handler_t handler)
{
    if (!cmds_ || cmd_count_ >= max_cmds_)
        return false;

    // 检查重名
    for (int i = 0; i < cmd_count_; i++)
    {
        if (strcmp(cmds_[i].name, name) == 0)
            return false;
    }

    cmds_[cmd_count_].name    = name;
    cmds_[cmd_count_].help    = help;
    cmds_[cmd_count_].handler = handler;
    cmd_count_++;
    return true;
}

int Shell::find_cmd(const char *name)
{
    for (int i = 0; i < cmd_count_; i++)
    {
        if (strcmp(cmds_[i].name, name) == 0)
            return i;
    }
    return -1;
}

// 简单的命令行 tokenizer：按空白分割
// 输入 line 会被原地修改（插入 \0 终止符）
// argv 最大 16 个参数
static int tokenize(char *line, char **argv, int max_args)
{
    int argc = 0;
    char *p = line;

    while (*p)
    {
        // 跳过前导空白
        while (*p && isspace((unsigned char)*p)) p++;
        if (!*p) break;

        argv[argc++] = p;

        // 找到 token 末尾
        while (*p && !isspace((unsigned char)*p)) p++;

        if (*p)
        {
            *p = '\0';
            p++;
        }

        if (argc >= max_args) break;
    }
    return argc;
}

void Shell::execute(const char *line)
{
    if (!line || !line[0]) return;

    // 拷贝到可修改缓冲区
    char buf[256];
    strncpy(buf, line, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';

    // strip 尾部 \r\n
    int len = (int)strlen(buf);
    while (len > 0 && (buf[len-1] == '\r' || buf[len-1] == '\n'))
        buf[--len] = '\0';
    if (len == 0) return;

    // 切分参数
    char *argv[16];
    int argc = tokenize(buf, argv, 16);
    if (argc == 0) return;

    // 查找命令
    int idx = find_cmd(argv[0]);
    if (idx < 0)
    {
        printf("Unknown command: '%s'. Type 'help' for list.\n", argv[0]);
        return;
    }

    // 执行
    cmds_[idx].handler(argc, argv);
}

void Shell::prompt()
{
    printf("kyl-epoll> ");
    fflush(stdout);
}

void Shell::print_help()
{
    printf("\n=== Kyl-Epoll Commands ===\n");
    for (int i = 0; i < cmd_count_; i++)
    {
        printf("  %-16s - %s\n", cmds_[i].name, cmds_[i].help);
    }
    printf("==========================\n");
}
