# Fingerprint robustness: measurements, refutations, and the root cause

Experimental log for the SplitBind fingerprint. Design invariants are in [fingerprint-v3-invariants.md](fingerprint-v3-invariants.md).

**Reading guide.** Read in this order if you are new to it; jump directly if you know what you need:

| You are… | Read |
|---|---|
| quoting a robustness number | "Measured V3 pre-gate robustness" then "clean-channel ceiling" — never quote a rate without the decomposition |
| explaining why V3 beats V1 | "What changed between generations" and "REFUTED: `qim_delta`" |
| proposing a parameter change | all four REFUTED / RETRACTED / NEGATIVE sections first — every parameter lever is exhausted |
| asking what survives crop or screenshot | "MEASURED: the full attack envelope", then "ROOT CAUSE" and "REFINED" |
| about to build a V4 | "ROOT CAUSE", "CONFIRMED FIX" and the three failure classes in "REFINED" |

Four claims here are recorded as **refuted or retracted**, including one of this author's own headline numbers. They are kept rather than deleted because each reasoning error is reusable; deleting them invites re-proposing a dead lever.

## Measured V3 pre-gate robustness (2026-09-06)

`reports/fingerprint-pregate-v3/summary.json`, `status: complete`, `planned_rows` 352 = `completed_rows` 352, `execution_errors: 0`, `false_attributions: 0`, 4 candidates at 12 quality observations each.

Best candidate `da34231d8ae5b50c0271cd5d06a794a780c0a1c051d791d9e1d7d778ce1e9d56`:

| Metric | V1 best (`fingerprint-profile-v1.md`) | V3 best | Denominator |
|---|---|---|---|
| JPEG-70 decode | 0 / 12 (0.000) | **9 / 12 (0.750)** | 12 |
| Resize-0.75 decode | 0 / 12 (0.000) | **8 / 12 (0.667)** | 12 |
| Crop-0.25 decode | 1 / 3 (0.333) | **9 / 12 (0.750)** | 12 |
| Execution errors | 31 / 682 | **0 / 352** | — |
| False attributions | 0 | 0 | — |
| Minimum PSNR | 69.31 dB | 42.47 dB | 12 |
| Minimum SSIM | 0.99992 | 0.9554 | 12 |

**The comparison is controlled.** Both generations were measured against the identical corpus contract SHA-256 `e5837cd446ab9c9959ba3fc4b85d205ec9d80e91efc6f801d139810b088a77ef`, under the same gate definitions (JPEG-70 and resize-0.75 each at least 0.95, crop-0.25 at least 0.90, quality population exactly 12) and the same denominator of 12 unique positive candidate/page pairs. The improvement is therefore attributable to the algorithm generation, not to a changed split or metric.

**What V3 bought and what it paid.** V3 trades imperceptibility for robustness: minimum PSNR falls from 69.31 dB to 42.47 dB and minimum SSIM from 0.99992 to 0.9554. Both remain above the release quality gates (38 dB PSNR, 0.95 SSIM), so the trade is inside budget. This is the classic watermarking capacity/robustness/imperceptibility trade-off made concrete on one corpus.

**What it does not establish.** `evidence_scope` is `research_measurement_only` and the summary's own limitations state that the V3 pre-gate is a deterministic cost-control filter, not release evidence, and that it measures only identity, JPEG 70, resize 0.75 and center crop 0.25. `profile_promoted` is `False` and `qualified_candidate_ids` is empty because 0.750 and 0.667 miss the 0.95 gates. V3 is **not** promotable on this evidence, and no slide may describe it as a released capability.

Do not restate the V1 figure of 0/12 as "the project's watermark robustness" without saying it is the V1 generation. On the same corpus the current research generation reaches 0.750 on JPEG-70. Reporting only the V1 number understates the measured work by a wide margin; reporting the V3 number without its `research_measurement_only` scope overstates it.

