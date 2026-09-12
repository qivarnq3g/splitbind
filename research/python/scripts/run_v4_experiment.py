"""V4 comparison harness: sweep the V3 spread-spectrum parameters that were frozen.

This is NOT the V3 pre-gate and its numbers must never be quoted as pre-gate
evidence. It is a separate harness that re-measures the V3 baseline alongside
each variant in the same process, so the comparison between rows is internally
valid even where absolute rates differ from the official pre-gate.

Why this design: the V3 pre-gate is hash-bound to `load_v3_profiles()` in several
validation paths and asserts exactly four candidates, so it cannot score a
different grid without being forked. Rather than fork a validated harness under
time pressure, this script reuses the V3 embed/decode primitives directly and
re-measures the baseline for comparison.

The only V3 behaviour suppressed here is `_validate_canonical_profile`, which
rejects any profile outside the sealed grid. That check is a provenance guard,
not part of the algorithm; every structural validator in the tile, DCT and
spread modules still runs. V3's own files are not modified.

Usage:
    python run_v4_experiment.py --corpus <manifest> --variant <0-3> --output <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

PYTHON_PROJECT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PYTHON_PROJECT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from splitbind_attack.attacks import AttackCase, apply_attack  # noqa: E402
from splitbind_bench.runner import _fit_canvas, iter_corpus_pages  # noqa: E402
from splitbind_ref import fingerprint_v3  # noqa: E402
from splitbind_ref.fingerprint_v3 import (  # noqa: E402
    FingerprintV3Context,
    decode_fingerprint_v3,
    embed_fingerprint_v3,
)
from splitbind_ref.fingerprint_v3_profile import (  # noqa: E402
    candidate_identifier_v3,
    load_v3_profiles,
)

CONTRACT_V4 = (
    PYTHON_PROJECT.parents[1] / "contracts" / "algorithm" / "fingerprint-candidates.v4.json"
)
SEED = 20260905
IDENTITY_DOMAIN = b"splitbind/bench/identity/v1"
# Research canonical canvas: (height, width). 1536x3072 yields exactly 3x6 = 18
# non-overlapping 512px tile slots, matching the frozen tiles_per_page.
CANVAS_HEIGHT, CANVAS_WIDTH = 1536, 3072

POSITIVE_PAGES = {
    "image-clean-gradient": (0,),
    "image-clean-mixed": (0,),
    "image-clean-noise": (0,),
    "pdf-multi-mixed": (0, 1, 2),
    "pdf-multi-noise": (0, 1),
    "pdf-one-gradient": (0,),
    "pdf-one-vector": (0,),
    "pdf-one-whitespace": (0,),
    "tamper-ground-truth": (0,),
}

ATTACKS = (
    AttackCase(case_id="identity", kind="identity", parameters={}),
    AttackCase(case_id="jpeg-70", kind="jpeg", parameters={"quality": 70}),
    AttackCase(case_id="resize-075", kind="resize", parameters={"scale": 0.75}),
    AttackCase(case_id="crop-025", kind="crop", parameters={"fraction": 0.25}),
)


def _structural_only(profile) -> None:
    """Replacement for the sealed-grid provenance guard. Structure still checked."""
    candidate_identifier_v3(profile)


def _case_context(fixture_id: str, page_index: int, profile_sha256: str):
    """Mirror the pre-gate's deterministic per-case identity and key derivation."""
    binding = (
        SEED.to_bytes(8, "big")
        + fixture_id.encode("utf-8")
        + b"\x00"
        + page_index.to_bytes(4, "big")
        + bytes.fromhex(profile_sha256)
    )
    digest = bytearray(hashlib.sha256(IDENTITY_DOMAIN + binding).digest()[:16])
    digest[6] = (digest[6] & 0x0F) | 0x40
    digest[8] = (digest[8] & 0x3F) | 0x80
    from uuid import UUID

    issuance = UUID(bytes=bytes(digest))
    key = hashlib.sha256(b"splitbind/bench/key/v1" + binding).digest()
    return issuance, key


