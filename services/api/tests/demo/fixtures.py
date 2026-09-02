import ctypes
import hashlib
import io
import struct

import cv2
import numpy as np
import pypdfium2 as pdfium


def synthetic_pdf_bytes(*, page_count: int = 1, width: int = 288, height: int = 384) -> bytes:
    """Build a deterministic, redistributable PDF fixture with no personal data."""

    document = pdfium.PdfDocument.new()
    try:
        for page_index in range(page_count):
            y, x = np.indices((height, width), dtype=np.uint16)
            image = np.empty((height, width, 3), dtype=np.uint8)
            image[:, :, 0] = ((x + page_index * 17) % 256).astype(np.uint8)
            image[:, :, 1] = ((y * 2 + page_index * 29) % 256).astype(np.uint8)
            image[:, :, 2] = (((x // 8 + y // 8) % 2) * 160 + 48).astype(np.uint8)

            page = document.new_page(width, height)
            bitmap_buffer = (ctypes.c_ubyte * image.nbytes).from_buffer(image)
            bitmap = pdfium.PdfBitmap.new_native(
                width,
                height,
                pdfium.raw.FPDFBitmap_BGR,
                buffer=bitmap_buffer,
            )
            try:
                page_image = pdfium.PdfImage.new(document)
                page_image.set_bitmap(bitmap)
                page_image.set_matrix(pdfium.PdfMatrix(width, 0, 0, height, 0, 0))
                page.insert_obj(page_image)
                page.gen_content()
            finally:
                bitmap.close()
                page.close()

        output = io.BytesIO()
        document.save(output)
        return output.getvalue()
    finally:
        document.close()


def blank_pdf_bytes(*, page_sizes: tuple[tuple[int, int], ...]) -> bytes:
    document = pdfium.PdfDocument.new()
    try:
        for width, height in page_sizes:
            page = document.new_page(width, height)
            page.close()
        output = io.BytesIO()
        document.save(output)
        return output.getvalue()
    finally:
        document.close()


def encrypted_pdf_bytes() -> bytes:
    """Build a tiny revision-2 Standard Security PDF with password ``user``."""

    padding = bytes.fromhex(
        "28bf4e5e4e758a4164004e56fffa01082e2e00b6d0683e802f0ca9fe6453697a"
    )

    def padded(value: str) -> bytes:
        return (value.encode("latin-1") + padding)[:32]

    def rc4(key: bytes, data: bytes) -> bytes:
        state = list(range(256))
        cursor = 0
        for index in range(256):
            cursor = (cursor + state[index] + key[index % len(key)]) & 255
            state[index], state[cursor] = state[cursor], state[index]
        output = bytearray()
        index = cursor = 0
        for value in data:
            index = (index + 1) & 255
            cursor = (cursor + state[index]) & 255
            state[index], state[cursor] = state[cursor], state[index]
            output.append(value ^ state[(state[index] + state[cursor]) & 255])
        return bytes(output)

    user = padded("user")
    owner = rc4(hashlib.md5(padded("owner")).digest()[:5], user)
    file_id = bytes.fromhex("00112233445566778899aabbccddeeff")
    permissions = -4
    encryption_key = hashlib.md5(
        user + owner + struct.pack("<i", permissions) + file_id
    ).digest()[:5]
    user_entry = rc4(encryption_key, padding)
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 288 384] >>",
        (
            f"<< /Filter /Standard /V 1 /R 2 /Length 40 /O <{owner.hex()}> "
            f"/U <{user_entry.hex()}> /P {permissions} >>"
        ).encode("ascii"),
    )
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number, payload in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode("ascii"))
        output.extend(payload)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            "trailer\n<< /Size 5 /Root 1 0 R /Encrypt 4 0 R "
            f"/ID [<{file_id.hex()}> <{file_id.hex()}>] >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def synthetic_image_bytes(
    *, extension: str = ".png", width: int = 640, height: int = 480
) -> bytes:
    """Encode a deterministic synthetic raster through the real OpenCV codec."""

    y, x = np.indices((height, width), dtype=np.uint16)
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = ((x * 3 + y) % 256).astype(np.uint8)
    image[:, :, 1] = ((x + y * 2) % 256).astype(np.uint8)
    image[:, :, 2] = (((x // 16 + y // 16) % 2) * 192 + 32).astype(np.uint8)
    encoded_ok, encoded = cv2.imencode(extension, image)
    if not encoded_ok:
        raise RuntimeError("synthetic image encoding failed")
    return encoded.tobytes()
