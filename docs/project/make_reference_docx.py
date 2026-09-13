from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "ref-default.docx"
TARGET = HERE / "reference-report.docx"

TWIPS_PER_CM = 566.9291
FONT = "Times New Roman"
BODY_HALF_POINTS = "26"
LINE_1_5 = "360"

MARGINS = {
    "top": round(3.5 * TWIPS_PER_CM),
    "bottom": round(3.0 * TWIPS_PER_CM),
    "left": round(3.5 * TWIPS_PER_CM),
    "right": round(2.0 * TWIPS_PER_CM),
}

HEADING_RULES = {
    "Heading1": (True, False, True),
    "Heading2": (True, False, False),
    "Heading3": (True, True, False),
    "Heading4": (False, True, False),
    "Heading5": (False, True, False),
    "Heading6": (False, True, False),
}

COVER_STYLES = [
    ("CoverHeader", "Cover Header", "28"),
    ("CoverBigTitle", "Cover Big Title", "72"),
    ("CoverTitle", "Cover Title", "40"),
    ("CoverLine", "Cover Line", "28"),
]

TABLE_BORDERS = (
    "<w:tblBorders>"
    '<w:top w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
    '<w:left w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
    '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
    '<w:right w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
    '<w:insideH w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
    '<w:insideV w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
    "</w:tblBorders>"
)


def patch_theme(xml: str) -> str:
    return re.sub(r'(<a:latin typeface=")[^"]*(")', rf"\g<1>{FONT}\g<2>", xml)


def patch_compact(xml: str) -> str:
    at = xml.find('w:styleId="Compact"')
    if at == -1:
        raise SystemExit("khong thay style Compact")
    start = xml.rfind("<w:style ", 0, at)
    end = xml.find("</w:style>", at) + len("</w:style>")
    block = xml[start:end]
    properties = (
        '<w:pPr><w:spacing w:before="40" w:after="40" w:line="360"'
        ' w:lineRule="auto"/><w:jc w:val="left"/></w:pPr>'
    )
    if "<w:pPr>" in block:
        block = re.sub(r"<w:pPr>.*?</w:pPr>", properties, block, count=1, flags=re.S)
    else:
        block = block.replace("</w:style>", properties + "</w:style>")
    return xml[:start] + block + xml[end:]


def patch_styles(xml: str) -> str:
    xml = re.sub(
        r'<w:rFonts w:asciiTheme="minorHAnsi"[^/]*/>',
        f'<w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:eastAsia="{FONT}" w:cs="{FONT}"/>',
        xml, count=1,
    )
    xml = xml.replace('<w:sz w:val="24" />', f'<w:sz w:val="{BODY_HALF_POINTS}" />', 1)
    xml = xml.replace('<w:szCs w:val="24" />', f'<w:szCs w:val="{BODY_HALF_POINTS}" />', 1)

    xml, count = re.subn(
        r"(<w:pPrDefault>\s*<w:pPr>).*?(</w:pPr>\s*</w:pPrDefault>)",
        rf'\g<1><w:spacing w:after="120" w:line="{LINE_1_5}" w:lineRule="auto"/>'
        rf'<w:jc w:val="both"/>\g<2>',
        xml, count=1, flags=re.S,
    )
    if count != 1:
        raise SystemExit("pPrDefault not patched")

    xml = re.sub(
        r'w:(ascii|hAnsi|eastAsia|cs)Theme="(?:major|minor)(?:HAnsi|EastAsia|Bidi)"',
        lambda m: f'w:{m.group(1)}="{FONT}"',
        xml,
    )

    for style_id, (bold, italic, caps) in HEADING_RULES.items():
        pattern = rf'(<w:style w:type="paragraph" w:styleId="{style_id}">.*?</w:style>)'
        match = re.search(pattern, xml, re.S)
        if not match:
            continue
        block = match.group(1)
        run = ["<w:rPr>", f'<w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>']
        if bold:
            run.append("<w:b/>")
        if italic:
            run.append("<w:i/>")
        if caps:
            run.append("<w:caps/>")
        run.append(
            f'<w:sz w:val="{BODY_HALF_POINTS}"/><w:szCs w:val="{BODY_HALF_POINTS}"/>'
            '<w:color w:val="000000"/></w:rPr>'
        )
        new_block = re.sub(r"<w:rPr>.*?</w:rPr>", "".join(run), block, count=1, flags=re.S)
        if "<w:rPr>" not in block:
            new_block = block.replace("</w:style>", "".join(run) + "</w:style>")
        new_block = re.sub(
            r"<w:jc[^/]*/>", "", new_block)
        new_block = re.sub(
            r"<w:spacing[^/]*/>",
            f'<w:spacing w:before="240" w:after="120" w:line="{LINE_1_5}" w:lineRule="auto"/>'
            '<w:jc w:val="left"/>',
            new_block, count=1,
        )
        if "<w:keepNext" not in new_block:
            new_block = new_block.replace("<w:pPr>", "<w:pPr><w:keepNext/>", 1)
        xml = xml.replace(block, new_block)

    for style_id in ("Caption", "TableCaption", "ImageCaption"):
        pattern = rf'(<w:style w:type="paragraph" w:styleId="{style_id}">.*?</w:style>)'
        match = re.search(pattern, xml, re.S)
        if not match:
            continue
        block = match.group(1)
        new_block = re.sub(
            r"<w:rPr>.*?</w:rPr>",
            f'<w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}"/><w:i/>'
            f'<w:sz w:val="{BODY_HALF_POINTS}"/><w:szCs w:val="{BODY_HALF_POINTS}"/></w:rPr>',
            block, count=1, flags=re.S,
        )
        if "<w:jc " not in new_block:
            new_block = new_block.replace("<w:pPr>", '<w:pPr><w:jc w:val="center"/>', 1)
        xml = xml.replace(block, new_block)

    table_pattern = r'(<w:style w:type="table" w:default="1" w:styleId="Table">.*?</w:style>)'
    table_match = re.search(table_pattern, xml, re.S)
    if table_match is None:
        raise SystemExit("Table style not found")
    table_block = table_match.group(1)
    if "<w:tblBorders>" not in table_block:
        xml = xml.replace(
            table_block, table_block.replace("<w:tblPr>", "<w:tblPr>" + TABLE_BORDERS, 1)
        )

    xml = patch_compact(xml)

    additions = []
    for style_id, name, size in COVER_STYLES:
        additions.append(
            f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{style_id}">'
            f'<w:name w:val="{name}"/><w:basedOn w:val="Normal"/><w:qFormat/>'
            f'<w:pPr><w:keepNext/><w:spacing w:before="0" w:after="160" '
            f'w:line="{LINE_1_5}" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr>'
            f'<w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/><w:b/>'
            f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr></w:style>'
        )
    return xml.replace("</w:styles>", "".join(additions) + "</w:styles>")


