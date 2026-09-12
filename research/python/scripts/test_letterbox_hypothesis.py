"""Test one prediction: stripping a screenshot's letterbox restores attribution.

The V5 envelope measured screenshot attribution at 0/12 across all three screen
variants, with the decoder reporting `insufficient_sync_evidence` — it never
formed a geometric candidate. Reading `geometry_v3.search_geometry_v3` explains
why: a hypothesis is only proposed when both axes scale by the same ratio, and
letterboxing a 1536x3072 page onto a 1920x1080 screen gives 0.703 and 0.625.

Prediction: remove the uniform border and the ratios agree again (0.625 and
0.625), the `pure_resize` hypothesis fires, and attribution should approach the
resize-0.50 rate of 9/12 — with no change to the watermark itself.

This script embeds, screenshots, strips the border, and decodes, reporting the
rate with and without the strip. A throwaway probe, not a pre-gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from uuid import UUID

import numpy as np

PYTHON_PROJECT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PYTHON_PROJECT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from splitbind_attack.attacks import AttackCase, apply_attack  # noqa: E402
from splitbind_bench.runner import _fit_canvas, iter_corpus_pages  # noqa: E402
from splitbind_ref.fingerprint_v3 import (  # noqa: E402
    FingerprintV3Context,
    decode_fingerprint_v3,
    embed_fingerprint_v3,
)
from splitbind_ref.fingerprint_v3_profile import (  # noqa: E402
    candidate_identifier_v3,
    load_v3_profiles,
)

SEED = 20260905
IDENTITY_DOMAIN = b"splitbind/bench/identity/v1"
CANVAS_HEIGHT, CANVAS_WIDTH = 1536, 3072

POSITIVE_PAGES = {
    "image-clean-gradient": (0,), "image-clean-mixed": (0,), "image-clean-noise": (0,),
    "pdf-multi-mixed": (0, 1, 2), "pdf-multi-noise": (0, 1), "pdf-one-gradient": (0,),
    "pdf-one-vector": (0,), "pdf-one-whitespace": (0,), "tamper-ground-truth": (0,),
}

SCREENSHOTS = (
    AttackCase(case_id="screenshot-1920", kind="screenshot",
               parameters={"kind": "raster", "width_px": 1920, "height_px": 1080}),
    AttackCase(case_id="screenshot-1366", kind="screenshot",
               parameters={"kind": "raster", "width_px": 1366, "height_px": 768}),
)


def strip_letterbox(image: np.ndarray, tolerance: int = 12) -> np.ndarray:
    """Remove uniform border rows/columns, the way a screen capture pads content.

    Deterministic and parameter-free beyond the tolerance: find the modal border
    colour from the four edges, then trim rows and columns that are uniformly
    within tolerance of it. Returns the input unchanged when nothing is trimmed.
    """
    if image.ndim != 3:
        return image
    edges = np.concatenate([
        image[0, :, :].reshape(-1, 3), image[-1, :, :].reshape(-1, 3),
        image[:, 0, :].reshape(-1, 3), image[:, -1, :].reshape(-1, 3),
    ])
    border = np.median(edges, axis=0)
    close = np.all(np.abs(image.astype(np.int16) - border.astype(np.int16)) <= tolerance, axis=2)
    row_is_border = np.all(close, axis=1)
    col_is_border = np.all(close, axis=0)
    rows = np.flatnonzero(~row_is_border)
    cols = np.flatnonzero(~col_is_border)
    if rows.size == 0 or cols.size == 0:
        return image
    return np.ascontiguousarray(image[rows[0]: rows[-1] + 1, cols[0]: cols[-1] + 1])


def _case_context(fixture_id: str, page_index: int, profile_sha256: str):
    binding = (
        SEED.to_bytes(8, "big") + fixture_id.encode("utf-8") + b"\x00"
        + page_index.to_bytes(4, "big") + bytes.fromhex(profile_sha256)
    )
    digest = bytearray(hashlib.sha256(IDENTITY_DOMAIN + binding).digest()[:16])
    digest[6] = (digest[6] & 0x0F) | 0x40
    digest[8] = (digest[8] & 0x3F) | 0x80
    key = hashlib.sha256(b"splitbind/bench/key/v1" + binding).digest()
    return UUID(bytes=bytes(digest)), key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args(argv)

    profile = next(p for p in load_v3_profiles()
                   if p.tile_size_px == 512 and p.payload_repetitions == 5)
    profile_sha = hashlib.sha256(candidate_identifier_v3(profile)).hexdigest()
    arguments.output.mkdir(parents=True, exist_ok=True)

    pages = [p for p in iter_corpus_pages(arguments.corpus, fixture_ids=set(POSITIVE_PAGES))
             if p.page_index in POSITIVE_PAGES.get(p.source.fixture_id, ())]

    rows: list[dict] = []
    started = time.time()
    for page in pages:
        fixture_id = page.source.fixture_id
        issuance, key = _case_context(fixture_id, page.page_index, profile_sha)
        fitted = _fit_canvas(page.image, CANVAS_WIDTH, CANVAS_HEIGHT)
        context = FingerprintV3Context(
            issuance_id=issuance, fingerprint_key=key, page_index=page.page_index
        )
        embedded = embed_fingerprint_v3(fitted.image, context, profile)
        canonical_shape = embedded.image.shape[:2]

        for attack in SCREENSHOTS:
            rng = np.random.default_rng(
                int.from_bytes(hashlib.sha256(
                    f"{fixture_id}/{page.page_index}/{attack.case_id}".encode()
                ).digest()[:8], "big")
            )
            shot = apply_attack(embedded.image, attack, rng).image
            stripped = strip_letterbox(shot)
            for label, raster in (("raw", shot), ("stripped", stripped)):
                decision = decode_fingerprint_v3(
                    raster, key, page.page_index, canonical_shape,
                    (profile,), embedded.sync_template,
                )
                matched = (decision.issuance_id is not None
                           and str(decision.issuance_id) == str(issuance))
                rows.append({
                    "fixture_id": fixture_id, "page_index": page.page_index,
                    "attack": attack.case_id, "variant": label,
                    "shape": list(raster.shape[:2]), "votes": decision.valid_votes,
                    "status": decision.status, "matched": matched,
                })
                print(f"{fixture_id} p{page.page_index} {attack.case_id} {label:9}"
                      f" shape={raster.shape[:2]} votes={decision.valid_votes}"
                      f" status={decision.status} match={matched}", flush=True)

    (arguments.output / "letterbox-rows.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8")

    print("\n" + "=" * 68)
    for attack in SCREENSHOTS:
        for label in ("raw", "stripped"):
            sub = [r for r in rows if r["attack"] == attack.case_id and r["variant"] == label]
            hit = sum(1 for r in sub if r["matched"])
            print(f"{attack.case_id:20} {label:9} {hit:>3}/{len(sub)}")
    print(f"elapsed {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
