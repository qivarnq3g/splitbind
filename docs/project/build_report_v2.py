from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "capstone-knowledge-base.md"
REFERENCE = HERE / "reference-report.docx"
OUT_MD = HERE / "Nhom9_TruyVetToanVenVanBan.md"
OUT_DOCX = HERE / "Nhom9_TruyVetToanVenVanBan.docx"
ASSETS = "report-assets"

CHAPTERS = [
    ("CƠ SỞ LÝ THUYẾT KỸ THUẬT DIGITAL WATERMARKING", [(2, None)]),
    ("ỨNG DỤNG THỦY VÂN TRONG TRUY VẾT VÀ TOÀN VẸN HÌNH ẢNH", [(3, None)]),
    ("ỨNG DỤNG CHỮ KÝ SỐ VÀ SO SÁNH CÁC KỸ THUẬT TOÀN VẸN",
     [(4, "Ứng dụng chữ ký số trong bảo vệ thông tin truy vết"),
      (5, "So sánh với các kỹ thuật xác minh bảo vệ tính toàn vẹn khác")]),
    ("HỆ THỐNG SPLITBIND: HIỆN THỰC, THỰC NGHIỆM VÀ ĐỀ XUẤT",
     [(6, "Kiến trúc và hiện thực hệ thống"),
      (7, "Kết quả thực nghiệm"),
      (13, "Đề xuất kiến trúc V4: chẩn đoán nguyên nhân gốc")]),
]

FIGURES = [
    ("ui-cap-phat.png", "Giao diện cấp phát tài liệu trên hệ thống đang vận hành"),
    ("ui-xac-minh-khop.png",
     "Kết quả xác minh khi tệp khớp bản cấp phát: mã SHA-256 trùng khớp và chữ ký hồ sơ hợp lệ"),
    ("ui-xac-minh-khong-khop.png",
     "Kết quả xác minh khi tệp đã bị chỉnh sửa: hệ thống báo không khớp và không quy kết hành vi cho bất kỳ ai"),
    ("bieu-do-v1-v3.png",
     "Tỉ lệ giải mã của thế hệ V1 và V3 trên cùng hợp đồng corpus, cùng định nghĩa cổng"),
    ("bieu-do-phong-bi-tan-cong.png",
     "Tỉ lệ truy vết của 13 phép biến đổi, phân theo ba lớp nguyên nhân thất bại"),
    ("bieu-do-boc-vien.png",
     "Hiệu quả của bước bóc viền letterbox trước khi giải mã, đo trên 12 trang dương tính"),
]

TABLE_CAPTIONS = [
    ("Hàm băm mật mã (Cryptographic Hash)",
     "Ma trận so sánh sáu kỹ thuật bảo vệ toàn vẹn trên bảy tiêu chí an ninh"),
    ("Số liệu thực nghiệm | Giá trị khóa",
     "Các số liệu thực nghiệm đã khóa của thế hệ V1"),
    ("Chỉ số | V1 tốt nhất | V3 tốt nhất",
     "Đối chiếu thế hệ V1 và V3 trên cùng một corpus"),
    ("Tấn công | Số trang trượt",
     "Phân rã số trang trượt theo từng phép tấn công so với phép đo không tấn công"),
    ("Chỉ số | n | Trung bình",
     "Thời gian xử lý, bộ nhớ đỉnh và dung lượng tệp tạm đo trên 352 hàng"),
    ("Chỉ số | Nhỏ nhất | Trung bình",
     "Chất lượng ảnh sau khi nhúng, đo trên 192 hàng có PSNR hữu hạn"),
    ("Hệ thống | Nén JPEG mạnh",
     "Tỉ lệ khôi phục chính xác toàn bộ payload, đối chiếu SplitBind với ba hệ thống mã nguồn mở"),
    ("Phép tấn công | Giải ở kích thước bị tấn công",
     "Tác động của bước chuẩn hóa khung ảnh, đo trên trang tài liệu của SplitBind"),
    ("`d1` | PSNR (dB)",
     "Quét cường độ nhúng đối chiếu độ bền với độ trung thực, trên trang tài liệu của SplitBind"),
    ("Hình học trang | Phép tấn công",
     "Năm phép thử thủy vân trên môi trường production"),
    ("Vật mang | không tấn công",
     "Ảnh hưởng của loại vật mang tới khả năng giải mã, ba vật mang trên năm điều kiện"),
    ("Phép biến đổi | Kích thước ra",
     "Đối chiếu khả năng sinh giả thuyết hình học với tỉ lệ truy vết đo được"),
    ("Lớp | Dấu hiệu | Ví dụ",
     "Ba lớp nguyên nhân thất bại và biện pháp tương ứng"),
]