Of the eight SSOT admission criteria, seven are satisfied (benchmark script `run_v3_pregate.py`, fixed corpus, recorded `plan_sha256` and contract hashes, raw `results.csv`/`results.jsonl`, their SHA-256 values, a documented pipeline, and no conflict with frozen V1 once labelled by generation). The open criterion is an independent re-run to confirm reproducibility.

### The 9/12 figure is a clean-channel ceiling, not attack damage

Reading 9/12 as "V3 survives 75% of JPEG-70" is wrong, and the raw rows refute it. Decomposing the best candidate's 88 rows by which page failed:

| Attack | Failures | Same pages as identity? | Additional failures vs identity |
|---|---|---|---|
| identity (no attack) | 3 | — | — |
| JPEG-70 | 3 | **yes** | **0** |
| Crop-0.25 | 3 | **yes** | **0** |
| Resize-0.75 | 4 | no | **1** |

All three identity failures are the three pages of one fixture, `pdf-multi-mixed` pages 0, 1 and 2. Every one is `outcome: partial` with `valid_vote_count: 1` and **`bit_error_rate: 0.0`** — the decoder recovered the payload bits without a single bit error and then declined to attribute, because only one of three payload repetitions produced a valid tile vote and the fail-safe requires more. Confidence was 0.3333 in each case.

The correct statement is therefore: **under JPEG-70 and centre crop 0.25, V3 decodes exactly as well as it does on the unattacked channel — zero additional loss.** The residual 3/12 gap is a tile-placement and vote-coverage limitation on one multi-page fixture, not compression or cropping damage. Only resize 0.75 inflicts genuine attack damage, and only one row: `image-clean-noise` page 0, `not_detected`, zero valid votes.

This links directly to the crop-resilient tile ordering rule above: the payload prefix must retain at least `max(2, ceil(0.60 * payload_repetitions))` whole tiles. With `payload_repetitions = 3` that threshold is 2 votes, and `pdf-multi-mixed` yields 1. The fixture exposes the placement constraint, exactly as the earlier V3 failure signature predicted — the defect is placement, not geometry reconstruction and not channel robustness.

Consequences for reporting:

- Do not present 0.750 as a robustness rate without the decomposition. It understates JPEG-70 and crop performance, which are at clean-channel parity, and it hides the real limitation, which is vote coverage on one fixture.
- Do not present it as "JPEG-70 solved" either. The denominator is 12 and one fixture never attributes at all.
- The single honest headline is parity with the unattacked channel under JPEG-70 and crop, one additional loss under resize, zero false attributions in 352 rows, and a decoder that fails closed rather than guessing.

### What changed between generations, and which failure each change addresses

Read directly from `contracts/algorithm/fingerprint-candidates.v{1,2,3}.json`. This is the causal chain behind the measurement above.

| Mechanism | V1 | V2 | V3 | Failure it addresses |
|---|---|---|---|---|
| Embedding band | `HL` (detail) | `LL` (approximation) | `LL` | JPEG quantises high frequencies hardest; V1 embedded exactly where the codec destroys the most |
| `qim_delta` | swept 6.0–12.0 | coupled 24/32/48/64 | fixed **32.0** | A 3–5× larger quantisation step survives JPEG-70's coarse rounding |
| Geometric sync | `orb-ransac` | pilot FFT + ORB, 3+1 hypotheses | pilot + **8 geometry hypotheses**, ratio tolerance 0.001 | Resize shifts the sampling grid and breaks QIM lattice alignment; hypothesis search reconstructs the grid before decoding |
| Spread spectrum | none | none | **`spread_delta` 4.0, 64 chips/bit** | Spreading each bit over 64 coefficients averages out localised compression damage |

The PSNR cost is a direct consequence of the `qim_delta` increase, not an unexplained regression: raising the step from the 6.0–12.0 range to 32.0 raises quantisation noise proportionally, which is why minimum PSNR falls 69.31 dB → 42.47 dB while staying above the 38 dB gate. Treat this as the project's own quantitative demonstration of the robustness-versus-imperceptibility trade-off.

