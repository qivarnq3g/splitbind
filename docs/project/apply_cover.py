from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_TEMPLATE_ENV = os.environ.get("SPLITBIND_COVER_TEMPLATE")
TEMPLATE = Path(_TEMPLATE_ENV) if _TEMPLATE_ENV else HERE / "cover-template.docx"
REPORT = HERE / "Nhom9_TruyVetToanVenVanBan.docx"

LOGO_REL_ID = "rIdCoverLogo"
LOGO_TARGET = "media/cover-logo.png"

REPLACEMENTS = [
    ("&lt;Tên đề tài&gt;", "TÌM HIỂU VÀ ĐỀ XUẤT HỆ THỐNG TRUY VẾT TOÀN VẸN VĂN BẢN"),
    ("Môn: tên môn", "Môn: An toàn thông tin"),
    ("Mã lớp học phần: mã lớp học phần", "Mã lớp học phần: 012012303303"),
    ("&lt;Tên sv 1&gt;", "Hoàng Việt Quang"),
    ("&lt;MSSV 1&gt;", "066206005044"),
    ("&lt;Tên sv 2&gt;", "Ngô Văn Gia Phúc"),
    ("&lt;MSSV 2&gt;", "070206006641"),
    ("tháng &lt;thang&gt; năm 2025", "tháng 9 năm 2026"),
]


def cover_body(xml: str) -> str:
    body = re.search(r"<w:body>(.*)</w:body>", xml, re.S).group(1)
    cut = body.find('w:type="page"')
    if cut == -1:
        raise SystemExit("template has no page break")
    para_start = max(body.rfind("<w:p ", 0, cut), body.rfind("<w:p>", 0, cut))
    para_end = body.find("</w:p>", cut) + len("</w:p>")
    paragraph = body[para_start:para_end]
    stripped = re.sub(r"<w:r\b[^>]*>(?:(?!</w:r>).)*?<w:br w:type=\"page\"/>"
                      r"(?:(?!</w:r>).)*?</w:r>", "", paragraph, flags=re.S)
    stripped = stripped.replace('<w:br w:type="page"/>', "")
    has_text = re.search(r"<w:t(?:\s[^>]*)?>[^<]", stripped)
    return body[:para_start] + (stripped if has_text else "")


def merge_namespaces(document: str, template_doc: str) -> str:
    open_tag = re.search(r"<w:document\b[^>]*>", document)
    donor_tag = re.search(r"<w:document\b[^>]*>", template_doc)
    if open_tag is None or donor_tag is None:
        raise SystemExit("không tìm thấy thẻ w:document")

    have = set(re.findall(r'xmlns:(\w+)=', open_tag.group(0)))
    additions = [
        f'xmlns:{prefix}="{uri}"'
        for prefix, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', donor_tag.group(0))
        if prefix not in have
    ]

    tag = open_tag.group(0)
    if additions:
        tag = tag[:-1].rstrip() + " " + " ".join(additions) + ">"

    donor_ignorable = re.search(r'mc:Ignorable="([^"]*)"', donor_tag.group(0))
    if donor_ignorable:
        existing = re.search(r'mc:Ignorable="([^"]*)"', tag)
        merged = sorted(set(donor_ignorable.group(1).split())
                        | set(existing.group(1).split() if existing else []))
        joined = " ".join(merged)
        if existing:
            tag = tag.replace(existing.group(0), f'mc:Ignorable="{joined}"')
        else:
            tag = tag[:-1].rstrip() + f' mc:Ignorable="{joined}">'

    return document.replace(open_tag.group(0), tag, 1)


def single_spaced(xml: str) -> str:
    spacing = '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'

    def fix(match: "re.Match[str]") -> str:
        block = match.group(0)
        if "<w:pPr>" in block:
            without = re.sub(r"<w:spacing[^/]*/>", "", block, count=1)
            return without.replace("<w:pPr>", "<w:pPr>" + spacing, 1)
        return block.replace("<w:p>", "<w:p><w:pPr>" + spacing + "</w:pPr>", 1)

    return re.sub(r"<w:p(?:\s[^>]*)?>(?:(?!</w:p>).)*?</w:p>", fix, xml, flags=re.S)