ABBREVIATIONS = [
    ("BER", "Bit Error Rate, tỉ lệ lỗi bit"),
    ("BTL", "Bài tập lớn"),
    ("CRC", "Cyclic Redundancy Check, mã kiểm dư vòng"),
    ("DCT", "Discrete Cosine Transform, biến đổi cosin rời rạc"),
    ("DWT", "Discrete Wavelet Transform, biến đổi sóng con rời rạc"),
    ("ECC", "Error-Correcting Code, mã sửa lỗi"),
    ("BCH", "Bose-Chaudhuri-Hocquenghem, một họ mã sửa lỗi khối"),
    ("JPEG", "Joint Photographic Experts Group, chuẩn nén ảnh có tổn hao; JPEG-70 nghĩa là nén ở mức chất lượng 70"),
    ("MAC", "Message Authentication Code, mã xác thực thông điệp dùng khóa bí mật chung"),
    ("HMAC", "Hash-based Message Authentication Code"),
    ("IoU", "Intersection over Union, tỉ số giao trên hợp"),
    ("JCS", "JSON Canonicalization Scheme (RFC 8785)"),
    ("ORB", "Oriented FAST and Rotated BRIEF"),
    ("PSNR", "Peak Signal-to-Noise Ratio, tỉ số tín hiệu trên nhiễu đỉnh"),
    ("QIM", "Quantization Index Modulation, điều chế chỉ số lượng tử"),
    ("RANSAC", "Random Sample Consensus"),
    ("RBAC", "Role-Based Access Control, kiểm soát truy cập theo vai trò"),
    ("RSS", "Resident Set Size, dung lượng bộ nhớ thường trú"),
    ("SSIM", "Structural Similarity Index Measure"),
    ("SSOT", "Single Source of Truth, nguồn chân lý duy nhất"),
    ("WM", "Watermark, thủy vân số"),
]

TERMS = [
    ("canvas", "Khung ảnh chuẩn tắc mà mọi trang tài liệu được đưa về trước khi nhúng"),
    ("corpus", "Bộ trang tài liệu mẫu cố định dùng cho mọi phép đo, để các lần chạy so sánh được với nhau"),
    ("fixture", "Một trang tài liệu cụ thể trong corpus, đóng vai trò mẫu thử"),
    ("letterbox", "Dải viền trơn mà ảnh chụp màn hình thêm vào hai bên khung ảnh khi tỉ lệ không khớp"),
    ("manifest", "Hồ sơ toàn vẹn: tệp mô tả một lần cấp phát, được ký số để chống sửa đổi"),
    ("payload", "Chuỗi bit mang thông tin định danh được nhúng vào ảnh"),
    ("pre-gate", "Vòng sàng lọc chạy trước cổng phát hành, dùng để loại sớm các bộ tham số kém"),
    ("tile", "Ô ảnh: vùng hình chữ nhật mà thuật toán chia trang ra để nhúng payload"),
    ("harness", "Bộ khung thực nghiệm: mã và cấu hình dùng để chạy hàng loạt phép đo lặp lại được, tách biệt với mã sản phẩm."),
    ("profile", "Hồ sơ tham số đã khoá của một thế hệ thuật toán: kích thước ô, số lần lặp bit, bước lượng tử và các hằng số kèm theo."),
    ("Reed-Solomon", "Mã sửa lỗi khối trên trường hữu hạn, cho phép khôi phục dữ liệu khi một số ký hiệu bị sai hoặc bị khai là mất."),
    ("artifact", "Tệp kết quả do một lần chạy thực nghiệm sinh ra và được lưu lại để kiểm chứng về sau."),
    ("benchmark", "Bộ phép đo chuẩn hoá chạy trên cùng một corpus, để các lần chạy khác nhau so sánh được với nhau."),
    ("production", "Môi trường máy chủ đang phục vụ người dùng thật, phân biệt với môi trường thử nghiệm. Giữ nguyên tiếng Anh theo cách gọi phổ biến trong ngành phần mềm."),
]