Do not describe V1's failure as "DWT-DCT-QIM does not work". It failed for two identifiable and since-corrected design reasons — band choice and step size — plus a synchronisation method too weak for resampling. The technique was not the problem; the V1 parameterisation was.

### Why V3 cannot be tuned in place, and where the headroom actually is

The V3 grid is sealed in code, not merely in the JSON contract:

- `fingerprint_v3_profile.py` pins `_EXPECTED_FIXED` (including `tiles_per_page: 18`), `_EXPECTED_TILE_SIZES = (384, 512)` and `_EXPECTED_REPETITIONS = (3, 5)`, and rejects any contract whose sweep differs.
- `fingerprint_v3._validate_canonical_profile` raises unless `profile in load_v3_profiles()`, so a hand-built `FingerprintV3Profile` cannot be embedded or decoded at all.

Editing `contracts/algorithm/fingerprint-candidates.v4.json` alone therefore changes nothing: any grid extension is a **V4**, requiring its own contract, loader, identity function and pre-gate. This seal is a feature — it is what makes the recorded `profile_contract_sha256` meaningful — but it means parameter tuning is never a same-day change.

**Where the measured headroom is.** All four V3 candidates, on the identical corpus:

| profile | `tile_size_px` | `payload_repetitions` | JPEG-70 | Resize-0.75 | Crop-0.25 |
|---|---:|---:|---:|---:|---:|
| b61bc037 | 384 | 3 | 8/12 | 8/12 | 8/12 |
| 1baf034d | 384 | 5 | 8/12 | 8/12 | 9/12 |
| da34231d | 512 | 3 | 9/12 | 8/12 | 9/12 |
| f33c8358 | 512 | 5 | **10/12** | **9/12** | 8/12 |

Both axes improve JPEG-70 and resize monotonically, and the winner sits on the **corner of the grid** — the trend had not flattened when the sweep ran out of room. Note that `f33c8358`, not `da34231d`, is the JPEG-70 and resize leader; `da34231d` leads only on the aggregate the pre-gate happens to rank by. Name the candidate whenever quoting a rate.

Two ceilings explain why the grid stops where it does, on the research canvas 1536×3072 = 4,718,592 px (distinct from `DEMO_CANONICAL_CANVAS = (2304, 1152)`, which is the production demo canvas — do not confuse them):

- **`tile_size_px` is geometrically capped.** 18 tiles × 512² = 4,718,592 px, exactly the canvas. 640 px would need 1.56× the canvas for 18 tiles. So 512 is the largest tile that still admits 18 of them; the sweep stops at a hard constraint, not an arbitrary bound.
- **`tiles_per_page` is not capped and was frozen anyway.** At 384 px, 18 tiles occupy only 0.56× the canvas and up to 32 would fit. V1 swept `tiles_per_page` over [12, 18, 24]; V3 froze it at 18 and never tested the headroom.

**The V4 hypothesis worth testing.** The failures are vote starvation (`valid_vote_count: 1`, threshold 2) with `bit_error_rate: 0.0`. `tiles_per_page` raises the number of independent votes **without** raising the crop threshold, which depends on `payload_repetitions` only via `max(2, ceil(0.60 × payload_repetitions))`. That is why raising repetitions 3 → 5 helped JPEG-70 but cost crop 9/12 → 8/12: it bought votes and raised the bar at the same time. Raising `tiles_per_page` at `tile_size_px = 384` should buy votes without that penalty. This is a hypothesis with a mechanism and a measurement behind it, not a guess — but it is untested, and must be labelled as untested until a V4 pre-gate run says otherwise.

### REFUTED: raising `tiles_per_page` does not add votes

The hypothesis in the previous section — that `tiles_per_page` buys independent votes without raising the crop threshold — is **wrong**, and the source refutes it directly. Recorded here rather than deleted, because the reasoning error is instructive.

`tile_layout_v3.derive_tiles_v3` ends with:

```python
candidates = crop_survivors + crop_vulnerable
return tuple(candidates[: profile.tiles_per_page])
```

and both `embed_fingerprint_v3` and `decode_fingerprint_v3` then use:

```python
for tile in tiles[:profile.payload_repetitions]:
```

So `tiles_per_page` truncates a pool that is immediately sliced far shorter. With `payload_repetitions` at 3 or 5 and `tiles_per_page` at 18, the 6th through 18th tiles are never touched. Raising the pool to 32 changes nothing functionally; `tiles_per_page` acts only as a page-capacity assertion (`derive_tiles_v3` raises if the page provides fewer non-overlapping slots than requested).

**The number of embedded carriers is exactly `payload_repetitions`.** That is why repetitions is the only vote-count lever in the frozen grid, and why the sweep coupled it against the crop threshold `max(2, ceil(0.60 × payload_repetitions))` — the two are genuinely entangled, and no parameter in V3 separates them.

**Methodological lesson.** The error came from reading a parameter's name and its contract position instead of its use site. A field in a `fixed` block that looks like a capacity knob may be dead weight downstream. Before proposing any parameter as an optimisation lever, grep its use sites and confirm it reaches the computation you think it controls.

### Where the real headroom is

Two levers survive the refutation, both with measured evidence:

1. **`qim_delta`, with quantified quality headroom.** V3 freezes it at 32.0 and measures minimum PSNR 42.47 dB against a 38 dB gate — roughly 4.5 dB unspent. V2's contract already defines the next coupled step (`qim_delta` 48.0 with `pilot_strength_rms` 3.0). A stronger carrier should convert more of the three embedded tiles into ECC-valid votes, which is exactly the `valid_vote_count: 1` failure mode. This is the lever to test first.
2. **Content-aware tile selection.** Tile ordering is HMAC-shuffle plus crop-survival only; it never inspects whether a tile carries enough texture to hold a watermark. `embed_fingerprint_v3` already detects the problem after the fact, switching to spread embedding when a tile is saturated bright or dark. On a mixed-content fixture such as `pdf-multi-mixed`, blank-paper tiles can be selected as carriers. Selecting carriers by a deterministic texture criterion is an algorithm change, not a parameter change, and is the larger of the two options.

### REFUTED: `qim_delta` is not the lever either

The previous section proposed raising `qim_delta` from 32.0, citing ~4.5 dB of unspent PSNR headroom. V2's own completed sweep refutes it. V2 ran 1408 rows, `status: complete`, `execution_errors: 0`, across `qim_delta` 24 / 32 / 48 / 64 crossed with the same tile sizes and repetitions:

| `qim_delta` | best identity | best JPEG-70 | best resize | min PSNR at that delta |
|---:|---:|---:|---:|---:|
| 24.0 | 2/12 | 2/12 | 2/12 | 44.70 |
| 32.0 | 3/12 | 2/12 | 1/12 | 42.33 |
| 48.0 | 3/12 | 3/12 | 0/12 | 39.01 |
| 64.0 | 3/12 | 3/12 | 1/12 | 36.53 |

Raising delta buys almost nothing — the ceiling stays around 3/12 across a 2.7× range — while PSNR falls monotonically, and at 64.0 it reaches 36.53 dB, **below the 38 dB release gate**. Delta is a spent lever.

**What this reveals instead.** V2 at its best is 3/12; V3 at the same `qim_delta` of 32.0 reaches 9-10/12. Since delta is held equal, the V2→V3 gain is not a carrier-strength effect. The structural difference is that V3 adds spread spectrum (`spread_delta` 4.0, `spread_chips_per_bit` 64) and widens geometry search from V2's 3+1 hypotheses to 8. **Spread spectrum is the mechanism that produced the tripling**, and it is the component whose own parameters were never swept — they sit in V3's `fixed` block.

Note for the report: the "V3 raised `qim_delta`, which is why PSNR fell" narrative recorded earlier is wrong in its causal direction. V2 already used 32.0 among its coupled levels and measured 42.33 dB there — essentially V3's 42.47 dB. The PSNR difference between V1 (69 dB) and V3 (42 dB) is a V1→V2 change, not a V2→V3 one, and the robustness gain is attributable to spread spectrum rather than to the step size. Correct any slide that ties V3's robustness to its quantisation step.

