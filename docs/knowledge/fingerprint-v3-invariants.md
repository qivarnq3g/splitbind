# Fingerprint V3 implementation invariants

Design invariants of the V3 fingerprint generation: what the algorithm guarantees and where its declared boundaries are. Measurements, tuning attempts and refuted hypotheses live in [fingerprint-robustness-experiments.md](fingerprint-robustness-experiments.md) — read that before proposing any change to robustness.

Local knowledge for continuing the versioned V3 recovery work. The approved design and implementation plan remain authoritative; this file records verified implementation details that are easy to lose between task turns.

## Geometry evidence envelope

- `geometry_hypotheses_v3(...)` remains the backward-compatible tuple-returning interface.
- Consumers that must distinguish evidence states use `search_geometry_v3(...) -> GeometrySearchV3`.
- `GeometrySearchV3.sync_reason` is the actual V2 fallback result when fallback ran: `aligned`, `insufficient_sync_evidence`, or `geometry_rejected`.
- When the hypothesis ceiling is already full and fallback is not run, `sync_reason` is `None`; reporting `aligned` in that branch fabricates synchronization evidence.
- Accepted shape priors remain usable even if the optional sync fallback is rejected. A geometry runtime exception propagates and is not converted into an evidence status.

## Crop-resilient tile ordering

- V3 first creates the same non-overlapping grid shape as V2, then applies the V3 HMAC shuffle bound to key, page index, and the complete V3 candidate identifier.
- Within that shuffled order, tiles fully contained by every frozen centered `crop_retained_scale` are stably prioritized. This preserves HMAC order inside the survivor and vulnerable groups.
- The payload prefix must retain at least `max(2, ceil(0.60 * payload_repetitions))` whole tiles under the frozen center crop on the canonical 1536×3072 canvas.
- Verified failure signature before survivor prioritization: crop reconstruction was pixel-exact, but the first 384-pixel/three-repetition candidate placed two payload tiles in cropped border bands. Gradient retained only one valid tile vote; whitespace retained a nonuniform spread tile and no valid vote. The defect was placement, not geometry reconstruction.

## Verification boundary

- Task 4 reference evidence covers representative identity, JPEG 70, resize 0.75, center crop 25%, negative attribution, conflict voting, and V2 regression.
- These checks do not promote a V3 profile. Pre-gate and release decisions remain separate fail-closed tasks.
