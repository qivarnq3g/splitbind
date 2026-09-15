import uuid

import cv2
import numpy as np
import pytest

from splitbind.demo.issuance import (
    _build_issuance_artifact,
    _select_frozen_candidate,
    issuance_output_extension,
)
from splitbind.demo.models import DEMO_CANONICAL_CANVAS
from splitbind.demo.verification import _decode_image
from splitbind.integrations.storage.base import validate_issuance_output_key


KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
ISSUANCE_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def photo(width: int, height: int) -> np.ndarray:
    y, x = np.indices((height, width), dtype=np.float64)
    return (
        np.stack(
            (
                40.0 + 150.0 * x / (width - 1),
                55.0 + 130.0 * y / (height - 1),
                70.0 + 110.0 * (x + y) / (width + height - 2),
            ),
            axis=2,
        )
        .clip(0, 255)
        .astype(np.uint8)
    )


def encoded(image: np.ndarray, extension: str) -> bytes:
    written, buffer = cv2.imencode(extension, image)
    assert written
    return buffer.tobytes()


@pytest.mark.parametrize("extension", [".png", ".jpg"])
def test_an_uploaded_image_is_issued_as_a_traceable_png(extension):
    source = encoded(photo(1400, 900), extension)

    output, page_count, _identifier, content_type = _build_issuance_artifact(
        source, issuance_id=ISSUANCE_ID, fingerprint_key=KEY
    )

    assert content_type == "image/png"
    assert page_count == 1
    issued = cv2.imdecode(np.frombuffer(output, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert issued.shape[:2] == (900, 1400)

    candidate, _frozen = _select_frozen_candidate()
    summary, pages = _decode_image(
        output,
        width=1400,
        height=900,
        fingerprint_key=KEY,
        candidates=(candidate,),
    )
    assert pages == 1
    assert summary.status == "decoded", summary.status
    assert summary.issuance_id == ISSUANCE_ID


def test_a_pdf_upload_still_produces_a_pdf():
    source = b"%PDF-1.4\n%%EOF\n"

    with pytest.raises(Exception):
        _build_issuance_artifact(source, issuance_id=ISSUANCE_ID, fingerprint_key=KEY)


def test_output_extension_follows_the_uploaded_content_type():
    assert issuance_output_extension("application/pdf") == "pdf"
    assert issuance_output_extension("image/png") == "png"
    assert issuance_output_extension("image/jpeg") == "png"
    assert issuance_output_extension("") == "pdf"


def test_the_image_output_key_shape_is_accepted():
    organization = uuid.uuid4()
    issuance = uuid.uuid4()
    for extension in ("pdf", "png"):
        validate_issuance_output_key(
            f"outputs/issuance/{organization}/{issuance}.{extension}"
        )
    with pytest.raises(ValueError):
        validate_issuance_output_key(
            f"outputs/issuance/{organization}/{issuance}.exe"
        )


def test_a_page_sized_image_round_trips_through_the_canonical_canvas():
    height, width = DEMO_CANONICAL_CANVAS
    source = encoded(photo(width, height), ".png")

    output, _pages, _identifier, _content_type = _build_issuance_artifact(
        source, issuance_id=ISSUANCE_ID, fingerprint_key=KEY
    )

    candidate, _frozen = _select_frozen_candidate()
    summary, _pages = _decode_image(
        output, width=width, height=height, fingerprint_key=KEY, candidates=(candidate,)
    )
    assert summary.issuance_id == ISSUANCE_ID