PAGEBREAK = (
    "\n```{=openxml}\n"
    '<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n'
    "```\n"
)

TOC_FIELD = (
    "\n```{=openxml}\n"
    '<w:sdt><w:sdtPr><w:docPartObj><w:docPartGallery w:val="Table of Contents"/>'
    "<w:docPartUnique/></w:docPartObj></w:sdtPr><w:sdtContent>"
    '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
    '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    "<w:r><w:t>Nhấn chuột phải vào đây và chọn Update Field để sinh mục lục.</w:t></w:r>"
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    "</w:sdtContent></w:sdt>\n"
    "```\n"
)

def extract(text: str, part: int) -> str:
    match = re.search(rf"^# PHẦN {part}:.*$", text, re.MULTILINE)
    if match is None:
        raise SystemExit(f"PHẦN {part} không tìm thấy")
    start = match.end()
    nxt = re.search(r"^# PHẦN \d+:", text[start:], re.MULTILINE)
    body = text[start: start + nxt.start()] if nxt else text[start:]
    body = body.strip("\n").rstrip("- \n")
    body = drop_epistemic_labels(body)
    if part != 11:
        body = translate_labels(body)
        body = ampersand_to_word(body)
    return body

LABEL_ONLY = re.compile(r"^\s*(?:`\[[^\]]+\]`\s*(?:&|và)?\s*)+$")


def drop_epistemic_labels(body: str) -> str:
    kept = [line for line in body.splitlines() if not LABEL_ONLY.match(line)]
    return "\n".join(kept)


LABEL_WORDS = {
    "Implemented": "Đã hiện thực trong mã nguồn",
    "Established theory": "Lý thuyết đã công bố",
    "Experimentally observed": "Số liệu đo thực nghiệm",
    "Production": "Đang vận hành trên hệ thống thật",
    "Limitation": "Giới hạn đã nhận diện",
    "Design": "Thiết kế đề xuất",
    "Proposed": "Thiết kế đề xuất",
}

LABEL_PATTERN = re.compile(
    r"`?\[(" + "|".join(re.escape(name) for name in LABEL_WORDS) + r")\]`?"
)


def translate_labels(body: str) -> str:
    return LABEL_PATTERN.sub(lambda m: f"*{LABEL_WORDS[m.group(1)]}*", body)


def ampersand_to_word(body: str) -> str:
    diacritic = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩị"
                           r"òóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.I)

    def fix(line: str) -> str:
        pieces = re.split(r"(`[^`]*`|\([^)]*\)|\$[^$]*\$)", line)
        for index, piece in enumerate(pieces):
            if index % 2 == 0 or (piece.startswith("(") and diacritic.search(piece)):
                pieces[index] = re.sub(r"(?<=\s)&(?=\s)", "và", piece)
        return "".join(pieces)

    return "\n".join(fix(line) for line in body.splitlines())


def strip_numbers(body: str, demote: bool) -> str:
    def fix(match: "re.Match[str]") -> str:
        hashes, rest = match.group(1), match.group(2)
        rest = re.sub(r"^\d+(\.\d+)*\.?\s*", "", rest)
        rest = re.sub(r"^[A-Z]\.\s+", "", rest)
        if demote:
            hashes += "#"
        return f"{hashes} {rest}"

    return re.sub(r"^(#{2,5}) +(.*)$", fix, body, flags=re.MULTILINE)

def number_sections(body: str, chapter_no: int) -> str:
    depths = [len(h) for h in re.findall(r"^(#{2,6}) +\S", body, re.MULTILINE)]
    if depths:
        shift = min(depths) - 2
        if shift > 0:
            body = re.sub(
                r"^(#{2,6})( +\S)",
                lambda m: m.group(1)[shift:] + m.group(2),
                body, flags=re.MULTILINE,
            )

    counters = [0, 0, 0]

    def fix(match: "re.Match[str]") -> str:
        level = len(match.group(1)) - 2
        if level > 2:
            return match.group(0)
        counters[level] += 1
        for deeper in range(level + 1, 3):
            counters[deeper] = 0
        number = ".".join(
            str(n) for n in [chapter_no] + counters[: level + 1]
        )
        return f"{match.group(1)} {number}. {match.group(2)}"

    return re.sub(r"^(#{2,4}) +(.*)$", fix, body, flags=re.MULTILINE)

