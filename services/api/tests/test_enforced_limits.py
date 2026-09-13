import math
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
        ("MAX_PDF_BYTES", 100 * 1000 * 1000),
        ("MAX_PDF_PAGES", 50),
        ("MAX_IMAGE_PIXELS", 40_000_000),
        ("MAX_DOCUMENT_RASTER_PIXELS", 140_000_000),
    ],
)
def test_configured_limits_hold_the_released_values(name, expected):
    assert getattr(settings, name) == expected


def test_document_raster_budget_admits_a_full_length_a4_document():
    a4_points = (595.276, 841.89)
    scale = issuance.SOURCE_RENDER_SCALE
    rendered = math.ceil(a4_points[0] * scale) * math.ceil(a4_points[1] * scale)
    canvas = issuance.CANONICAL_CANVAS[0] * issuance.CANONICAL_CANVAS[1]
    per_page = max(rendered, canvas)
    assert per_page * settings.MAX_PDF_PAGES <= settings.MAX_DOCUMENT_RASTER_PIXELS, (
        "_validate_raster_budget charges every page at least the canonical canvas, "
        "so a budget sized only from the rendered page area rejects a full-length "
        "document before the page limit does and makes the advertised limit unreachable"
    )


def test_single_image_cap_stays_below_the_document_budget():
    assert settings.MAX_IMAGE_PIXELS < settings.MAX_DOCUMENT_RASTER_PIXELS, (
        "one uploaded image must not be allowed to consume a whole document's raster budget"
    )


def test_browser_and_server_agree_on_the_byte_ceiling():
    source = (WEB_ROOT / "src" / "features" / "uploads" / "uploadIssuance.ts").read_text(encoding="utf-8")
    match = re.search(r"export const MAX_PDF_BYTES = (\d+) \* 1000 \* 1000;", source)
    assert match, "the browser byte ceiling is no longer declared in the expected form"
    assert int(match.group(1)) * 1000 * 1000 == settings.MAX_PDF_BYTES
    assert "export const MAX_PDF_LABEL = formatBytes(MAX_PDF_BYTES);" in source, (
        "the displayed limit must be derived from the enforced constant, never typed out, "
        "so the words and the number cannot drift apart"
    )


@pytest.mark.parametrize("page", ["IssueDocumentPage.tsx", "VerifyDocumentPage.tsx"])
def test_help_text_states_the_limits_actually_enforced(page):
    source = (WEB_ROOT / "src" / "pages" / page).read_text(encoding="utf-8")
    assert "tối đa ${MAX_PDF_LABEL}" in source, (
        "the byte limit in the help text must interpolate the derived label rather than "
        "hard-code a number that can fall out of step with the server"
    )
    assert f"PDF tối đa {settings.MAX_PDF_PAGES} trang" in source


def test_committed_result_constraint_admits_every_page_the_limit_allows():
    from splitbind.demo.models import DEMO_MAX_COMMITTED_PAGES

    assert DEMO_MAX_COMMITTED_PAGES >= settings.MAX_PDF_PAGES, (
        "the database CHECK constraint on a committed issuance result would reject a "
        "page count the processing limit accepts, so the job would fail at commit "
        "after the artifact had already been produced and uploaded"
    )
