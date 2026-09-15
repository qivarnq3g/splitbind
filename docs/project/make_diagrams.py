from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

OUT = Path(__file__).resolve().parent / "report-assets" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, RULE = "#0b0b0b", "#52514e", "#cfcdc6"
FILL_HEAD, FILL_SOFT, FILL_OUT = "#e8f0fb", "#f5f4f1", "#eefaf4"

mpl.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.monospace": ["Consolas", "DejaVu Sans Mono"],
    "font.size": 11,
    "text.color": INK,
    "figure.dpi": 400,
    "savefig.dpi": 400,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def _canvas(width, height):
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_aspect("auto")
    ax.axis("off")
    return fig, ax


def _box(ax, x0, y0, x1, y1, facecolor="white", edgecolor=MUTED, lw=0.9, radius=1.2, z=2):
    patch = FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=lw, edgecolor=edgecolor, facecolor=facecolor, zorder=z,
    )
    ax.add_patch(patch)
    return patch


def _arrow(ax, x0, y0, x1, y1, color=MUTED, lw=1.0):
    ax.add_patch(FancyArrowPatch(
        (x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=10,
        linewidth=lw, color=color, shrinkA=0, shrinkB=0, zorder=3,
    ))


def _elbow(ax, x0, y0, x1, y1, color=MUTED, lw=1.0):
    ax.plot([x0, x0], [y0, y1], color=color, lw=lw, zorder=1, solid_capstyle="round")
    ax.plot([x0, x1], [y1, y1], color=color, lw=lw, zorder=1, solid_capstyle="round")


def diagram_manifest_signing() -> None:
    fig, ax = _canvas(6.3, 4.9)

    fields = [
        ("schema_version", "phiên bản lược đồ manifest"),
        ("issuance_id", "khoá liên kết tới bản cấp phát"),
        ("recipient_id", "người nhận tài liệu"),
        ("source_sha256", "mã băm tệp gốc"),
        ("output_sha256", "mã băm tệp sau khi cấp phát"),
        ("signing_key_id", "định danh khoá ký đang dùng"),
    ]

    top, head_h, row_h = 99.0, 7.6, 5.0
    bottom = top - head_h - row_h * len(fields)
    _box(ax, 6, bottom, 94, top, facecolor="none", edgecolor=BLUE, lw=1.1)
    ax.plot([6, 94], [top - head_h, top - head_h], color=BLUE, lw=0.8, zorder=3)
    ax.text(50, top - head_h / 2, "MANIFEST NỘI BỘ", ha="center", va="center",
            fontsize=10.5, fontweight="bold", color=BLUE, zorder=4)

    for i, (name, meaning) in enumerate(fields):
        y = top - head_h - row_h * (i + 0.5)
        ax.text(10, y, name, ha="left", va="center", fontsize=9.5,
                family="monospace", color=INK, zorder=4)
        ax.text(46, y, meaning, ha="left", va="center", fontsize=9.5,
                color=MUTED, zorder=4)

    steps = [
        ("Chuẩn tắc hoá theo RFC 8785 (JCS)",
         "chuỗi nhị phân UTF-8 xác định, bất biến thứ tự khoá"),
        ("Ký bằng khoá riêng Ed25519", None),
    ]
    y = bottom
    for label, note in steps:
        _arrow(ax, 50, y, 50, y - 5.2)
        y -= 5.2
        height = 11.0 if note else 8.0
        _box(ax, 14, y - height, 86, y, facecolor=FILL_SOFT, edgecolor=MUTED)
        if note:
            ax.text(50, y - height * 0.36, label, ha="center", va="center",
                    fontsize=10, color=INK, zorder=4)
            ax.text(50, y - height * 0.74, note, ha="center", va="center",
                    fontsize=8.8, color=MUTED, style="italic", zorder=4)
        else:
            ax.text(50, y - height / 2, label, ha="center", va="center",
                    fontsize=10, color=INK, zorder=4)
        y -= height

    _arrow(ax, 50, y, 50, y - 5.2)
    y -= 5.2
    _box(ax, 8, y - 9.0, 92, y, facecolor=FILL_OUT, edgecolor=AQUA, lw=1.1)
    ax.text(50, y - 4.5, '{"algorithm": "Ed25519", "signature": "Base64..."}',
            ha="center", va="center", fontsize=9.2, family="monospace",
            color=INK, zorder=4)

    ax.set_ylim(y - 10.5, 100)
    fig.savefig(OUT / "diagram-manifest-signing.png")
    plt.close(fig)


def diagram_architecture() -> None:
    fig, ax = _canvas(6.3, 5.2)

    def node(x0, y0, x1, y1, title, subtitle=None, mono=False,
             edge=MUTED, fill="white", bold=False):
        _box(ax, x0, y0, x1, y1, facecolor=fill, edgecolor=edge, lw=1.0)
        cx = (x0 + x1) / 2
        if subtitle:
            ax.text(cx, (y0 + y1) / 2 + 1.9, title, ha="center", va="center",
                    fontsize=9.4, fontweight="bold" if bold else "normal",
                    color=INK, zorder=4)
            ax.text(cx, (y0 + y1) / 2 - 2.4, subtitle, ha="center", va="center",
                    fontsize=8.0, color=MUTED, zorder=4,
                    family="monospace" if mono else "serif",
                    style="normal" if mono else "italic")
        else:
            ax.text(cx, (y0 + y1) / 2, title, ha="center", va="center",
                    fontsize=9.4, fontweight="bold" if bold else "normal",
                    color=INK, zorder=4)

    ax.text(50, 100, "TẦNG SẢN PHẨM", ha="center", va="top", fontsize=9,
            fontweight="bold", color=BLUE, zorder=4)

    node(34, 87, 66, 95.5, "Trình duyệt người dùng", edge=BLUE, fill=FILL_HEAD, bold=True)
    _arrow(ax, 50, 87, 50, 80)
    ax.text(51.5, 83.5, "HTTPS / TLS", ha="left", va="center", fontsize=8.2,
            color=MUTED, style="italic", zorder=4)

    node(30, 71.5, 70, 80, "Caddy Reverse Proxy", edge=BLUE, fill=FILL_HEAD, bold=True)

    ax.plot([50, 50], [71.5, 66], color=MUTED, lw=1.0, zorder=1)
    ax.plot([19, 81], [66, 66], color=MUTED, lw=1.0, zorder=1)
    _arrow(ax, 19, 66, 19, 60)
    _arrow(ax, 81, 66, 81, 60)

    node(1, 47, 37, 60, "Giao diện React", "apps/web, Vite", mono=True)
    node(63, 47, 99, 60, "Dịch vụ Django API", "services/api", mono=True)

    _arrow(ax, 81, 47, 81, 36)
    ax.text(82.5, 41.5, "truy vấn", ha="left", va="center", fontsize=8.0,
            color=MUTED, style="italic", zorder=4)
    node(63, 23, 91, 36, "Neon PostgreSQL 18", "siêu dữ liệu và manifest")

    node(31, 5, 69, 18, "Cloudflare R2", "đối tượng PDF và PNG",
         edge=ORANGE, fill="#fdf1ea")

    _elbow(ax, 19, 47, 27, 11.5)
    _arrow(ax, 27, 11.5, 31, 11.5)
    ax.text(2, 33.5, "tải thẳng qua liên kết", ha="left", va="center",
            fontsize=8.0, color=MUTED, style="italic", zorder=4)
    ax.text(2, 29.5, "S3 có thời hạn", ha="left", va="center",
            fontsize=8.0, color=MUTED, style="italic", zorder=4)

    _elbow(ax, 96, 47, 73, 11.5)
    _arrow(ax, 73, 11.5, 69, 11.5)
    ax.text(94.5, 19, "ghi và đọc đối tượng", ha="right", va="center",
            fontsize=8.0, color=MUTED, style="italic", zorder=4)

    ax.plot([0, 100], [-3, -3], color=RULE, lw=0.9, zorder=1)
    ax.text(50, -7.5, "TẦNG NGHIÊN CỨU VÀ KIỂM THỬ THUẬT TOÁN", ha="center",
            va="center", fontsize=9, fontweight="bold", color=AQUA, zorder=4)

    research = [
        (0, 30, "Bộ mã hoá đối chứng", "bản Python độc lập"),
        (35, 65, "Bộ trang mẫu tổng hợp", "12 trang chuẩn"),
        (70, 100, "Ma trận tấn công", "31 phép ảnh, 4 phép can thiệp"),
    ]
    for i, (x0, x1, title, subtitle) in enumerate(research):
        node(x0, -25, x1, -12, title, subtitle, edge=AQUA, fill="#eefaf4")
        if i:
            _arrow(ax, research[i - 1][1], -18.5, x0, -18.5, color=AQUA)

    ax.set_ylim(-26.5, 101)
    fig.savefig(OUT / "diagram-architecture.png")
    plt.close(fig)


if __name__ == "__main__":
    diagram_manifest_signing()
    diagram_architecture()
    print("da dung:", *(p.name for p in sorted(OUT.glob("diagram-*.png"))))
