"""Assemble the submittable report (DOCX) from the SSOT knowledge base.

The knowledge base is a working document: it carries internal aids (defence Q&A,
claim-safety rules, slide mapping) that belong to the team, not to the examiner.
This script selects the chapters that form the report, renumbers them, adds the
front matter and a conclusion, and hands the result to pandoc.

It never edits the knowledge base. Re-run it after any change there.

    python build_report.py && pandoc <out>.md -o <out>.docx --toc
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "btl-nhom-9-knowledge-base.md"
OUT_MD = HERE / "BaoCao-BTL-ATTT-Nhom9.md"
OUT_DOCX = HERE / "BaoCao-BTL-ATTT-Nhom9.docx"

# (source PHẦN number, new chapter number, chapter title)
CHAPTERS = [
    (1, 1, "GIỚI THIỆU ĐỀ TÀI VÀ QUY ƯỚC NGỮ NGHĨA"),
    (2, 2, "CƠ SỞ LÝ THUYẾT KỸ THUẬT DIGITAL WATERMARKING"),
    (3, 3, "ỨNG DỤNG THỦY VÂN TRONG TRUY VẾT VÀ TOÀN VẸN HÌNH ẢNH"),
    (4, 4, "ỨNG DỤNG CHỮ KÝ SỐ TRONG BẢO VỆ THÔNG TIN TRUY VẾT"),
    (5, 5, "SO SÁNH CÁC KỸ THUẬT XÁC MINH BẢO VỆ TÍNH TOÀN VẸN"),
    (6, 6, "HỆ THỐNG SPLITBIND: KIẾN TRÚC VÀ HIỆN THỰC"),
    (7, 7, "KẾT QUẢ THỰC NGHIỆM"),
    (13, 8, "ĐỀ XUẤT KIẾN TRÚC V4: CHẨN ĐOÁN NGUYÊN NHÂN GỐC VÀ HƯỚNG SỬA"),
]
# Excluded by design: PHẦN 8 (defence Q&A), 9 (claim safety), 10 (slide mapping)
# are internal preparation aids. PHẦN 11 and 12 become back matter below.

TITLE_PAGE = """---
title: "TÌM HIỂU VÀ ĐỀ XUẤT HỆ THỐNG TRUY VẾT TOÀN VẸN VĂN BẢN"
subtitle: "Báo cáo Bài tập lớn — Môn An toàn thông tin"
author: "Nhóm 9 — Lớp học phần 012012303303"
lang: vi
---

# TÌM HIỂU VÀ ĐỀ XUẤT HỆ THỐNG TRUY VẾT TOÀN VẸN VĂN BẢN

**Báo cáo Bài tập lớn — Môn An toàn thông tin**

| | |
|---|---|
| Đề tài | Tìm hiểu và đề xuất Hệ thống truy vết toàn vẹn văn bản |
| Nhóm thực hiện | Nhóm 9 |
| Lớp học phần | 012012303303 |
| Giảng viên hướng dẫn | TS. Hồ Đăng Thế |
| Hệ thống minh hoạ | SplitBind |

## Phạm vi và quy ước trình bày

Báo cáo bám sát bốn nội dung được giao: lý thuyết kỹ thuật Digital Watermarking; ứng dụng thủy vân trong truy vết thay đổi hình ảnh; ứng dụng ký số trong bảo vệ thông tin truy vết; và so sánh với các kỹ thuật xác minh bảo vệ tính toàn vẹn khác. Bốn nội dung này tương ứng lần lượt với các Chương 2, 3, 4 và 5.

Chương 6 và 7 trình bày hệ thống SplitBind mà nhóm đã hiện thực và đo đạc để kiểm chứng phần lý thuyết. Chương 8 là phần **đề xuất** của nhóm: một chẩn đoán nguyên nhân gốc dựa trên số liệu đo được, kèm phép kiểm chứng đã thực hiện.

Mọi khẳng định kỹ thuật và số liệu trong báo cáo đều được gắn một trong năm nhãn phân định cấp độ tri thức sau, nhằm phân biệt rạch ròi giữa lý thuyết kinh điển, tính năng đã hiện thực, kết quả đo được và giới hạn đã nhận diện:

1. `[Established theory]` — tri thức khoa học kinh điển từ giáo trình, sách chuyên khảo, bài báo khoa học hoặc tiêu chuẩn quốc tế.
2. `[Implemented]` — tính năng hoặc thuật toán đã được cài đặt thành mã nguồn cụ thể.
3. `[Experimentally observed]` — kết quả đo lường sinh ra từ kịch bản benchmark có artifact lưu vết và mã băm SHA-256 xác thực.
4. `[Production]` — tính năng đang hoạt động thực tế trên môi trường máy chủ của phiên bản phát hành hiện hành.
5. `[Limitation]` — giới hạn kỹ thuật đã nhận diện, ranh giới thất bại của thuật toán, hoặc tính năng được chủ động khoá lại.

Nhóm chủ trương công bố giới hạn thay vì che giấu: các kết quả âm tính và các giả thuyết đã bị bác bỏ đều được trình bày đầy đủ, vì chúng là một phần của đóng góp khoa học.

\\newpage

"""

CONCLUSION = """# CHƯƠNG 9. KẾT LUẬN

## 9.1. Kết quả đạt được

Báo cáo đã hoàn thành bốn nội dung được giao. Về lý thuyết, nhóm trình bày cơ sở kỹ thuật Digital Watermarking, phân loại theo miền nhúng và theo mục tiêu an ninh, cùng bài toán đánh đổi giữa độ bền, tính vô hình và dung lượng tải trọng (Chương 2). Về ứng dụng, nhóm phân tích vai trò của thủy vân bền vững trong truy vết nguồn phát hành và của thủy vân bán mỏng manh trong định vị can thiệp (Chương 3), vai trò của chữ ký số Ed25519 trên manifest chuẩn tắc RFC 8785 trong bảo vệ thông tin truy vết (Chương 4), và đặt sáu kỹ thuật toàn vẹn cạnh nhau trên bảy tiêu chí an ninh (Chương 5).

Điểm khác biệt của báo cáo nằm ở chỗ toàn bộ phần lý thuyết đều được kiểm chứng bằng một hệ thống hiện thực đầy đủ. SplitBind không dừng ở mô hình: hệ thống đã được triển khai và vận hành thực tế, cấp phát PDF có chữ ký số, xác minh toàn vẹn tệp chính xác, và ghi nhận toàn bộ quá trình vào audit log (Chương 6). Phần thủy vân bền vững được phát triển qua ba thế hệ thuật toán và đo đạc trên corpus khoá theo mã băm, với kết quả được trình bày trung thực kể cả khi bất lợi (Chương 7).

## 9.2. Đóng góp chính

Đóng góp có giá trị nhất của nhóm không phải một con số độ bền, mà là một **chẩn đoán nguyên nhân gốc** (Chương 8).

Qua ba thế hệ, nhóm đã lần lượt kiểm chứng và **bác bỏ** cả ba hướng tinh chỉnh tham số của thiết kế: bước lượng tử hóa, số tile trên trang, và các tham số trải phổ. Mỗi lần bác bỏ dựa trên một loại bằng chứng khác nhau: một sweep 1408 hàng, một lần đọc mã nguồn, và một thí nghiệm 192 hàng. Kết quả âm tính đó dẫn tới câu hỏi đúng, và câu trả lời là: **độ bền của hệ thống không bị giới hạn bởi thủy vân, mà bởi tập giả thuyết hình học của bộ giải mã.**

Bằng chứng cho kết luận này là một tương quan không có ngoại lệ trên 286 hàng đo: mọi phép biến đổi mà bộ giải mã có sẵn giả thuyết đúng đều đạt 7–11 trên 12, mọi phép thiếu giả thuyết đúng đều đạt 0–2 trên 12. Chẩn đoán sau đó được xác nhận bằng một phép thử có tính tiên đoán: bóc viền letterbox của ảnh chụp màn hình đưa tỉ lệ truy vết từ **0/12 lên 9/12** ở độ phân giải 1920×1080, mà **không thay đổi bất kỳ tham số nào của thủy vân**.

Từ đó, nhóm phân tách được ba lớp thất bại vốn bị gộp chung dưới nhãn "thủy vân không đủ bền": không tạo được ứng viên hình học, tạo ứng viên sai, và ứng viên đúng nhưng sóng mang đã chết. Chỉ lớp thứ ba mới thực sự là vấn đề của thủy vân.

