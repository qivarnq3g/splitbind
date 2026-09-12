import pathlib
import re

import pytest
from django.conf import settings

from splitbind.demo import issuance, verification


API_ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB_ROOT = API_ROOT.parents[1] / "apps" / "web"


def test_no_module_constant_shadows_a_configured_limit():
    for module in (issuance, verification):
        shadowing = [
            name
            for name in dir(module)
            if name.startswith("DEMO_MAX") and name.endswith(("PAGES", "BYTES", "PIXELS"))
        ]
        assert shadowing == [], (
            f"{module.__name__} defines {shadowing}; a processing limit must come from "
            "settings so that the configured value is the enforced value"
        )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("MAX_PDF_BYTES", 100 * 1024 * 1024),
        ("MAX_PDF_PAGES", 50),
        ("MAX_IMAGE_PIXELS", 40_000_000),
        ("MAX_DOCUMENT_RASTER_PIXELS", 120_000_000),
    ],
)
def test_configured_limits_hold_the_released_values(name, expected):
    assert getattr(settings, name) == expected


def test_document_raster_budget_admits_fifty_a4_pages_at_the_render_scale():
    a4_points = (595.276, 841.89)
    scale = issuance.SOURCE_RENDER_SCALE
    per_page = (a4_points[0] * scale) * (a4_points[1] * scale)
    assert per_page * settings.MAX_PDF_PAGES <= settings.MAX_DOCUMENT_RASTER_PIXELS, (
        "the cumulative raster budget rejects a full-length A4 document before the "
        "page limit does, so the advertised page limit is unreachable"
    )


def test_single_image_cap_stays_below_the_document_budget():
    assert settings.MAX_IMAGE_PIXELS < settings.MAX_DOCUMENT_RASTER_PIXELS, (
        "one uploaded image must not be allowed to consume a whole document's raster budget"
    )


def test_browser_and_server_agree_on_the_byte_ceiling():
    source = (WEB_ROOT / "src" / "features" / "uploads" / "uploadIssuance.ts").read_text(encoding="utf-8")
    match = re.search(r"export const MAX_PDF_BYTES = (\d+) \* 1024 \* 1024;", source)
    assert match, "the browser byte ceiling is no longer declared in the expected form"
    assert int(match.group(1)) * 1024 * 1024 == settings.MAX_PDF_BYTES


@pytest.mark.parametrize("page", ["IssueDocumentPage.tsx", "VerifyDocumentPage.tsx"])
def test_help_text_states_the_limits_actually_enforced(page):
    source = (WEB_ROOT / "src" / "pages" / page).read_text(encoding="utf-8")
    megabytes = settings.MAX_PDF_BYTES // (1024 * 1024)
    assert f"tối đa {megabytes} MB" in source
    assert f"PDF tối đa {settings.MAX_PDF_PAGES} trang" in source
