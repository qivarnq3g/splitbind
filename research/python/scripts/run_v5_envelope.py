"""V5 experiment: measure the full attack envelope and score two decision policies.

Two questions this answers that the V3 pre-gate never asked:

1. **Does the watermark survive a screenshot?** The pre-gate measures only
   identity, JPEG 70, resize 0.75 and centre crop 0.25. The attack contract has
   always contained a `screenshot` family (raster letterbox at 1920x1080 and
   1366x768, plus a perspective warp simulating a photograph of a screen), and
   it has never been run against V3.

2. **Is the two-vote quorum costing attributions it should not?** Every row
   records `valid_vote_count`, so each row can be scored under the shipped
   policy (attribute at >= 2 agreeing ECC/CRC-valid votes) and under the
   proposed policy (attribute at >= 1) without re-running anything. Negative
   fixtures are included precisely so the false-attribution cost of the looser
   policy is measured rather than assumed.

This is NOT the V3 pre-gate. Its absolute rates differ from the pre-gate's
because attack RNG derivation differs and the decoder is given the ORB sync
template. Compare rows within this harness only.

Usage:
    python run_v5_envelope.py --corpus <manifest> --output <dir> [--shard i/n]
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

# The 12 positive page slots the V3 pre-gate embeds into, plus negatives so the
# false-attribution cost of a looser quorum is measured, not assumed.
POSITIVE_PAGES = {
    "image-clean-gradient": (0,), "image-clean-mixed": (0,), "image-clean-noise": (0,),
    "pdf-multi-mixed": (0, 1, 2), "pdf-multi-noise": (0, 1), "pdf-one-gradient": (0,),
    "pdf-one-vector": (0,), "pdf-one-whitespace": (0,), "tamper-ground-truth": (0,),
}
NEGATIVE_FIXTURES = tuple(f"negative-external-{i:02d}" for i in range(10))

ATTACKS = (
    AttackCase(case_id="identity", kind="identity", parameters={}),
    AttackCase(case_id="jpeg-85", kind="jpeg", parameters={"quality": 85}),
    AttackCase(case_id="jpeg-70", kind="jpeg", parameters={"quality": 70}),
    AttackCase(case_id="jpeg-50", kind="jpeg", parameters={"quality": 50}),
    AttackCase(case_id="crop-010", kind="crop", parameters={"fraction": 0.10}),
    AttackCase(case_id="crop-025", kind="crop", parameters={"fraction": 0.25}),
    AttackCase(case_id="crop-050", kind="crop", parameters={"fraction": 0.50}),
    AttackCase(case_id="resize-075", kind="resize", parameters={"scale": 0.75}),
    AttackCase(case_id="resize-050", kind="resize", parameters={"scale": 0.50}),
    AttackCase(case_id="resize-150", kind="resize", parameters={"scale": 1.50}),
    AttackCase(
        case_id="screenshot-1920", kind="screenshot",
        parameters={"kind": "raster", "width_px": 1920, "height_px": 1080},
    ),
    AttackCase(
        case_id="screenshot-1366", kind="screenshot",
        parameters={"kind": "raster", "width_px": 1366, "height_px": 768},
    ),
    AttackCase(
        case_id="screenshot-perspective", kind="screenshot",
        parameters={
            "kind": "perspective", "width_px": 1920, "height_px": 1080,
            "corner_offsets": [[0.03, 0.02], [-0.02, 0.04], [-0.03, -0.02], [0.02, -0.03]],
        },
    ),
)


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
    parser.add_argument("--shard", default="0/1")
    arguments = parser.parse_args(argv)
    shard_index, shard_count = (int(v) for v in arguments.shard.split("/"))

    profile = next(
        p for p in load_v3_profiles()
        if p.tile_size_px == 512 and p.payload_repetitions == 5
    )
    profile_sha = hashlib.sha256(candidate_identifier_v3(profile)).hexdigest()
    arguments.output.mkdir(parents=True, exist_ok=True)

    wanted = set(POSITIVE_PAGES) | set(NEGATIVE_FIXTURES)
    pages = [
        page for page in iter_corpus_pages(arguments.corpus, fixture_ids=wanted)
        if page.source.fixture_id in NEGATIVE_FIXTURES
        or page.page_index in POSITIVE_PAGES.get(page.source.fixture_id, ())
    ]
    pages = [p for i, p in enumerate(pages) if i % shard_count == shard_index]

    rows: list[dict] = []
    started = time.time()
    for page in pages:
        fixture_id = page.source.fixture_id
        positive = fixture_id in POSITIVE_PAGES
        issuance, key = _case_context(fixture_id, page.page_index, profile_sha)
        fitted = _fit_canvas(page.image, CANVAS_WIDTH, CANVAS_HEIGHT)
        if positive:
            context = FingerprintV3Context(
                issuance_id=issuance, fingerprint_key=key, page_index=page.page_index
            )
            embedded = embed_fingerprint_v3(fitted.image, context, profile)
            carrier, template = embedded.image, embedded.sync_template
            psnr, ssim = embedded.psnr_db, embedded.ssim
        else:
            # Negative fixtures are never embedded; any vote here is a false vote.
            carrier, template, psnr, ssim = fitted.image, None, None, None
        canonical_shape = carrier.shape[:2]

        for attack in ATTACKS:
            rng = np.random.default_rng(
                int.from_bytes(
                    hashlib.sha256(
                        f"{fixture_id}/{page.page_index}/{attack.case_id}".encode()
                    ).digest()[:8], "big",
                )
            )
            try:
                artifact = apply_attack(carrier, attack, rng)
                decision = decode_fingerprint_v3(
                    artifact.image, key, page.page_index, canonical_shape,
                    (profile,), template,
                )
                votes = decision.valid_votes
                decoded = decision.issuance_id
                confidence = decision.confidence
                ber = decision.bit_error_rate
                status = decision.status
                error = None
            except Exception as exc:  # noqa: BLE001 - record, never mask
                votes, decoded, error = 0, None, f"{type(exc).__name__}: {exc}"
                confidence, ber, status = None, None, None

            matches = bool(decoded) and str(decoded) == str(issuance)
            rows.append({
                "fixture_id": fixture_id, "page_index": page.page_index,
                "attack": attack.case_id, "attack_kind": attack.kind,
                "positive": positive, "valid_vote_count": votes,
                "decoded_id": str(decoded) if decoded else None,
                "expected_id": str(issuance) if positive else None,
                "decoded_matches_expected": matches,
                # Shipped policy attributes at >= 2 votes; proposed policy at >= 1.
                "attributed_quorum2": bool(decoded) and votes >= 2,
                "attributed_quorum1": bool(decoded) and votes >= 1,
                "confidence": confidence, "bit_error_rate": ber,
                "decode_status": status,
                "psnr_db": psnr, "ssim": ssim, "error": error,
            })
            print(
                f"{fixture_id} p{page.page_index} {attack.case_id}: "
                f"pos={positive} votes={votes} match={matches}"
                + (f" ERROR={error}" if error else ""),
                flush=True,
            )

    stem = f"envelope-shard-{shard_index}"
    (arguments.output / f"{stem}-rows.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "rows": len(rows), "elapsed_seconds": round(time.time() - started, 1),
        "profile_sha256": profile_sha,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