### TESTED AND NEGATIVE: sweeping the spread parameters does not beat V3

The spread-spectrum hypothesis above was tested on 2026-09-11 and **did not hold**. Harness: `research/python/scripts/run_v4_experiment.py`, grid `contracts/algorithm/fingerprint-candidates.v4.json`, 4 variants × 12 positive pages × 4 attacks = 192 rows, all complete.

| variant | `spread_chips_per_bit` | `saturated_fraction_min` | identity | JPEG-70 | resize-0.75 | crop-0.25 | total | min PSNR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **V3 baseline** | 64 | 0.75 | 11/12 | **11/12** | **10/12** | 7/12 | **39/48** | 42.30 |
| V4 | 64 | 0.50 | 11/12 | 10/12 | 10/12 | **8/12** | **39/48** | 42.28 |
| V4 | 128 | 0.75 | 10/12 | 10/12 | 9/12 | 7/12 | 36/48 | 42.17 |
| V4 | 128 | 0.50 | 11/12 | 10/12 | 9/12 | **8/12** | 38/48 | 42.20 |

Doubling chips per bit from 64 to 128 is **strictly worse** (36 and 38 against 39). Lowering the saturation threshold to 0.50, which routes more tiles to the spread codec, is a **wash**: it gains one crop row and loses one JPEG row. V3's frozen values sit at a local optimum in this neighbourhood.

**The informative part is not the totals — it is that the failures move.** The baseline loses all four attacks on `pdf-multi-mixed/p0` while decoding `pdf-one-vector/p0` cleanly. At `saturated_fraction_min` 0.50 this inverts exactly: `pdf-multi-mixed/p0` is rescued on every attack and `pdf-one-vector/p0` fails on every attack. The failure count barely moves; **which document fails** changes completely.

That is the signature of a **carrier-placement problem, not a carrier-strength problem**. Every parameter tested here scales how strongly or how often the signal is written. None of them chooses *where* to write it with respect to page content, and tile ordering is HMAC-shuffle plus crop-survival only — content-blind by construction. A page whose selected carriers land on blank or flat regions fails regardless of chip count or saturation routing, and a different parameter simply relocates the problem to a different page.