COMPAT = (
    "<w:compat>"
    '<w:compatSetting w:name="compatibilityMode"'
    ' w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>'
    "</w:compat>"
)


def patch_settings(xml: str) -> str:
    if "<w:compat>" in xml:
        return xml
    for marker in ("<w:rsids>", "<m:mathPr>", "<w:themeFontLang", "</w:settings>"):
        if marker in xml:
            return xml.replace(marker, COMPAT + marker, 1)
    return xml


PAGE_SIZE = '<w:pgSz w:w="11906" w:h="16838"/>'


def patch_document(xml: str) -> str:
    margins = (
        f'<w:pgMar w:top="{MARGINS["top"]}" w:right="{MARGINS["right"]}" '
        f'w:bottom="{MARGINS["bottom"]}" w:left="{MARGINS["left"]}" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
    )
    if re.search(r"<w:pgSz[^/]*/>", xml):
        xml = re.sub(r"<w:pgSz[^/]*/>", PAGE_SIZE, xml, count=1)
    else:
        xml = xml.replace("<w:sectPr>", "<w:sectPr>" + PAGE_SIZE, 1)
    if re.search(r"<w:pgMar[^/]*/>", xml):
        return re.sub(r"<w:pgMar[^/]*/>", margins, xml, count=1)
    return xml.replace(PAGE_SIZE, PAGE_SIZE + margins, 1)


def main() -> int:
    if not SOURCE.exists():
        raise SystemExit(
            "ref-default.docx missing. Run:\n"
            "  pandoc -o ref-default.docx --print-default-data-file reference.docx"
        )
    shutil.copy(SOURCE, TARGET)
    source = zipfile.ZipFile(SOURCE)
    items = {name: source.read(name) for name in source.namelist()}
    source.close()

    items["word/styles.xml"] = patch_styles(
        items["word/styles.xml"].decode("utf-8")
    ).encode("utf-8")
    items["word/document.xml"] = patch_document(
        items["word/document.xml"].decode("utf-8")
    ).encode("utf-8")
    items["word/settings.xml"] = patch_settings(
        items["word/settings.xml"].decode("utf-8")
    ).encode("utf-8")
    if "word/theme/theme1.xml" in items:
        items["word/theme/theme1.xml"] = patch_theme(
            items["word/theme/theme1.xml"].decode("utf-8")
        ).encode("utf-8")

    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in items.items():
            out.writestr(name, data)

    print(f"wrote {TARGET.name}")
    print(f"  {FONT} 13pt, line 1.5, A4, margins {MARGINS}")
    print(f"  table borders on, {len(COVER_STYLES)} cover styles added")
    print("  compatibilityMode 15, style Compact canh trai cho o bang")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
