#!/usr/bin/env python3
"""
日志可视化脚本 — 解析板子 log/ 中的 CSV 日志，生成 matplotlib 图表。

用法:
    python3 scripts/plot_log.py log/main_20260515_143022.log          # 默认输出到同目录 .png
    python3 scripts/plot_log.py log/main_20260515_143022.log -o out/  # 指定输出目录
    python3 scripts/plot_log.py log/main_20260515_143022.log --show   # 弹出窗口显示

支持的 CSV 列名（自动识别）:
    编码器模式: t, left_enc, right_enc, left_delta, right_delta
    通用模式:   任意以 t/time 开头 + 数值列的 CSV
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 无头模式，不弹窗口
import matplotlib.pyplot as plt
import numpy as np


# ──────────────────────────────────────────────────────────────────────
# 配色方案 — 暗色风格，适合在终端下查看
# ──────────────────────────────────────────────────────────────────────
COLORS = {
    "left":  "#00bcd4",  # 青色
    "right": "#ff6f00",  # 橙色
    "grid":  "#333333",
    "bg":    "#1a1a2e",
    "text":  "#e0e0e0",
}
plt.rcParams.update({
    "figure.facecolor": COLORS["bg"],
    "axes.facecolor": "#16213e",
    "axes.edgecolor": COLORS["grid"],
    "axes.labelcolor": COLORS["text"],
    "text.color": COLORS["text"],
    "xtick.color": COLORS["text"],
    "ytick.color": COLORS["text"],
    "grid.color": COLORS["grid"],
    "grid.alpha": 0.3,
    "legend.facecolor": "#16213e",
    "legend.edgecolor": COLORS["grid"],
    "savefig.facecolor": COLORS["bg"],
    "savefig.dpi": 150,
    "figure.dpi": 100,
})


# ──────────────────────────────────────────────────────────────────────
# 日志解析
# ──────────────────────────────────────────────────────────────────────
def parse_csv_log(filepath: str) -> dict:
    """解析 CSV 日志文件，跳过 # 注释行，返回 {col_name: [values]}"""
    data = defaultdict(list)
    headers = None

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # 用 csv 模块解析，容忍空格
            reader = csv.reader([line])
            row = next(reader)
            row = [c.strip() for c in row]

            if headers is None:
                # 第一行数据 → 自动命名列
                # 如果看起来像表头（含非数字字符），作为 header
                if any(not _is_numberish(c) for c in row):
                    headers = row
                    continue
                else:
                    # 否则自动生成列名
                    headers = [f"col_{i}" for i in range(len(row))]
                    # 回退处理当前行
                    for i, val in enumerate(row):
                        data[headers[i]].append(_to_float(val))
                    continue

            for i, val in enumerate(row):
                if i < len(headers):
                    data[headers[i]].append(_to_float(val))

    return dict(data)


def _is_numberish(s: str) -> bool:
    """判断字符串是否可以转为数字"""
    try:
        float(s)
        return True
    except ValueError:
        return False