def caption_tables(body: str, counters: dict) -> str:
    for fragment, caption in TABLE_CAPTIONS:
        idx = body.find(fragment)
        if idx == -1:
            continue
        line_start = body.rfind("\n", 0, idx) + 1
        counters["table"] += 1
        label = f"**Bảng {counters['chapter']}.{counters['table']}:** {caption}\n\n"
        body = body[:line_start] + label + body[line_start:]
    return body

def build() -> str:
    text = io.open(SOURCE, encoding="utf-8").read()
    figure_index = 0
    table_list: list[str] = []
    figure_list: list[str] = []
    out: list[str] = [COVER]

    out.append("# MỤC LỤC\n" + TOC_FIELD + PAGEBREAK)

    merged = sorted(ABBREVIATIONS + TERMS, key=lambda pair: pair[0].lower())
    abbr = "\n".join(f"| **{k}** | {v} |" for k, v in merged)
    out.append(
        "# DANH MỤC TỪ VIẾT TẮT VÀ THUẬT NGỮ\n\n"
        "| Từ viết tắt / thuật ngữ | Nghĩa đầy đủ |\n|---|---|\n"
        + abbr + "\n" + PAGEBREAK
    )
    out.append("<<<BANG>>>")
    out.append("<<<HINH>>>")

    intro = strip_numbers(extract(text, 1), demote=False)
    out.append("# LỜI MỞ ĐẦU\n\n" + LOI_MO_DAU + "\n\n" + intro + "\n" + PAGEBREAK)

    for chapter_no, (title, sources) in enumerate(CHAPTERS, start=1):
        counters = {"chapter": chapter_no, "table": 0}
        pieces = [f"# CHƯƠNG {chapter_no}. {title}\n"]
        merged = len(sources) > 1
        for part_no, section_title in sources:
            body = caption_tables(
                strip_numbers(extract(text, part_no), demote=merged), counters
            )
            if merged and section_title:
                pieces.append(f"\n## {section_title}\n\n{body}\n")
            else:
                pieces.append("\n" + body + "\n")
        chapter_md = number_sections("".join(pieces), chapter_no)

        for match in re.finditer(r"\*\*Bảng (\d+\.\d+):\*\* (.+)", chapter_md):
            table_list.append(f"| Bảng {match.group(1)} | {match.group(2)} |")

        if chapter_no == len(CHAPTERS):
            gallery = []
            for filename, caption in FIGURES:
                figure_index += 1
                number = f"{chapter_no}.{figure_index}"
                gallery.append(
                    f"\n![]({ASSETS}/{filename})\n\n**Hình {number}:** {caption}\n"
                )
                figure_list.append(f"| Hình {number} | {caption} |")
            chapter_md += (
                "\n## Hình ảnh minh hoạ hệ thống và biểu đồ kết quả\n\n"
                "Các hình dưới đây được chụp từ hệ thống đang vận hành và dựng từ "
                "dữ liệu đo đã trình bày ở các mục trên.\n" + "".join(gallery)
            )
        out.append(chapter_md + PAGEBREAK)

    out.append(KET_LUAN + PAGEBREAK)
    out.append("# TÀI LIỆU THAM KHẢO\n\n" + extract(text, 11) + "\n" + PAGEBREAK)
    out.append(
        "# PHỤ LỤC A. MA TRẬN TRUY VẾT KHẲNG ĐỊNH VÀ BẰNG CHỨNG\n\n"
        + strip_numbers(extract(text, 12), demote=False) + "\n"
    )

    document = "\n".join(out)
    document = document.replace(
        "<<<BANG>>>",
        "# DANH MỤC CÁC BẢNG\n\n| Số hiệu | Tên bảng |\n|---|---|\n"
        + "\n".join(table_list) + "\n" + PAGEBREAK,
    )
    document = document.replace(
        "<<<HINH>>>",
        "# DANH MỤC CÁC HÌNH\n\n| Số hiệu | Tên hình |\n|---|---|\n"
        + "\n".join(figure_list) + "\n" + PAGEBREAK,
    )
    print(f"  {len(table_list)} bảng, {len(figure_list)} hình")
    return document

