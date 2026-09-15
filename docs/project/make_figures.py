from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

OUT = Path(__file__).resolve().parent / "report-assets" / "figures"
OUT.mkdir(exist_ok=True)

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, RULE = "#0b0b0b", "#52514e", "#cfcdc6"

mpl.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 11,
    "axes.titlesize": 11,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "axes.edgecolor": MUTED,
    "axes.linewidth": 0.8,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "figure.dpi": 400,
    "savefig.dpi": 400,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

def _despine(ax, keep=("left", "bottom")):
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)

def figure_v1_v3() -> None:
    labels = ["Nén JPEG\nchất lượng 70", "Co giãn\n0.75×", "Cắt cúp\ntrung tâm 25%"]
    v1_count, v1_total = [0, 0, 1], [12, 12, 3]
    v3_count, v3_total = [9, 8, 9], [12, 12, 12]
    v1 = [c / t * 100 for c, t in zip(v1_count, v1_total)]
    v3 = [c / t * 100 for c, t in zip(v3_count, v3_total)]

    fig, ax = plt.subplots(figsize=(6.3, 3.2))
    x = range(len(labels))
    width = 0.36
    left = [i - width / 2 - 0.01 for i in x]
    right = [i + width / 2 + 0.01 for i in x]

    ax.bar(left, v1, width, color=BLUE, label="Thế hệ V1", zorder=3)
    ax.bar(right, v3, width, color=ORANGE, label="Thế hệ V3", zorder=3)

    for xs, vals, counts, totals in ((left, v1, v1_count, v1_total),
                                     (right, v3, v3_count, v3_total)):
        for xi, val, c, t in zip(xs, vals, counts, totals):
            ax.text(xi, val + 2.2, f"{c}/{t}", ha="center", va="bottom",
                    fontsize=9.5, fontweight="bold", color=INK)

    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0", "25", "50", "75", "100"])
    ax.set_ylabel("Tỉ lệ giải mã thành công (%)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.yaxis.grid(True, color=RULE, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    _despine(ax)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, 1.02), ncol=2)
    fig.savefig(OUT / "chart-v1-vs-v3.png")
    plt.close(fig)

def figure_envelope() -> None:
    rows = [
        ("Giữ nguyên", 11, BLUE), ("JPEG 85", 11, BLUE), ("JPEG 70", 11, BLUE),
        ("Co giãn 1.50×", 11, BLUE), ("Co giãn 0.75×", 10, BLUE),
        ("Co giãn 0.50×", 9, BLUE), ("Cắt cúp 25%", 7, BLUE),
        ("Cắt cúp 10%", 2, ORANGE), ("Cắt cúp 50%", 0, ORANGE),
        ("Chụp màn hình 1920×1080", 0, ORANGE),
        ("Chụp màn hình 1366×768", 0, ORANGE),
        ("Chụp màn hình + phối cảnh", 0, ORANGE),
        ("JPEG 50", 0, AQUA),
    ]
    names = [r[0] for r in rows][::-1]
    vals = [r[1] for r in rows][::-1]
    cols = [r[2] for r in rows][::-1]

    fig, ax = plt.subplots(figsize=(6.3, 4.4))
    y = range(len(names))
    ax.barh(list(y), [max(val, 0.09) for val in vals], height=0.68, color=cols, zorder=3)
    for yi, val in zip(y, vals):
        ax.text(max(val, 0.09) + 0.18, yi, str(val), va="center", ha="left",
                fontsize=9.5, fontweight="bold", color=INK)

    ax.set_xlim(0, 12.6)
    ax.set_xticks([0, 3, 6, 9, 12])
    ax.set_xlabel("Số trang truy vết đúng (trên 12 trang dương tính)")
    ax.set_yticks(list(y))
    ax.set_yticklabels(names)
    ax.xaxis.grid(True, color=RULE, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    _despine(ax)

    handles = [
        Patch(facecolor=BLUE, label="Có giả thuyết hình học đúng, sóng mang sống"),
        Patch(facecolor=ORANGE, label="Thiếu giả thuyết hình học đúng"),
        Patch(facecolor=AQUA, label="Có giả thuyết đúng, sóng mang chết"),
    ]
    ax.legend(handles=handles, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, -0.16), fontsize=9.5, ncol=1,
              handlelength=1.6, handleheight=0.9, labelspacing=0.45)
    fig.savefig(OUT / "chart-attack-envelope.png")
    plt.close(fig)

def figure_letterbox() -> None:
    groups = ["1920×1080", "1366×768"]
    raw, stripped = [0, 0], [9, 0]

    fig, ax = plt.subplots(figsize=(6.3, 2.1))
    y = list(range(len(groups)))
    height = 0.32
    offset = height / 2 + 0.015
    top = [i - offset for i in y]
    bottom = [i + offset for i in y]

    ax.barh(top, [max(v, 0.09) for v in raw], height, color=ORANGE,
            label="Ảnh chụp màn hình thô", zorder=3)
    ax.barh(bottom, [max(v, 0.09) for v in stripped], height, color=BLUE,
            label="Sau khi bóc viền", zorder=3)
    for positions, values in ((top, raw), (bottom, stripped)):
        for position, value in zip(positions, values):
            ax.text(max(value, 0.09) + 0.2, position, f"{value}/12", va="center",
                    ha="left", fontsize=9.5, fontweight="bold", color=INK)

    ax.set_xlim(0, 12.8)
    ax.set_ylim(len(groups) - 0.55, -0.45)
    ax.set_xticks([0, 3, 6, 9, 12])
    ax.set_xlabel("Số trang truy vết đúng (trên 12 trang dương tính)")
    ax.set_yticks(y)
    ax.set_yticklabels(groups)
    ax.set_ylabel("Độ phân giải màn hình")
    ax.xaxis.grid(True, color=RULE, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    _despine(ax)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.38),
              ncol=2, fontsize=9.5, handlelength=1.6, handleheight=0.9,
              columnspacing=2.0)
    fig.savefig(OUT / "chart-frame-restore.png")
    plt.close(fig)

