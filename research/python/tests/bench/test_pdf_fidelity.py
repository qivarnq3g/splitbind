"""Final-file quality checks must catch geometry and image regressions."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from splitbind_bench.pdf_fidelity import assess_pdf_fidelity


def pdf_bytes(width=144, height=216, contents=b"0 g 12 12 80 160 re f", pages=1, user_unit=1):
    """Independent tiny PDF fixture; no watermark/production serializer used."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Count {pages} /Kids [".encode()
        + b" ".join(f"{3 + i * 2} 0 R".encode() for i in range(pages))
        + b"] >>",
    ]
    for i in range(pages):
        objects.extend([
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /UserUnit {user_unit} /Resources << >> /Contents {4 + i * 2} 0 R >>".encode(),
            f"<< /Length {len(contents)} >>\nstream\n".encode() + contents + b"\nendstream",
        ])
    return serialize_fixture(objects)


def serialize_fixture(objects):
    result = bytearray(b"%PDF-1.6\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(result)
    result.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    return bytes(result)


def test_identical_pdf_passes_and_report_is_strict_json():
    original = pdf_bytes()
    report = assess_pdf_fidelity(original, original)
    assert report["passed"] is True
    assert report["failures"] == []
    assert report["pages"][0]["identical_pixels"] is True
    assert report["pages"][0]["psnr_db"] is None
    assert report["pages"][0]["ssim"] == pytest.approx(1)
    assert report["source_bytes"] == len(original)
    json.dumps(report, allow_nan=False)


def test_changed_page_size_fails_without_resizing_or_hiding_the_difference():
    report = assess_pdf_fidelity(pdf_bytes(), pdf_bytes(width=1152, height=2304))
    assert report["passed"] is False
    assert report["failures"] == ["page_geometry"]
    assert report["pages"][0]["source_size_pt"] == [144.0, 216.0]
    assert report["pages"][0]["output_size_pt"] == [1152.0, 2304.0]
    assert report["pages"][0]["psnr_db"] is None


def test_same_geometry_does_not_hide_removed_content():
    report = assess_pdf_fidelity(pdf_bytes(), pdf_bytes(contents=b""))
    assert report["passed"] is False
    assert report["failures"] == ["visual_quality"]
    assert report["pages"][0]["psnr_db"] < 38
    assert report["pages"][0]["ssim"] < 0.95


def test_user_unit_changes_physical_size_not_just_canvas_coordinates():
    report = assess_pdf_fidelity(pdf_bytes(), pdf_bytes(user_unit=2))
    assert report["passed"] is False
    assert report["pages"][0]["output_size_pt"] == [288.0, 432.0]


def test_removed_visible_form_appearance_fails_quality():
    appearance = b"0 g 0 0 80 160 re f\n"
    def form_pdf(include_widget):
        return serialize_fixture([
            b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [4 0 R] >> >>",
            b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 144 216] /Resources << >> "
            + (b"/Annots [4 0 R] " if include_widget else b"") + b">>",
            b"<< /Type /Annot /Subtype /Widget /FT /Tx /T (field) /V (synthetic) "
            b"/Rect [12 12 92 172] /P 3 0 R /F 4 /AP << /N 5 0 R >> >>",
            b"<< /Type /XObject /Subtype /Form /BBox [0 0 80 160] /Resources << >> /Length "
            + str(len(appearance)).encode() + b" >>\nstream\n" + appearance + b"endstream",
        ])
    report = assess_pdf_fidelity(form_pdf(True), form_pdf(False))
    assert report["passed"] is False
    assert report["failures"] == ["visual_quality"]
    assert report["pages"][0]["identical_pixels"] is False


def test_page_count_difference_is_not_silently_zipped_away():
    report = assess_pdf_fidelity(pdf_bytes(), pdf_bytes(pages=2))
    assert report["passed"] is False
    assert report["failures"] == ["page_count"]
    assert report["source_pages"] == 1
    assert report["output_pages"] == 2


def test_size_in_bytes_is_reported_but_not_confused_with_page_size():
    original = pdf_bytes()
    report = assess_pdf_fidelity(original, original + b"\n% harmless trailing comment\n")
    assert report["passed"] is True
    assert report["output_bytes"] > report["source_bytes"]
    assert report["source_sha256"] != report["output_sha256"]


@pytest.mark.parametrize(
    "bad",
    [b"not pdf", b"%PDF-broken", b"%PDF-" + b"x" * (10 * 1024 * 1024)],
    ids=["not-pdf", "broken-pdf", "oversized"],
)
def test_invalid_or_oversized_input_cannot_pass(bad):
    with pytest.raises(ValueError):
        assess_pdf_fidelity(bad, pdf_bytes())


def test_oversized_page_is_rejected_before_render():
    large = pdf_bytes(width=20000, height=20000)
    with pytest.raises(ValueError, match="raster_budget"):
        assess_pdf_fidelity(large, large)


@pytest.mark.parametrize("case,expected_exit", [("identical", 0), ("changed", 2), ("missing", 1)])
def test_cli_has_distinct_machine_readable_outcomes(tmp_path, case, expected_exit):
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    source.write_bytes(pdf_bytes())
    if case != "missing":
        output.write_bytes(pdf_bytes() if case == "identical" else pdf_bytes(contents=b""))
    script = Path(__file__).resolve().parents[2] / "scripts" / "check_pdf_fidelity.py"
    command = [sys.executable, str(script), str(source), str(output)]
    result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=tmp_path)
    assert result.returncode == expected_exit
    report = json.loads(result.stdout)
    assert report["passed"] is (case == "identical")
    if case == "changed":
        assert report["failures"] == ["visual_quality"]
    if case == "missing":
        assert report["error"] == "measurement_failed"
    assert str(tmp_path) not in result.stdout
    assert result.stderr == ""