def main() -> int:
    document = build()
    OUT_MD.write_text(document, encoding="utf-8")
    print(f"wrote {OUT_MD.name} ({OUT_MD.stat().st_size / 1024:.1f} KB)")

    command = [
        "pandoc", str(OUT_MD), "-o", str(OUT_DOCX),
        "--reference-doc", str(REFERENCE),
        "--standalone",
        "-f", "markdown+tex_math_dollars+raw_attribute",
        "--resource-path", str(HERE),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print("pandoc failed:\n" + result.stderr[:1200], file=sys.stderr)
        return result.returncode
    if result.stderr.strip():
        print("pandoc warnings:\n" + result.stderr[:500])
    print(f"wrote {OUT_DOCX.name} ({OUT_DOCX.stat().st_size / 1024:.1f} KB)")
    return 0

COVER = """---
lang: vi
---
"""

LOI_MO_DAU = """Tài liệu điện tử ngày nay rò rỉ chủ yếu qua các kênh làm mất tính toàn vẹn bit: chụp ảnh màn hình, in ra rồi quét lại, hoặc chụp lại bằng điện thoại. Chữ ký số bảo vệ rất tốt biểu diễn số nguyên bản, nhưng chỉ cần một byte thay đổi là phép xác minh thất bại, và nó không cung cấp cơ chế nào để đối chiếu một bản sao đã qua biến đổi tín hiệu với hồ sơ phát hành gốc. Khoảng trống đó là lý do nhóm chọn đề tài này.

Báo cáo bám sát bốn nội dung được giao. Chương 1 trình bày lý thuyết kỹ thuật Digital Watermarking. Chương 2 trình bày ứng dụng thủy vân trong truy vết thay đổi hình ảnh. Chương 3 gồm hai phần: ứng dụng ký số trong bảo vệ thông tin truy vết, và so sánh với các kỹ thuật xác minh toàn vẹn khác. Chương 4 trình bày hệ thống SplitBind mà nhóm đã hiện thực, đo đạc và đề xuất cải tiến.

Nhóm chủ trương công bố giới hạn thay vì che giấu. Mọi khẳng định kỹ thuật trong báo cáo đều được gắn một trong năm nhãn phân định cấp độ tri thức, in nghiêng ngay trước nội dung: *lý thuyết đã công bố* cho lý thuyết kinh điển, *đã hiện thực trong mã nguồn* cho tính năng đã có mã nguồn, *số liệu đo thực nghiệm* cho kết quả đo có artifact và mã băm xác thực, *đang vận hành trên hệ thống thật* cho tính năng đang chạy thực tế, và *giới hạn đã nhận diện* cho ranh giới thất bại đã xác định. Các kết quả âm tính và các giả thuyết đã bị bác bỏ đều được trình bày đầy đủ, vì chúng là một phần của đóng góp khoa học chứ không phải điều cần giấu."""

KET_LUAN = """# KẾT LUẬN

Báo cáo đã hoàn thành bốn nội dung được giao. Về lý thuyết, nhóm trình bày cơ sở kỹ thuật Digital Watermarking, phân loại theo miền nhúng và theo mục tiêu an ninh, cùng bài toán đánh đổi giữa độ bền, tính vô hình và dung lượng nhúng. Về ứng dụng, nhóm phân tích vai trò của thủy vân bền vững trong truy vết nguồn phát hành, của thủy vân bán dễ vỡ trong định vị can thiệp, và của chữ ký số Ed25519 trên manifest chuẩn tắc RFC 8785 trong bảo vệ thông tin truy vết. Về so sánh, nhóm đặt sáu kỹ thuật toàn vẹn cạnh nhau trên bảy tiêu chí an ninh.

Điểm khác biệt của báo cáo là toàn bộ phần lý thuyết đều được kiểm chứng bằng một hệ thống hiện thực đầy đủ và đang vận hành, chứ không dừng ở mô hình.

Đóng góp chính của nhóm không phải một con số độ bền, mà là một chẩn đoán nguyên nhân gốc. Qua ba thế hệ thuật toán, nhóm đã lần lượt kiểm chứng và bác bỏ cả ba hướng tinh chỉnh tham số, mỗi lần bằng một loại bằng chứng khác nhau: một sweep 1408 hàng, một lần đọc mã nguồn, và một thí nghiệm 192 hàng. Kết quả âm tính đó dẫn tới câu hỏi đúng, và câu trả lời là: độ bền của hệ thống không bị giới hạn bởi thủy vân, mà bởi tập giả thuyết hình học của bộ giải mã. Bằng chứng là một tương quan không có ngoại lệ trên 286 hàng đo, sau đó được xác nhận bằng một phép thử có tính tiên đoán: bóc viền letterbox đưa tỉ lệ truy vết của ảnh chụp màn hình 1920×1080 từ 0 trên 12 lên 9 trên 12, mà không thay đổi bất kỳ tham số nào của thủy vân. Ở 1366×768 phép bóc viền không khôi phục được hàng nào, và chính sự khác biệt giữa hai độ phân giải là thứ tách bạch được hai lớp thất bại.

Từ đó nhóm phân tách được ba lớp thất bại vốn bị gộp chung dưới nhãn thủy vân không đủ bền: không tạo được ứng viên hình học, tạo ứng viên sai, và ứng viên đúng nhưng vật mang đã chết. Chỉ lớp thứ ba mới thực sự là vấn đề của thủy vân.

Điều tra tiếp trong hai ngày cuối tìm ra một nguyên nhân gốc thứ ba, và nó buộc nhóm rút lại một phần chẩn đoán của chính mình. Lớp thất bại thứ ba hoá ra không phải vật mang chết: bộ giải mã đo độ tin cậy ở mức bit nhưng khai ký hiệu bị xoá ở mức byte, nên một bit yếu làm cả tám bit cùng byte bị khai xoá, và số ký hiệu xoá vượt quá mức mã Reed-Solomon sửa được. Hệ thống từ chối đúng những từ mã mà nó đã khôi phục ở tỉ lệ lỗi bit bằng 0,000. Một vật mang thay thế được cài đặt để kiểm chứng giả thuyết vật mang đã đo kém hơn ở mọi tỉ lệ và bị loại bỏ. Sửa kế toán ký hiệu xoá khôi phục được nén JPEG q50, thu nhỏ tới 0.375 và cả ca ảnh chụp màn hình có viền, mà không đụng tới khâu nhúng và không phải cấp phát lại tài liệu cũ. Chi tiết và bảng số liệu ở Mục 7.5.

Nhóm cũng ghi nhận một lớp thất bại nằm ngoài thuật toán: dịch vụ đòi hai kết quả giải mã khớp nhau mới công bố danh tính, trong khi số trang là thành phần của phép dẫn xuất có khoá nên một tấm ảnh chỉ sinh được đúng một kết quả. Đường truy vết ảnh vì thế không thể kết luận dù thuật toán hoạt động đúng. Điều này định vị lại mọi bảng độ bền trong báo cáo: chúng được đo bằng cách gọi thẳng bộ giải mã và truyền sẵn số trang, tức mô tả thư viện chứ chưa mô tả sản phẩm.

Về các giới hạn đã nhận diện, phân hệ thủy vân đã được bật trên hệ thống vận hành và mọi kết quả truy vết vẫn mang nhãn độ thu hồi chưa đạt cổng phát hành do chính hệ thống gắn. Ranh giới còn lại là tổn thất chồng nhau chứ không phải một phép biến đổi đơn lẻ: ảnh chụp màn hình cộng nén JPEG q60 thất bại trong khi từng phép một đều sống. Cắt ảnh quá nửa và xoay vẫn chưa giải được ở đây lẫn ở mọi công trình mã nguồn mở đã đối chiếu. Định vị can thiệp đạt IoU tổng hợp khoảng 0.09 do cơ chế fail-safe kích hoạt trên phần lớn kịch bản có diện tích can thiệp lớn. Và quan trọng nhất: không kết quả nào trong báo cáo chứng minh danh tính người làm rò rỉ, chỉnh sửa hay phát tán tài liệu; thủy vân và chữ ký số cung cấp tín hiệu kỹ thuật phục vụ điều tra, không phải kết luận pháp lý về hành vi của một cá nhân.

Hướng phát triển rút ra trực tiếp từ chẩn đoán: chuẩn hoá khung ảnh trước khi giải mã, ước lượng tỉ lệ cắt thay vì liệt kê một giá trị cứng, cho phép hai trục co giãn độc lập, và cuối cùng mới là chọn vật mang theo nội dung. Xa hơn, bước lượng tử thích nghi theo mô hình thị giác người và các kiến trúc học sâu là lối đi cho lớp thất bại thứ ba."""

if __name__ == "__main__":
    raise SystemExit(main())