def figure_carrier() -> None:
    """Chất lượng nhúng đổi lấy độ bền, trên hai vật mang khác nhau."""

    qim = [24, 32, 48, 64]
    coarse_psnr = [44.09, 42.02, 39.16, 37.04]
    coarse_ok = [False, True, True, True]
    fine_psnr = [44.03, 41.91, 39.01, 36.95]
    fine_ok = [False, False, False, False]

    fig, ax = plt.subplots(figsize=(6.3, 3.5))
    x = list(range(len(qim)))

    ax.axhspan(30, 38, color=ORANGE, alpha=0.10, zorder=0)
    ax.axhline(38, color=ORANGE, linewidth=1.1, linestyle="--", zorder=2)
    ax.text(len(qim) - 0.55, 38.25, "cổng chất lượng 38 dB",
            fontsize=9, color=ORANGE, va="bottom", ha="right")

    ax.plot(x, coarse_psnr, color=BLUE, linewidth=1.2, zorder=3)
    ax.plot(x, fine_psnr, color=MUTED, linewidth=1.2, linestyle=":", zorder=3)

    for xi, value, ok in zip(x, coarse_psnr, coarse_ok):
        ax.scatter([xi], [value], s=90, zorder=4, color=BLUE if ok else "white",
                   edgecolors=BLUE, linewidths=1.4)
    for xi, value, ok in zip(x, fine_psnr, fine_ok):
        ax.scatter([xi], [value], s=90, zorder=4, marker="s",
                   color=MUTED if ok else "white", edgecolors=MUTED, linewidths=1.4)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{value}" for value in qim])
    ax.set_xlabel("Bước lượng tử QIM")
    ax.set_ylabel("PSNR sau khi nhúng (dB)")
    ax.set_ylim(35.5, 45.5)
    ax.set_xlim(-0.45, len(qim) - 0.55)
    ax.yaxis.grid(True, color=RULE, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    _despine(ax)

    handles = [
        Line2D([], [], color=BLUE, marker="o", markerfacecolor=BLUE,
               markeredgecolor=BLUE, markersize=8, linewidth=1.2,
               label="Trang chữ nét dày, 23,82 phần trăm điểm tối"),
        Line2D([], [], color=MUTED, marker="s", markerfacecolor="white",
               markeredgecolor=MUTED, markersize=8, linewidth=1.2, linestyle=":",
               label="Trang chữ nét mảnh, 9,24 phần trăm điểm tối"),
        Line2D([], [], color="none", marker="o", markerfacecolor=INK,
               markeredgecolor=INK, markersize=8,
               label="Ký hiệu tô đặc: truy được nguồn sau khi nén JPEG 70"),
        Line2D([], [], color="none", marker="o", markerfacecolor="white",
               markeredgecolor=INK, markersize=8,
               label="Ký hiệu rỗng: không truy được"),
    ]
    ax.legend(handles=handles, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, -0.20), fontsize=9, ncol=1,
              handlelength=1.8, labelspacing=0.35)
    fig.savefig(OUT / "chart-carrier-decides.png")
    plt.close(fig)


if __name__ == "__main__":
    figure_v1_v3()
    figure_envelope()
    figure_letterbox()
    figure_carrier()
    for name in ("chart-v1-vs-v3", "chart-attack-envelope", "chart-frame-restore", "chart-carrier-decides"):
        path = OUT / f"{name}.png"
        print(f"{path.name:34} {path.stat().st_size / 1024:7.1f} KB")