def _to_float(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return 0.0


# ──────────────────────────────────────────────────────────────────────
# 智能列名映射
# ──────────────────────────────────────────────────────────────────────
def map_columns(data: dict) -> tuple:
    """
    从数据中智能识别时间列、左编码器列、右编码器列等。
    返回 (time_col, left_col, right_col, extra_cols)
    """
    cols = list(data.keys())
    time_col = None
    left_col = None
    right_col = None

    # 找时间列
    for c in cols:
        if c.lower() in ("t", "time", "timestamp", "time_s", "t_s"):
            time_col = c
            break

    # 找左右编码器列
    for c in cols:
        cl = c.lower()
        if "left" in cl and ("enc" in cl or "delta" not in cl):
            if left_col is None:
                left_col = c
        elif "right" in cl and ("enc" in cl or "delta" not in cl):
            if right_col is None:
                right_col = c

    # 如果没找到明确的，就用第 2、3 列作为左右
    if left_col is None and len(cols) >= 2:
        left_col = cols[1]
    if right_col is None and len(cols) >= 3:
        right_col = cols[2]

    # 其余列
    extra_cols = [c for c in cols if c not in (time_col, left_col, right_col)]

    return time_col, left_col, right_col, extra_cols


# ──────────────────────────────────────────────────────────────────────
# 绘图函数
# ──────────────────────────────────────────────────────────────────────
def plot_encoder_data(data: dict, filepath: str, output_path: str,
                      time_col: str, left_col: str, right_col: str,
                      extra_cols: list):
    """主绘图函数 — 生成多子图"""
    t = np.array(data.get(time_col, list(range(len(data.get(left_col, []))))))
    left = np.array(data.get(left_col, [])) if left_col else np.array([])
    right = np.array(data.get(right_col, [])) if right_col else np.array([])

    # 计算 delta（如果数据中没提供）
    if len(left) > 1:
        left_delta = np.diff(left, prepend=left[0])
        right_delta = np.diff(right, prepend=right[0])
        # 对齐时间
        if len(t) == len(left):
            t_delta = t
        else:
            t_delta = np.arange(len(left_delta))
    else:
        left_delta = np.array([])
        right_delta = np.array([])
        t_delta = np.array([])

    # 如果 CSV 本身有 delta 列，优先使用
    for c in extra_cols:
        if "left" in c.lower() and "delta" in c.lower():
            left_delta = np.array(data[c])
        if "right" in c.lower() and "delta" in c.lower():
            right_delta = np.array(data[c])

    # ── 创建 2×2 子图 ──
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"编码器测试 — {os.path.basename(filepath)}",
                 fontsize=14, fontweight="bold", y=0.98)

    # ── 图1: 编码器累计值 ──
    ax1 = axes[0, 0]
    ax1.set_title("编码器累计计数", fontsize=12, pad=10)
    if len(left) > 0:
        ax1.plot(t, left, color=COLORS["left"], linewidth=1.8, label="左轮 (left_enc)")
    if len(right) > 0:
        ax1.plot(t, right, color=COLORS["right"], linewidth=1.8, label="右轮 (right_enc)")
    ax1.set_xlabel("时间 (s)")
    ax1.set_ylabel("编码器计数")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=0, color="#555555", linewidth=0.8, linestyle="--")

    # ── 图2: 速度（delta / 100ms） ──
    ax2 = axes[0, 1]
    ax2.set_title("轮速 (每100ms增量)", fontsize=12, pad=10)
    if len(left_delta) > 0:
        ax2.plot(t_delta, left_delta, color=COLORS["left"], linewidth=1.5,
                 alpha=0.8, label="左轮 Δ")
    if len(right_delta) > 0:
        ax2.plot(t_delta, right_delta, color=COLORS["right"], linewidth=1.5,
                 alpha=0.8, label="右轮 Δ")
    ax2.set_xlabel("时间 (s)")
    ax2.set_ylabel("Δ 编码器 / 100ms")
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color="#555555", linewidth=0.8, linestyle="--")

    # ── 图3: 左轮 vs 右轮 散点 ──
    ax3 = axes[1, 0]
    ax3.set_title("左右轮相关性", fontsize=12, pad=10)
    if len(left) > 0 and len(right) > 0:
        ax3.scatter(left, right, c=t, cmap="plasma", s=12, alpha=0.8)
        # 理想对角线
        all_vals = np.concatenate([left, right])
        mn, mx = all_vals.min(), all_vals.max()
        if mx > mn:
            ax3.plot([mn, mx], [mn, mx], color="#555555", linewidth=0.8,
                     linestyle="--", label="理想对称线")
            ax3.legend(fontsize=9)
    ax3.set_xlabel("左轮编码器")
    ax3.set_ylabel("右轮编码器")
    ax3.grid(True, alpha=0.3)

    # ── 图4: 统计摘要 ──
    ax4 = axes[1, 1]
    ax4.set_title("统计摘要", fontsize=12, pad=10)
    ax4.axis("off")

    lines = []
    lines.append(f"数据点数: {len(left)}")
    if len(t) > 0:
        lines.append(f"时间跨度: {t[0]:.1f}s ~ {t[-1]:.1f}s ({t[-1]-t[0]:.1f}s)")
    if len(left) > 0:
        lines.append(f"左轮范围: {left.min()} ~ {left.max()}  (Δ={left.max()-left.min()})")
    if len(right) > 0:
        lines.append(f"右轮范围: {right.min()} ~ {right.max()}  (Δ={right.max()-right.min()})")
    if len(left_delta) > 0:
        lines.append(f"左轮平均 Δ: {left_delta.mean():.1f}")
    if len(right_delta) > 0:
        lines.append(f"右轮平均 Δ: {right_delta.mean():.1f}")

    # 编码器方向诊断
    if len(left) > 1 and len(right) > 1:
        left_trend = "正转 ✓" if left[-1] > left[0] else "反转/不动 ✗"
        right_trend = "正转 ✓" if right[-1] > right[0] else "反转/不动 ✗"
        left_d = left[-1] - left[0]
        right_d = right[-1] - right[0]
        lines.append(f"左轮趋势: {left_trend} ({left_d:+d})")
        lines.append(f"右轮趋势: {right_trend} ({right_d:+d})")

        if abs(left_d) > 10 and abs(right_d) > 10:
            ratio = abs(right_d / left_d) if left_d != 0 else float("inf")
            lines.append(f"左右比率: {ratio:.2f}")
            if 0.5 <= ratio <= 2.0:
                lines.append("→ 左右基本对称")
            else:
                lines.append("→ ⚠ 左右不对称，需排查")

    y_pos = 0.95
    for line in lines:
        ax4.text(0.05, y_pos, line, transform=ax4.transAxes,
                 fontsize=10, fontfamily="monospace", color=COLORS["text"])
        y_pos -= 0.09

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(output_path, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close(fig)

    return output_path


# ──────────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="板子日志可视化工具 — 解析 CSV 日志并生成图表",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s log/main_20250515_143022.log           # 生成同名 PNG
  %(prog)s log/main_20250515_143022.log -o out/   # 输出到指定目录
  %(prog)s log/main_20250515_143022.log --show    # 弹窗预览
        """,
    )
    parser.add_argument("logfile", help="CSV 日志文件路径")
    parser.add_argument("-o", "--output", default=None,
                        help="输出目录 (默认: 日志文件同目录)")
    parser.add_argument("--show", action="store_true",
                        help="弹出窗口显示图表 (需要 GUI)")
    parser.add_argument("--title", default=None,
                        help="图表标题 (默认使用文件名)")

    args = parser.parse_args()

    # 检查输入文件
    if not os.path.isfile(args.logfile):
        print(f"❌ 日志文件不存在: {args.logfile}", file=sys.stderr)
        sys.exit(1)

    # 确定输出路径
    log_path = Path(args.logfile)
    if args.output:
        out_dir = Path(args.output)
    else:
        out_dir = log_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(out_dir / f"{log_path.stem}.png")

    # 解析数据
    print(f"📖 解析日志: {args.logfile}")
    data = parse_csv_log(args.logfile)

    if not data:
        print("❌ 日志中没有有效数据行", file=sys.stderr)
        sys.exit(1)

    print(f"   找到 {len(data)} 列, {len(list(data.values())[0])} 行数据")
    print(f"   列名: {list(data.keys())}")

    # 智能列映射
    time_col, left_col, right_col, extra_cols = map_columns(data)
    print(f"   时间列: {time_col}, 左列: {left_col}, 右列: {right_col}")

    # 绘图
    if args.show:
        matplotlib.use("TkAgg")  # 切换回 GUI 后端

    out = plot_encoder_data(data, args.logfile, output_path,
                            time_col, left_col, right_col, extra_cols)
    print(f"✅ 图表已保存: {out}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