def _build_variants():
    """Return (label, profile) pairs: the V3 baseline plus the V4 sweep."""
    contract = json.loads(CONTRACT_V4.read_text(encoding="utf-8"))
    v4_hash = hashlib.sha256(CONTRACT_V4.read_bytes()).digest()

    baseline = next(
        p for p in load_v3_profiles()
        if p.tile_size_px == 512 and p.payload_repetitions == 5
    )
    variants = [("v3-baseline chips=64 sat=0.75", baseline)]
    for chips in contract["sweep"]["spread_chips_per_bit"]:
        for sat in contract["sweep"]["saturated_fraction_min"]:
            if chips == baseline.spread_chips_per_bit and sat == baseline.saturated_fraction_min:
                continue
            variants.append((
                f"v4 chips={chips} sat={sat}",
                replace(
                    baseline,
                    contract_sha256=v4_hash,
                    spread_chips_per_bit=chips,
                    saturated_fraction_min=float(sat),
                ),
            ))
    return variants


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--variant", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit-pages", type=int, default=None)
    arguments = parser.parse_args(argv)

    # Suppress only the sealed-grid provenance guard; structure still validated.
    fingerprint_v3._validate_canonical_profile = _structural_only

    variants = _build_variants()
    if not 0 <= arguments.variant < len(variants):
        raise SystemExit(f"--variant must be 0..{len(variants) - 1}")
    label, profile = variants[arguments.variant]
    profile_sha = hashlib.sha256(candidate_identifier_v3(profile)).hexdigest()

    arguments.output.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    started = time.time()

    pages = [
        page for page in iter_corpus_pages(arguments.corpus, fixture_ids=set(POSITIVE_PAGES))
        if page.page_index in POSITIVE_PAGES.get(page.source.fixture_id, ())
    ]
    if arguments.limit_pages is not None:
        pages = pages[: arguments.limit_pages]

    for page in pages:
        fixture_id = page.source.fixture_id
        issuance, key = _case_context(fixture_id, page.page_index, profile_sha)
        context = FingerprintV3Context(
            issuance_id=issuance, fingerprint_key=key, page_index=page.page_index
        )
        fitted = _fit_canvas(page.image, CANVAS_WIDTH, CANVAS_HEIGHT)
        embedded = embed_fingerprint_v3(fitted.image, context, profile)
        canonical_shape = embedded.image.shape[:2]
        for attack in ATTACKS:
            rng = np.random.default_rng(
                int.from_bytes(
                    hashlib.sha256(
                        f"{fixture_id}/{page.page_index}/{attack.case_id}".encode()
                    ).digest()[:8],
                    "big",
                )
            )
            artifact = apply_attack(embedded.image, attack, rng)
            decision = decode_fingerprint_v3(
                artifact.image, key, page.page_index, canonical_shape, (profile,),
                embedded.sync_template,
            )
            decoded = getattr(decision, "issuance_id", None)
            rows.append({
                "variant": label,
                "profile_sha256": profile_sha,
                "fixture_id": fixture_id,
                "page_index": page.page_index,
                "attack": attack.case_id,
                "expected_id": str(issuance),
                "decoded_id": str(decoded) if decoded else None,
                "correct": bool(decoded) and str(decoded) == str(issuance),
                "valid_vote_count": getattr(decision, "valid_vote_count", None),
                "confidence": getattr(decision, "geometry_confidence", None),
                "status": getattr(decision, "status", None),
                "psnr_db": embedded.psnr_db,
                "ssim": embedded.ssim,
            })
            print(
                f"[{label}] {fixture_id} p{page.page_index} {attack.case_id} shape={canonical_shape}: "
                f"correct={rows[-1]['correct']} votes={rows[-1]['valid_vote_count']}",
                flush=True,
            )

    elapsed = time.time() - started
    summary = {
        "variant": label,
        "profile_sha256": profile_sha,
        "spread_chips_per_bit": profile.spread_chips_per_bit,
        "saturated_fraction_min": profile.saturated_fraction_min,
        "tile_size_px": profile.tile_size_px,
        "payload_repetitions": profile.payload_repetitions,
        "rows": len(rows),
        "elapsed_seconds": round(elapsed, 1),
        "minimum_psnr_db": min((r["psnr_db"] for r in rows), default=None),
        "minimum_ssim": min((r["ssim"] for r in rows), default=None),
        "decode": {
            a.case_id: {
                "correct": sum(1 for r in rows if r["attack"] == a.case_id and r["correct"]),
                "total": sum(1 for r in rows if r["attack"] == a.case_id),
            }
            for a in ATTACKS
        },
        "harness": "run_v4_experiment.py (NOT the V3 pre-gate)",
    }
    stem = f"variant-{arguments.variant}"
    (arguments.output / f"{stem}-rows.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    (arguments.output / f"{stem}-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