SIDE = '<w:{0} w:val="single" w:sz="6" w:space="0" w:color="auto"/>'
TABLE_SIDES = ("top", "left", "bottom", "right", "insideH", "insideV")
CELL_SIDES = ("top", "left", "bottom", "right")
PAGE_WIDTH = 11906
PAGE_SIZE = '<w:pgSz w:w="11906" w:h="16838"/>'
CELL_SPACING = '<w:spacing w:before="60" w:after="60" w:line="240" w:lineRule="auto"/>'


def clean_cell_paragraph(paragraph: str) -> str:
    paragraph = re.sub(r"<w:numPr>.*?</w:numPr>", "", paragraph, flags=re.S)
    paragraph = re.sub(r"<w:ind[^/]*/>", "", paragraph)
    paragraph = re.sub(r"<w:spacing[^/]*/>", "", paragraph)
    paragraph = re.sub(r"<w:jc[^/]*/>", "", paragraph)
    paragraph = re.sub(r'<w:pStyle w:val="[^"]*"\s*/>', "", paragraph)
    props = CELL_SPACING + '<w:jc w:val="center"/>'
    existing = re.search(r"<w:pPr>(.*?)</w:pPr>", paragraph, re.S)
    if existing:
        return paragraph.replace(
            existing.group(0), "<w:pPr>" + props + existing.group(1) + "</w:pPr>", 1
        )
    opening = re.match(r"<w:p(?:\s[^>]*)?>", paragraph)
    return paragraph.replace(
        opening.group(0), opening.group(0) + "<w:pPr>" + props + "</w:pPr>", 1
    )


def number_cell(cell: str, ordinal: int) -> str:
    text = re.search(r"<w:t(?:\s[^>]*)?>", cell)
    if text is None:
        return cell
    cut = text.end()
    if re.match(r"\s*\d+\s*[.)]\s", cell[cut:]):
        return cell
    return cell[:cut] + f"{ordinal}. " + cell[cut:]


def rebuild_cover_table(xml: str, available: int) -> str:
    found = re.search(r"<w:tbl>.*?</w:tbl>", xml, re.S)
    if found is None:
        raise SystemExit("không thấy bảng sinh viên trong trang bìa")

    rows = re.findall(r"<w:tr[ >].*?</w:tr>", found.group(0), re.S)
    columns = len(re.findall(r"<w:tc>", rows[0]))
    base = available // columns
    widths = [base] * columns
    widths[-1] = available - base * (columns - 1)

    table_borders = "<w:tblBorders>" + "".join(
        SIDE.format(side) for side in TABLE_SIDES
    ) + "</w:tblBorders>"
    cell_borders = "<w:tcBorders>" + "".join(
        SIDE.format(side) for side in CELL_SIDES
    ) + "</w:tcBorders>"

    properties = (
        "<w:tblPr>"
        '<w:tblStyle w:val="Table"/>'
        f'<w:tblW w:w="{available}" w:type="dxa"/>'
        '<w:tblInd w:w="0" w:type="dxa"/>'
        + table_borders
        + '<w:tblLayout w:type="fixed"/>'
        '<w:tblCellMar>'
        '<w:top w:w="57" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
        '<w:bottom w:w="57" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>'
        '</w:tblCellMar>'
        '<w:tblLook w:val="0000" w:firstRow="0" w:lastRow="0" w:firstColumn="0"'
        ' w:lastColumn="0" w:noHBand="1" w:noVBand="1"/>'
        "</w:tblPr>"
    )
    grid = "<w:tblGrid>" + "".join(
        f'<w:gridCol w:w="{width}"/>' for width in widths
    ) + "</w:tblGrid>"

    rebuilt = []
    for row_index, row in enumerate(rows):
        cells = re.findall(r"<w:tc>.*?</w:tc>", row, re.S)
        pieces = []
        for column, cell in enumerate(cells[:columns]):
            if row_index and not column:
                cell = number_cell(cell, row_index)
            paragraphs = "".join(
                clean_cell_paragraph(one)
                for one in re.findall(r"<w:p(?:\s[^>]*)?>.*?</w:p>", cell, re.S)
            )
            if not paragraphs:
                paragraphs = "<w:p><w:pPr>" + CELL_SPACING + "</w:pPr></w:p>"
            pieces.append(
                "<w:tc><w:tcPr>"
                f'<w:tcW w:w="{widths[column]}" w:type="dxa"/>'
                + cell_borders
                + '<w:vAlign w:val="center"/>'
                "</w:tcPr>" + paragraphs + "</w:tc>"
            )
        rebuilt.append("<w:tr>" + "".join(pieces) + "</w:tr>")

    return xml.replace(
        found.group(0), "<w:tbl>" + properties + grid + "".join(rebuilt) + "</w:tbl>", 1
    )