**Conclusion for the roadmap.** Parameter tuning of the existing V3 design is exhausted: `qim_delta` (refuted by V2's 1408-row sweep), `tiles_per_page` (refuted by source inspection), and the spread parameters (refuted here by measurement). The remaining lever is deterministic **content-aware carrier selection** — scoring candidate tiles by texture or variance before choosing the `payload_repetitions` carriers, while keeping selection reproducible from the key. That is an algorithm change and the honest next step.

**Harness caveat.** These numbers come from `run_v4_experiment.py`, not the V3 pre-gate, and the two differ in attack RNG derivation and in passing the ORB sync template to the decoder. The baseline measures 11/12 on JPEG-70 here against the pre-gate's 10/12 for the same configuration. Only comparisons **within** this table are valid; never quote these figures as pre-gate evidence or mix them with Section 7.2 of the course report.

### RETRACTED: the "quorum of one would give 47/48" claim

An earlier analysis in this file reasoned that lowering the attribution quorum from two valid votes to one would convert the twelve `partial` rows into true attributions, yielding 47/48. **That figure was inferred, never measured, and the inference rests on two mistakes.**

**Mistake 1: `decoded_id` is empty on every `partial` row.** All twelve partial rows in `reports/fingerprint-pregate-v3/results.csv` record `decoded_id` as the empty string. The pre-gate never stores which identity a sub-quorum vote decoded to, so the data cannot show whether that single vote carried the correct issuance id. Without it, "these twelve would have attributed correctly" is unfalsifiable from the artifact.

**Mistake 2: `bit_error_rate: 0.0` does not mean the identity was right.** From `_decode_payload_vote`:

```python
payload = decode_ecc_with_erasures(evidence.codeword, evidence.erase_positions)
decoded = decode_payload(payload)
expected = encode_ecc(payload)          # re-encodes what ECC just decoded
ber = mismatch(evidence.codeword, expected)
```

`expected` is the re-encoding of the **decoded** payload, not of the true issuance. BER is therefore a **channel** measure — how many raw bits the ECC had to correct — and `0.0` means only that the codeword came off the page already valid. It carries no information about whether the recovered identity matches the issued one. Any reasoning that treats BER as identity-correctness is wrong.

**What survives.** A vote still requires ECC decode **and** `decode_payload`'s CRC-32 to pass, so a wrong-identity vote is roughly a 2⁻³² event per trial; and across 352 pre-gate rows the observed `false_attributions` is 0 with 40/40 negative fixtures producing zero votes. The quorum-of-one proposal remains **plausible and untested**, not established. To test it, the harness must record each vote's issuance id, which `DecodeV3Decision` does not expose — it returns `issuance_id = None` whenever it declines to attribute, which is also why scoring "quorum ≥ 1" from the decision object alone silently reproduces the quorum-2 numbers exactly.

**Methodological lesson.** Two different fields looked like they encoded "was the answer right" — `decoded_id` and `bit_error_rate` — and neither did. Before deriving a headline number from a column, read the code that writes it. A metric's name is a hypothesis about its meaning, not evidence of it.

### MEASURED: the full attack envelope, including screenshot (2026-09-11)

`research/python/scripts/run_v5_envelope.py`, 286 rows (156 positive, 130 negative), 0 execution errors, profile `tile_size_px` 512 / `payload_repetitions` 5. Thirteen attacks, of which nine had never been measured against V3 — the pre-gate only ever ran identity, JPEG 70, resize 0.75 and crop 0.25.

| Attack | Attribution | Note |
|---|---:|---|
| identity | 11/12 | |
| JPEG 85 | 11/12 | |
| JPEG 70 | 11/12 | |
| **JPEG 50** | **0/12** | `payload_not_detected` on all twelve |
| **crop 0.10** | **2/12** | worse than the harsher crop 0.25 — see below |
| crop 0.25 | 7/12 | |
| **crop 0.50** | **0/12** | |
| resize 0.75 | 10/12 | |
| resize 0.50 | 9/12 | |
| resize 1.50 | 11/12 | upscaling is nearly free |
| **screenshot 1920×1080** | **0/12** | 7 `payload_not_detected`, 5 `insufficient_sync_evidence` |
| **screenshot 1366×768** | **0/12** | `insufficient_sync_evidence` on all twelve |
| **screenshot + perspective** | **0/12** | `insufficient_sync_evidence` on all twelve |

False attributions on the 130 never-embedded negative rows: **0**, under both decision policies.

**The watermark does not survive a screenshot at all.** This is now measured rather than assumed, and it is the honest answer to "can it still be traced after a screenshot": no. The failure mode names the cause — at 1366×768 and under perspective the decoder reports `insufficient_sync_evidence`, meaning geometry search never recovered the page, so the payload layer was never reached. The screenshot attack fits a 1536×3072 page into a 1920×1080 screen, a scale of about 0.625, and letterboxes it on a dark background; the pilot does not survive that reduction. Note this is a harder operation than the resize 0.5 case that scores 9/12, because letterboxing changes the page's extent as well as its scale.

**The crop 0.10 anomaly.** A 10% crop scoring 2/12 while a 25% crop scores 7/12 is not physically sensible and should be treated as a defect signal, not a property of the algorithm. The most likely cause is the crop-survivor tile ordering, which is frozen around `crop_retained_scales = [0.866]`: carriers are prioritised to survive that specific retained scale, so a crop geometry the ordering was not tuned for can displace more carriers than a harsher one it was tuned for. This is a concrete, testable defect and is the single most promising lead in this table — it suggests the crop handling is over-fitted to one crop ratio.

**Scope.** These figures come from this harness, not the pre-gate; the two differ in attack RNG derivation and in supplying the ORB sync template to the decoder. Compare within this table only, and never mix these numbers with Section 7.2 of the course report.

### ROOT CAUSE: robustness is bounded by the geometry hypothesis set, not by the watermark

Reading `geometry_v3.search_geometry_v3`, the decoder proposes canonical candidates from exactly three sources:

1. `identity` — only when the attacked raster has the canonical shape exactly.
2. `pure_resize` — only when both axes scale by the same ratio, within `geometry_ratio_tolerance` (0.001).
3. `center_crop` — only for scales listed in `profile.crop_retained_scales`, which is frozen to the single value `0.8660254037844386`.

Anything outside those three produces **no geometric hypothesis at all**, so the payload layer is never reached regardless of how strong the carrier is. Mapping the measured envelope against which transforms generate a hypothesis gives a perfect correlation:

| Transform | Output shape | `ratios_agree` | Hypothesis | Measured |
|---|---|---|---|---:|
| crop 0.10 (side 0.9487) | 1457×2914 | yes | **none** — 0.9486 ≠ 0.8660 | 2/12 |
| crop 0.25 (side 0.8660) | 1330×2660 | yes | `center_crop` | **7/12** |
| crop 0.50 (side 0.7071) | 1086×2172 | yes | **none** | 0/12 |
| resize 0.75 / 0.50 / 1.50 | uniform | yes | `pure_resize` | 10, 9, 11 /12 |
| screenshot 1920×1080 | 1080×1920 | **no** | **none** | 0/12 |
| screenshot 1366×768 | 768×1366 | **no** | **none** | 0/12 |

Every attack that yields a hypothesis scores 7–11 of 12. Every attack that yields none scores 0–2 of 12. There is no counter-example in the table.

**Two consequences worth stating plainly.**

*The crop 0.25 result is over-fitted to the benchmark.* `crop_retained_scales = [sqrt(0.75)]` is precisely the side scale produced by `crop_fraction = 0.25`, the one crop the pre-gate measures. The decoder was hard-coded to invert exactly the attack it is scored on. That is why a *milder* 10% crop does worse than a harsher 25% one — a result that is physically nonsensical for a signal-strength story and entirely expected for a hypothesis-coverage story.

*Screenshot fails for an unrelated and more basic reason.* Letterboxing a 1536×3072 page onto a 1920×1080 screen gives ratios 0.703 and 0.625, which disagree, so neither `pure_resize` nor `center_crop` fires. The decoder reports `insufficient_sync_evidence` because it never formed a candidate at all. No amount of carrier tuning addresses this.

**This supersedes the carrier-placement conclusion recorded earlier.** Placement is a real secondary effect — it explains which pages fail *within* an attack the decoder can invert — but it is not why crop, JPEG-50 and screenshot fail wholesale. The binding constraint is hypothesis coverage, and it is the first thing any V4 must widen.

### CONFIRMED FIX: stripping the letterbox restores screenshot attribution (0/12 → 9/12)

The root-cause analysis above predicted that screenshot failure is hypothesis coverage, not carrier strength, and that removing the screen's uniform border would let the existing `pure_resize` hypothesis fire. `research/python/scripts/test_letterbox_hypothesis.py` tested it on the 12 positive pages:

| Screen | raw | after border strip |
|---|---:|---:|
| 1920×1080 | 0/12 | **9/12** |
| 1366×768 | 0/12 | 0/12 |

**9/12 is exactly the resize-0.50 rate**, which is what the prediction required: with the border gone, a screenshot *is* a uniform resize, and the decoder already handles those. The watermark, the ECC, the spread parameters and the tile placement were all unchanged — the fix is roughly twenty lines of deterministic preprocessing that finds the modal edge colour and trims rows and columns uniformly within tolerance of it.

**The two screen sizes fail for different reasons, and the strip separates them.**

- At 1920×1080 the page lands at scale 0.625 after stripping. Ratios agree, `pure_resize` fires, attribution recovers. This was **never a watermark problem**.
- At 1366×768 the stripped page lands at 683×1366, scale 0.4447. Ratios agree there too, and the status moves from `insufficient_sync_evidence` to `payload_not_detected` — geometry now succeeds and the *payload* is what dies. 0.4447 is below the resize-0.50 point that scores 9/12, so this is a genuine resolution limit of the carrier.

That status transition is the useful diagnostic: `insufficient_sync_evidence` means the decoder never formed a candidate and the failure is geometric; `payload_not_detected` means it aligned the page and the signal was gone. Read the status before theorising about either.

**Design consequence.** Any preprocessing that normalises an attacked raster toward the canonical framing — border trimming, and by extension deskew and page-boundary detection — buys more robustness per line of code than any carrier parameter tested in this file. The V3 decoder assumes its input is already framed like the issued page; real leak channels never are.

**Scope.** A throwaway probe on 12 pages, not the pre-gate, and the strip tolerance (12 levels) was not swept. Treat 9/12 as a demonstration that the mechanism is real, not as a release figure.

### REFINED: the complete cause table, and a correction about crops

Breaking the V5 envelope down by `decode_status` rather than by pass/fail sharpens the root-cause story and corrects one detail of it.

| Attack | Correct hypothesis available? | `decode_status` across 12 positive pages | Cause |
|---|---|---|---|
| identity, JPEG 85, JPEG 70 | yes (`identity`) | `decoded` 11, `partial` 1 | — |
| **JPEG 50** | yes (`identity`) | **`payload_not_detected` 12** | **carrier destroyed** |
| **crop 0.10** | no (0.949 ∉ {0.866}) | `partial` 5, `payload_not_detected` 5, `decoded` 2 | **wrong alignment** |
| crop 0.25 | **yes** (`center_crop` 0.866) | `decoded` 7, `partial` 5, **`payload_not_detected` 0** | — |
| **crop 0.50** | no (0.707) | **`payload_not_detected` 12** | **wrong alignment** |
| resize 0.75 / 0.50 / 1.50 | yes (`pure_resize`) | mostly `decoded` | — |
| screenshot 1366, perspective | no (ratios disagree) | **`insufficient_sync_evidence` 12** | **no candidate at all** |

**Correction.** An earlier section said crop 0.10 and crop 0.50 produce *no* geometric hypothesis. That is wrong. Both satisfy `ratios_agree` — a centred crop scales both axes identically — so the `pure_resize` branch fires and stretches the cropped region back to the full canvas. A candidate **is** formed; it is simply the wrong one, because a crop is not a resize. That is why these rows report `payload_not_detected` (aligned, signal absent at those coordinates) rather than `insufficient_sync_evidence` (never aligned). The distinction matters: the defect is not missing hypothesis *generation*, it is missing hypothesis *coverage* — the one correct candidate is absent while a plausible-looking wrong one crowds the slot.

**The sharpest single piece of evidence for the over-fitting claim** is that crop 0.25 is the only crop with **zero** `payload_not_detected` rows. Every page yields at least partial evidence there, and only there. That is exactly what "the correct hypothesis exists for this crop ratio and no other" predicts, and it is not explainable by signal strength, since crop 0.10 removes less of the page.

**Three distinct failure classes, not one.** Any V4 must treat them separately:

1. **No candidate formed** (`insufficient_sync_evidence`) — screenshot at 1366 and under perspective. Fixed by frame normalisation; demonstrated at 1920×1080, where stripping the letterbox took attribution from 0/12 to 9/12.
2. **Wrong candidate formed** (`payload_not_detected` with a shape change) — crop 0.10 and 0.50. Fixed by estimating the crop scale instead of enumerating one frozen value.
3. **Correct candidate, dead carrier** (`payload_not_detected` with no shape change) — JPEG 50, and the 1366 screenshot after stripping. This is the only class that is a genuine carrier limit, and the only one for which the refuted parameter levers were ever the right conversation.

Diagnose which class a failure belongs to from `decode_status` plus whether the raster changed shape, before proposing any remedy.