## 9.3. Giới hạn

`[Limitation]`

Nhóm nêu rõ các giới hạn sau, và không trình bày chúng như đã giải quyết:

- Phân hệ thủy vân bền vững **chưa đạt cổng phát hành** và được giữ ở tầng nghiên cứu. Phiên bản vận hành chỉ kích hoạt xác thực toàn vẹn tệp chính xác bằng SHA-256 và chữ ký Ed25519.
- Dưới tỉ lệ co giãn khoảng 0,45, payload không còn khôi phục được kể cả khi hình học chính xác. Đây là giới hạn phân giải thật của sóng mang.
- Định vị can thiệp đạt IoU tổng hợp khoảng 0,09 do cơ chế fail-safe kích hoạt trên phần lớn kịch bản có diện tích can thiệp lớn.
- Kết quả thủy vân bền vững mang phạm vi bằng chứng nghiên cứu, chưa phải bằng chứng phát hành.
- **Không kết quả nào trong báo cáo chứng minh danh tính người làm rò rỉ, chỉnh sửa hay phát tán tài liệu.** Thủy vân và chữ ký số cung cấp tín hiệu kỹ thuật phục vụ điều tra, không phải kết luận pháp lý về hành vi của một cá nhân.

## 9.4. Hướng phát triển

Thứ tự ưu tiên rút ra trực tiếp từ chẩn đoán ở Chương 8: chuẩn hoá khung ảnh trước khi giải mã (đã kiểm chứng hiệu quả); ước lượng tỉ lệ cắt thay vì liệt kê một giá trị cứng; cho phép hai trục co giãn độc lập để xử lý biến dạng phối cảnh; và cuối cùng mới là chọn sóng mang theo nội dung. Xa hơn, hướng bước lượng tử thích nghi theo mô hình thị giác người và các kiến trúc học sâu như HiDDeN hoặc StegaStamp là lối đi cho lớp thất bại thứ ba, lớp duy nhất mà cường độ sóng mang thực sự là nút thắt.

\\newpage

"""


def extract(text: str, part: int) -> str:
    """Return the body of one PHẦN, without its own heading line."""
    pattern = rf"^# PHẦN {part}:.*$"
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise SystemExit(f"PHẦN {part} not found")
    start = match.end()
    nxt = re.search(r"^# PHẦN \d+:", text[start:], re.MULTILINE)
    body = text[start: start + nxt.start()] if nxt else text[start:]
    return body.strip("\n").rstrip("-\n ").strip()


def renumber(body: str, old: int, new: int) -> str:
    """Rewrite `## old.x` / `### old.x.y` section numbers onto the new chapter."""
    body = re.sub(rf"^(#{{2,4}} ){old}\.", rf"\g<1>{new}.", body, flags=re.MULTILINE)
    body = re.sub(rf"\bMục {old}\.(\d)", rf"Mục {new}.\1", body)
    return body


def main() -> int:
    text = io.open(SOURCE, encoding="utf-8").read()
    parts = [TITLE_PAGE]
    for source_part, chapter, title in CHAPTERS:
        body = renumber(extract(text, source_part), source_part, chapter)
        parts.append(f"# CHƯƠNG {chapter}. {title}\n\n{body}\n\n\\newpage\n")
    parts.append(CONCLUSION)
    parts.append("# TÀI LIỆU THAM KHẢO\n\n" + extract(text, 11) + "\n\n\\newpage\n")
    parts.append("# PHỤ LỤC A. MA TRẬN TRUY VẾT KHẲNG ĐỊNH VÀ BẰNG CHỨNG\n\n" + extract(text, 12) + "\n")

    OUT_MD.write_text("\n".join(parts), encoding="utf-8")
    size = OUT_MD.stat().st_size
    print(f"wrote {OUT_MD.name} ({size / 1024:.1f} KB)")

    command = [
        "pandoc", str(OUT_MD), "-o", str(OUT_DOCX),
        "--toc", "--toc-depth=3", "--standalone", "-f", "markdown+tex_math_dollars",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print("pandoc failed:", result.stderr[:800], file=sys.stderr)
        return result.returncode
    print(f"wrote {OUT_DOCX.name} ({OUT_DOCX.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