LONG_TOKEN = 24


def insert_paragraph_props(block: str, props: str) -> str:
    existing = re.search(r"<w:pPr>(.*?)</w:pPr>", block, re.S)
    if existing:
        inner = existing.group(1)
        style = re.match(r"\s*<w:pStyle[^>]*/>", inner)
        if style:
            merged = style.group(0) + props + inner[style.end():]
        else:
            merged = props + inner
        return block.replace(existing.group(0), "<w:pPr>" + merged + "</w:pPr>", 1)
    opening = re.match(r"<w:p(?:\s[^>]*)?>", block)
    return block.replace(
        opening.group(0), opening.group(0) + "<w:pPr>" + props + "</w:pPr>", 1
    )


def unjustify_code_paragraphs(xml: str) -> str:
    align = '<w:jc w:val="left"/>'

    def fix(match: "re.Match[str]") -> str:
        block = match.group(0)
        if 'w:val="VerbatimChar"' not in block:
            return block
        runs = re.findall(r'<w:rStyle w:val="VerbatimChar"\s*/>.*?</w:r>', block, re.S)
        text = "".join(
            "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", run)) for run in runs
        )
        if not any(len(token) >= LONG_TOKEN for token in text.split()):
            return block
        stripped = re.sub(r"<w:jc[^/]*/>", "", block)
        return insert_paragraph_props(stripped, align)

    return re.sub(r"<w:p(?:\s[^>]*)?>.*?</w:p>", fix, xml, flags=re.S)


def compact_table_cells(xml: str) -> str:
    spacing = '<w:spacing w:before="40" w:after="40" w:line="240" w:lineRule="auto"/>'
    align = '<w:jc w:val="left"/>'

    def fix_cell(match: "re.Match[str]") -> str:
        cell = match.group(0)

        def fix_paragraph(inner: "re.Match[str]") -> str:
            block = inner.group(0)
            block = re.sub(r"<w:spacing[^/]*/>", "", block)
            block = re.sub(r"<w:jc[^/]*/>", "", block)
            return insert_paragraph_props(block, spacing + align)

        return re.sub(r"<w:p(?:\s[^>]*)?>.*?</w:p>", fix_paragraph, cell, flags=re.S)

    return re.sub(r"<w:tc>.*?</w:tc>", fix_cell, xml, flags=re.S)


BREAK_ONLY = re.compile(
    r'<w:p(?:\s[^>]*)?>(?:(?!</w:p>).)*?<w:br w:type="page"\s*/>(?:(?!</w:p>).)*?</w:p>',
    re.S,
)


def fold_page_breaks(xml: str) -> str:
    def carries_text(block: str) -> bool:
        return bool(re.search(r"<w:t(?:\s[^>]*)?>[^<]", block))

    while True:
        found = BREAK_ONLY.search(xml)
        while found is not None and carries_text(found.group(0)):
            found = BREAK_ONLY.search(xml, found.end())
        if found is None:
            return xml
        after = re.compile(r"<w:p(?:\s[^>]*)?>", re.S).search(xml, found.end())
        if after is None or xml[found.end():after.start()].strip():
            xml = xml[:found.start()] + xml[found.end():]
            continue
        target = re.compile(r"<w:p(?:\s[^>]*)?>.*?</w:p>", re.S).match(xml, after.start())
        folded = insert_paragraph_props(target.group(0), "<w:pageBreakBefore/>")
        xml = xml[:found.start()] + folded + xml[target.end():]


