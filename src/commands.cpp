#include "commands.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>
#include <sys/sysinfo.h>
#include <sys/utsname.h>

// ============================================================================
// 内置命令实现
// ============================================================================

// ---- help ----------------------------------------------------------------
static void cmd_help(int argc, char **argv)
{
    (void)argc; (void)argv;
    // Shell::print_help() 是外部符号，这里通过全局 shell 指针调用
    // 实际在 main.cpp 的 register_builtin_commands 中通过 lambda/bind 注册
    printf("Available commands: help, status, echo, uptime, uname, reboot\n");
    printf("Type '<cmd> --help' for detailed usage.\n");
}

// ---- status --------------------------------------------------------------
static void cmd_status(int argc, char **argv)
{
    (void)argc; (void)argv;

    struct sysinfo si;
    if (sysinfo(&si) == 0)
    {
        long uptime_min = si.uptime / 60;
        printf("=== System Status ===\n");
        printf("  Uptime    : %ld min\n", uptime_min);
        printf("  Load      : %lu / %lu / %lu (1/5/15 min)\n",
               si.loads[0], si.loads[1], si.loads[2]);
        printf("  Total RAM : %lu MB\n", (si.totalram * si.mem_unit) / (1024*1024));
        printf("  Free RAM  : %lu MB\n", (si.freeram * si.mem_unit) / (1024*1024));
        printf("  Processes : %u\n", (unsigned)si.procs);
    }
    else
    {
        perror("sysinfo");
    }
}

// ---- echo ----------------------------------------------------------------
static void cmd_echo(int argc, char **argv)
{
    for (int i = 1; i < argc; i++)
    {
        if (i > 1) printf(" ");
        printf("%s", argv[i]);
    }
    printf("\n");
}

// ---- uptime --------------------------------------------------------------
static void cmd_uptime(int argc, char **argv)
{
    (void)argc; (void)argv;

    struct sysinfo si;
    if (sysinfo(&si) == 0)
    {
        long days  = si.uptime / 86400;
        long hours = (si.uptime % 86400) / 3600;
        long mins  = (si.uptime % 3600) / 60;
        printf("up %ld days, %ld:%02ld\n", days, hours, mins);
    }
}

// ---- uname ---------------------------------------------------------------
static void cmd_uname(int argc, char **argv)
{
    (void)argc; (void)argv;

    struct utsname buf;
    if (uname(&buf) == 0)
    {
        printf("%s %s %s %s %s\n",
               buf.sysname, buf.nodename, buf.release,
               buf.version, buf.machine);
    }
    else
    {
        perror("uname");
    }
}

// ---- reboot --------------------------------------------------------------
static void cmd_reboot(int argc, char **argv)
{
    (void)argc; (void)argv;

    printf("Rebooting in 1 second...\n");
    fflush(stdout);
    // 注意：需要 root 权限，否则 EPERM
    sync();
    if (system("reboot") != 0)
    {
        printf("reboot failed (need root?)\n");
    }
}

// ============================================================================
// 注册所有内置命令
// ============================================================================
void register_builtin_commands(Shell &shell)
{
    shell.register_cmd("help",   "Show available commands",               cmd_help);
    shell.register_cmd("status", "System resource status (RAM, load...)", cmd_status);
    shell.register_cmd("echo",   "Echo text back, usage: echo <text>",    cmd_echo);
    shell.register_cmd("uptime", "Show system uptime",                    cmd_uptime);
    shell.register_cmd("uname",  "Show kernel version and arch",          cmd_uname);
    shell.register_cmd("reboot", "Reboot the system (needs root)",        cmd_reboot);
}