def attach_section(cover: str, properties: str) -> str:
    cover = re.sub(r"<w:sectPr(?:\s[^>]*)?>.*?</w:sectPr>", "", cover, flags=re.S)
    cover = re.sub(r"<w:sectPr(?:\s[^>]*)?/>", "", cover)
    while True:
        blocks = list(re.finditer(r"<w:p(?:\s[^>]*)?>.*?</w:p>", cover, re.S))
        if not blocks or cover[blocks[-1].end():].strip():
            break
        tail = blocks[-1].group(0)
        if re.search(r"<w:t(?:\s[^>]*)?>[^<]", tail) or "<w:drawing>" in tail:
            break
        cover = cover[:blocks[-1].start()] + cover[blocks[-1].end():]
    blocks = list(re.finditer(r"<w:p(?:\s[^>]*)?>.*?</w:p>", cover, re.S))
    if not blocks or cover[blocks[-1].end():].strip():
        return cover + "<w:p><w:pPr>" + properties + "</w:pPr></w:p>"
    last = blocks[-1]
    block = last.group(0)
    if "<w:pPr>" in block:
        block = block.replace("</w:pPr>", properties + "</w:pPr>", 1)
    else:
        opening = re.match(r"<w:p(?:\s[^>]*)?>", block).group(0)
        block = block.replace(opening, opening + "<w:pPr>" + properties + "</w:pPr>", 1)
    return cover[:last.start()] + block + cover[last.end():]


FOOTER_NS = (
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
)
FOOTER_BODY = (
    '<w:p><w:pPr><w:jc w:val="center"/>'
    '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:pPr>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr>'
    '<w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
)
FOOTER_XML = FOOTER_NS + FOOTER_BODY + "</w:ftr>"
FOOTER_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"
)
FOOTER_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
)


def add_footers(items: dict) -> tuple[str, str]:
    rels = items["word/_rels/document.xml.rels"].decode("utf-8")
    ids = []
    for index, name in (("1", "footer-front.xml"), ("2", "footer-body.xml")):
        rel_id = f"rIdFooter{index}"
        items[f"word/{name}"] = FOOTER_XML.encode("utf-8")
        entry = f'<Relationship Id="{rel_id}" Type="{FOOTER_REL}" Target="{name}"/>'
        if rel_id not in rels:
            rels = rels.replace("</Relationships>", entry + "</Relationships>")
        ids.append(rel_id)
        types = items["[Content_Types].xml"].decode("utf-8")
        override = f'<Override PartName="/word/{name}" ContentType="{FOOTER_TYPE}"/>'
        if override not in types:
            types = types.replace("</Types>", override + "</Types>")
        items["[Content_Types].xml"] = types.encode("utf-8")
    items["word/_rels/document.xml.rels"] = rels.encode("utf-8")
    return ids[0], ids[1]


def number_pages(document: str, front_id: str, body_id: str, page_size: str) -> str:
    heading = re.search(
        r'<w:p(?:\s[^>]*)?>(?:(?!</w:p>).)*?<w:t(?:\s[^>]*)?>LỜI MỞ ĐẦU</w:t>',
        document, re.S,
    )
    if heading is None:
        raise SystemExit("không thấy tiêu đề LỜI MỞ ĐẦU để chia phần")

    tail = re.search(r"<w:sectPr>.*?</w:sectPr>", document[heading.end():], re.S)
    if tail is None:
        raise SystemExit("không thấy sectPr cuối tài liệu")
    start, end = heading.end() + tail.start(), heading.end() + tail.end()
    body_section = document[start:end]
    margins = re.search(r"<w:pgMar[^/]*/>", body_section).group(0)

    numbered_body = body_section.replace(
        "<w:sectPr>",
        f'<w:sectPr><w:footerReference w:type="default" r:id="{body_id}"/>',
        1,
    ).replace(
        "</w:sectPr>",
        '<w:pgNumType w:fmt="decimal" w:start="1"/></w:sectPr>',
        1,
    )
    document = document[:start] + numbered_body + document[end:]

    front_section = (
        "<w:p><w:pPr><w:sectPr>"
        f'<w:footerReference w:type="default" r:id="{front_id}"/>'
        + page_size + margins
        + '<w:pgNumType w:fmt="lowerRoman" w:start="1"/>'
        "</w:sectPr></w:pPr></w:p>"
    )
    return document[:heading.start()] + front_section + document[heading.start():]


def drop_third_student(xml: str) -> str:
    for row in re.findall(r"<w:tr[ >].*?</w:tr>", xml, re.S):
        if "Tên sv 3" in row or "MSSV 3" in row:
            xml = xml.replace(row, "")
    return xml


def next_free_id(rels: str) -> str:
    return LOGO_REL_ID if LOGO_REL_ID not in rels else LOGO_REL_ID + "X"


def main() -> int:
    if not TEMPLATE.exists():
        raise SystemExit(f"không thấy mẫu bìa: {TEMPLATE}")
    if not REPORT.exists():
        raise SystemExit("chưa có báo cáo, chạy build_report_v2.py trước")

    template = zipfile.ZipFile(TEMPLATE)
    template_doc = template.read("word/document.xml").decode("utf-8")
    logo = template.read("word/media/image1.png")
    borders = re.search(r"<w:pgBorders.*?</w:pgBorders>", template_doc, re.S).group(0)

    cover = cover_body(template_doc)
    cover = drop_third_student(cover)
    for old, new in REPLACEMENTS:
        cover = cover.replace(old, new)

    old_embed = re.search(r'r:embed="([^"]+)"', cover)
    if old_embed is None:
        raise SystemExit("không thấy ảnh logo trong trang bìa mẫu")
    template.close()

    report = zipfile.ZipFile(REPORT)
    items = {name: report.read(name) for name in report.namelist()}
    report.close()

    rels = items["word/_rels/document.xml.rels"].decode("utf-8")
    rel_id = next_free_id(rels)
    cover = cover.replace(f'r:embed="{old_embed.group(1)}"', f'r:embed="{rel_id}"')

    if LOGO_TARGET not in rels:
        entry = (
            f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/image" Target="{LOGO_TARGET}"/>'
        )
        rels = rels.replace("</Relationships>", entry + "</Relationships>")
        items["word/_rels/document.xml.rels"] = rels.encode("utf-8")
    items[f"word/{LOGO_TARGET}"] = logo

    types = items["[Content_Types].xml"].decode("utf-8")
    if 'Extension="png"' not in types:
        entry = '<Default Extension="png" ContentType="image/png"/>'
        first_override = types.find("<Override")
        if first_override == -1:
            types = types.replace("</Types>", entry + "</Types>")
        else:
            types = types[:first_override] + entry + types[first_override:]
        items["[Content_Types].xml"] = types.encode("utf-8")

    document = items["word/document.xml"].decode("utf-8")
    document = merge_namespaces(document, template_doc)

    cover_margin = re.search(r"<w:pgMar[^/]*/>", template_doc).group(0)
    left = int(re.search(r'w:left="(\d+)"', cover_margin).group(1))
    right = int(re.search(r'w:right="(\d+)"', cover_margin).group(1))
    available = PAGE_WIDTH - left - right

    if re.search(r"<w:pgSz[^/]*/>", document):
        document = re.sub(r"<w:pgSz[^/]*/>", PAGE_SIZE, document)
    else:
        document = document.replace("<w:sectPr>", "<w:sectPr>" + PAGE_SIZE)

    cover_section = (
        "<w:sectPr>" + PAGE_SIZE + cover_margin + borders + "</w:sectPr>"
    )
    cover = rebuild_cover_table(single_spaced(cover), available)
    cover = attach_section(cover, cover_section)
    document = compact_table_cells(document)
    document = unjustify_code_paragraphs(document)
    document = fold_page_breaks(document)
    front_id, body_id = add_footers(items)
    document = number_pages(document, front_id, body_id, PAGE_SIZE)
    document = document.replace("<w:body>", "<w:body>" + cover, 1)
    items["word/document.xml"] = document.encode("utf-8")

    backup = REPORT.with_suffix(".pre-cover.docx")
    shutil.copy(REPORT, backup)
    with zipfile.ZipFile(REPORT, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in items.items():
            out.writestr(name, data)

    print(f"ghép trang bìa vào {REPORT.name}")
    print(f"  logo {len(logo) / 1024:.1f} KB, rel {rel_id}")
    print(f"  khung viền firstPage: {'có' if '<w:pgBorders' in document else 'KHÔNG'}")
    print(f"  khổ A4 11906, cột chữ bìa {available} twips, bảng dựng lại vừa khít")
    print(f"  bản trước khi ghép: {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
