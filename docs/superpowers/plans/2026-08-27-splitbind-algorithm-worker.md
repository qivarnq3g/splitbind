# SplitBind Algorithm and Rust Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a measured, versioned SplitBind watermark profile and a bounded Rust worker that issues and verifies synthetic PDF/ image inputs with cross-language parity, signed manifests, and cleanup on every terminal path.

**Architecture:** Contracts and a fixed synthetic corpus precede implementation. Python supplies the readable reference, attack simulator, and benchmark used to promote one candidate profile; Rust must reproduce checked-in vectors before becoming the production data plane. PDF, storage, metadata, and secret access are traits so the local executor can prove behavior before RabbitMQ, R2, PostgreSQL, and Azure Key Vault adapters are connected.

**Tech Stack:** Python 3.11+, NumPy, OpenCV, PyWavelets, SciPy, scikit-image, Pillow, Hypothesis, pytest, Rust stable, Tokio, Serde, OpenCV bindings, PDFium, printpdf, ed25519-dalek, SQLx, aws-sdk-s3, Reqwest

**Spec:** `docs/superpowers/specs/2026-08-13-splitbind-production-design.md`

## Global Constraints

- `issuance_id` is a random 128-bit UUID and is the only recipient-linked identifier carried by the public fingerprint.
- Candidate profiles are research artifacts. Only a profile that passes Gate G1 in the master plan may be copied to `contracts/algorithm/fingerprint-profile.v1.json`.
- Robust fingerprint and semi-fragile integrity keys are separate from the Ed25519 signing key.
- Canonical JSON follows RFC 8785 JSON Canonicalization Scheme (JCS); Ed25519 signs the exact canonical bytes.
- Internal manifests may contain protected `recipient_id`; externally shared evidence manifests must omit it.
- PDF processing is page-sequential. A worker never retains multiple decoded pages concurrently.
- Production job concurrency is `1`, timeout is 600 seconds, retry count is at most `2`, peak RSS is at most 1.5 GiB, and temporary disk is at most 2 GiB.
- Input limits are 10 MiB, 50 PDF pages, and 40 megapixels per decoded image.
- The worker rejects encrypted, structurally invalid, or non-renderable PDFs and never uses a user filename as a path component.
- Output is uploaded and re-read for SHA-256 verification before local deletion.
- All fixtures are synthetic and their generator, license statement, seed, and SHA-256 are versioned.
- Queue `schema_version` is the JSON integer `1`; `v1` is only a filename/exchange suffix.

---

## File Structure Lock-In

```text
contracts/
  algorithm/
    payload-profile.v1.json
    fingerprint-candidates.v1.json
    fingerprint-profile.v1.json          created only by profile promotion
    integrity-profile.v1.json
    attack-matrix.v1.json
  jsonschema/
    algorithm-vector-v1.schema.json
    internal-manifest-v1.schema.json
    public-manifest-v1.schema.json
    evidence-v1.schema.json
    job-metrics-v1.schema.json
    job-request-v1.schema.json
    job-result-v1.schema.json
fixtures/
  corpus/
    README.md
    corpus-manifest.v1.json
    generated/
  vectors/v1/
  messages/
    issuance-request-v1.json
    verification-request-v1.json
research/python/
  pyproject.toml
  src/splitbind_ref/
  src/splitbind_attack/
  src/splitbind_bench/
  scripts/
  tests/
services/worker/
  Cargo.toml
  crates/core/
  crates/pdf/
  crates/runtime/
  crates/worker/
```

## Stable Interfaces

```python
@dataclass(frozen=True)
class DecodeDecision:
    issuance_id: UUID | None
    confidence: float
    valid_votes: int
    bit_error_rate: float | None
    reason: Literal["decoded", "partial", "not_detected", "invalid_crc"]

@dataclass(frozen=True)
class IntegrityDecision:
    score: float
    suspicious_regions: tuple[NormalizedRect, ...]
    evaluated_regions: int
    limitations: tuple[str, ...]
```

```rust
pub trait ObjectStore: Send + Sync {
    async fn download_to(&self, key: &ObjectKey, target: &Path) -> Result<ObjectMeta, StoreError>;
    async fn upload_from(&self, key: &ObjectKey, source: &Path) -> Result<ObjectMeta, StoreError>;
    async fn head(&self, key: &ObjectKey) -> Result<ObjectMeta, StoreError>;
}

pub trait MetadataRepository: Send + Sync {
    async fn lookup_manifest(&self, issuance_id: Uuid) -> Result<Option<SignedManifest>, RepoError>;
    async fn cancellation_requested(&self, job_id: Uuid) -> Result<bool, RepoError>;
}

pub trait SecretProvider: Send + Sync {
    async fn signing_key(&self, key_id: &str) -> Result<Zeroizing<Vec<u8>>, SecretError>;
    async fn fingerprint_key(&self, key_id: &str) -> Result<Zeroizing<Vec<u8>>, SecretError>;
    async fn integrity_key(&self, key_id: &str) -> Result<Zeroizing<Vec<u8>>, SecretError>;
}
```

### Task A1: Freeze schemas, synthetic corpus, and acceptance matrix

**Owner:** Leader; member reviews fixtures and attack coverage.

**Files:**

- Create: `contracts/algorithm/payload-profile.v1.json`
- Create: `contracts/algorithm/fingerprint-candidates.v1.json`
- Create: `contracts/algorithm/integrity-profile.v1.json`
- Create: `contracts/algorithm/attack-matrix.v1.json`
- Create: `contracts/jsonschema/algorithm-vector-v1.schema.json`
- Create: `contracts/jsonschema/internal-manifest-v1.schema.json`
- Create: `contracts/jsonschema/public-manifest-v1.schema.json`
- Create: `contracts/jsonschema/evidence-v1.schema.json`
- Create: `contracts/jsonschema/job-metrics-v1.schema.json`
- Create: `contracts/jsonschema/job-request-v1.schema.json`
- Create: `contracts/jsonschema/job-result-v1.schema.json`
- Create: `fixtures/corpus/README.md`
- Create: `fixtures/corpus/corpus-manifest.v1.json`
- Create: `fixtures/messages/issuance-request-v1.json`
- Create: `fixtures/messages/verification-request-v1.json`
- Create: `research/python/scripts/generate_corpus.py`
- Test: `research/python/tests/contracts/test_contracts.py`
- Test: `research/python/tests/contracts/test_corpus.py`

**Interfaces:**

- Produces payload bytes: `b"SB" + schema_version:u8 + issuance_uuid:16 + crc32:4`.
- Produces shortened Reed–Solomon configuration: GF(256), primitive polynomial `0x11d`, `16` parity symbols, interleave depth `8`.
- Produces deterministic corpus entries with `fixture_id`, generator seed, pages, dimensions, SHA-256, and license.
- Produces the complete attack matrix from the specification, including exact parameter arrays.
- Produces the shared `JobRequestV1`, `JobResultV1`, `EvidenceV1`, and `JobMetricsV1` schemas named in the master plan; every schema sets `additionalProperties: false`.
- Produces two synthetic request fixtures consumed unchanged by Django, Rust, and integration tests.
- `InternalManifestV1` requires `schema_version`, `issuance_id`, `document_id`, `recipient_id`, `issued_at`, `source_sha256`, `output_sha256`, `fingerprint_algorithm`, `integrity_algorithm`, `signing_key_id`, and `retention_policy_id`.
- `PublicManifestV1` requires `schema_version`, `issuance_id`, `issued_at`, `output_sha256`, `fingerprint_algorithm`, `integrity_algorithm`, and `signing_key_id`; it forbids `document_id`, `recipient_id`, private object keys, and personal data. Internal and public canonical bytes receive separate Ed25519 signatures so the public projection remains independently verifiable.

- [ ] **Step 1: Write failing schema and corpus tests**

```python
def test_attack_matrix_has_every_required_level(load_json):
    matrix = load_json("contracts/algorithm/attack-matrix.v1.json")
    assert matrix["jpeg_quality"] == [95, 85, 70, 50]
    assert matrix["crop_fraction"] == [0.10, 0.25, 0.50]
    assert matrix["resize_scale"] == [0.50, 0.75, 1.50]
    assert matrix["rotation_degrees"] == [-5, -3, -1, 1, 3, 5]
    assert len(matrix["brightness_contrast"]) == 3
    assert len(matrix["gaussian_noise_blur"]) == 3
    assert len(matrix["screenshot"]) == 3
    assert {case["kind"] for case in matrix["tamper"]} == {
        "replace_text", "cover_region", "copy_move", "insert_object"
    }

def test_corpus_contains_clean_and_negative_documents(load_json):
    corpus = load_json("fixtures/corpus/corpus-manifest.v1.json")
    kinds = {entry["kind"] for entry in corpus["entries"]}
    assert {"clean_pdf", "clean_image", "negative_external", "tamper_ground_truth"} <= kinds

def test_job_contracts_freeze_fields_and_forbid_extras(load_json):
    request = load_json("contracts/jsonschema/job-request-v1.schema.json")
    result = load_json("contracts/jsonschema/job-result-v1.schema.json")
    assert request["additionalProperties"] is False
    assert result["additionalProperties"] is False
    assert set(request["required"]) == {
        "schema_version", "message_type", "message_id", "job_id", "attempt",
        "issuance_id", "verification_id", "input_object_key", "input_sha256",
        "deadline_at", "correlation_id",
    }
    assert "$ref" in result["properties"]["metrics"]
```

- [ ] **Step 2: Run tests and observe missing-file failures**

Run: `python -m pytest research/python/tests/contracts -v`

Expected: FAIL with `FileNotFoundError` for contract and corpus files.

- [ ] **Step 3: Add explicit candidate grid and corpus generator**

Use this research grid in `fingerprint-candidates.v1.json`; it is not a release claim:

```json
{
  "schema_version": 1,
  "fixed": {
    "wavelet": "haar",
    "wavelet_level": 1,
    "dct_block_size": 8,
    "midband_pairs": [[[1, 2], [2, 1]], [[2, 3], [3, 2]]],
    "ecc_parity_symbols": 16,
    "interleave_depth": 8,
    "sync_detector": "orb-ransac"
  },
  "sweep": {
    "qim_delta": [6.0, 8.0, 10.0, 12.0],
    "tile_size_px": [256, 384],
    "tiles_per_page": [12, 18, 24],
    "payload_repetitions": [3, 5]
  }
}
```

Generate at least three one-page and two multi-page PDFs using vector text, grayscale shapes, photographs from generated noise/gradients, whitespace, and mixed contrast; generate at least ten unwatermarked negative images with independent seeds.

Define `JobMetricsV1` with the five non-negative integer fields `processing_ms`, `pages_processed`, `peak_rss_bytes`, `temp_peak_bytes`, and `cleanup_failures`. Define the request/result/evidence fields exactly as the master plan's Cross-Track Contracts section and validate both files in `fixtures/messages/` with `jsonschema` in `test_contracts.py`.

- [ ] **Step 4: Validate schemas, hashes, determinism, and Git boundaries**

Run: `python research/python/scripts/generate_corpus.py --seed 20260827 --output fixtures/corpus/generated`

Run: `python -m pytest research/python/tests/contracts -v`

Expected: PASS; a second generation produces identical SHA-256 values; no file exceeds the fixture size documented in `README.md`.

- [ ] **Step 5: Commit the contracts and reproducible fixtures**

```bash
git add contracts fixtures/corpus research/python/scripts/generate_corpus.py research/python/tests/contracts
git commit -m "spec: freeze algorithm contracts and acceptance corpus"
```

### Task A2: Implement payload, CRC, Reed–Solomon, interleave, and keyed tile layout

**Owner:** Leader.

**Files:**

- Create: `research/python/pyproject.toml`
- Create: `research/python/src/splitbind_ref/contracts.py`
- Create: `research/python/src/splitbind_ref/payload.py`
- Create: `research/python/src/splitbind_ref/ecc.py`
- Create: `research/python/src/splitbind_ref/tile_layout.py`
- Test: `research/python/tests/reference/test_payload.py`
- Test: `research/python/tests/reference/test_ecc.py`
- Test: `research/python/tests/reference/test_tile_layout.py`

**Interfaces:**

- `encode_payload(issuance_id: UUID, version: int = 1) -> bytes`
- `decode_payload(encoded: bytes) -> PayloadDecode`
- `encode_ecc(payload: bytes, parity_symbols: int = 16) -> bytes`
- `decode_ecc(codeword: bytes, parity_symbols: int = 16) -> bytes`
- `derive_tiles(page_shape, key, document_nonce, page_index, profile) -> tuple[Tile, ...]`

- [ ] **Step 1: Write failing golden and corruption tests**

```python
def test_payload_has_stable_network_byte_order():
    value = encode_payload(UUID("12345678-1234-5678-1234-567812345678"), 1)
    assert value[:19].hex() == "53420112345678123456781234567812345678"
    assert len(value) == 23

@given(st.binary(min_size=23, max_size=23), st.integers(min_value=0, max_value=8))
def test_shortened_rs_corrects_up_to_eight_symbol_errors(payload, count):
    codeword = bytearray(encode_ecc(payload, parity_symbols=16))
    for index in range(count):
        codeword[index] ^= 0x5A
    assert decode_ecc(bytes(codeword), parity_symbols=16) == payload
```

- [ ] **Step 2: Run targeted tests and observe import failures**

Run: `python -m pytest research/python/tests/reference/test_payload.py research/python/tests/reference/test_ecc.py research/python/tests/reference/test_tile_layout.py -v`

Expected: FAIL with missing `splitbind_ref` modules.

- [ ] **Step 3: Implement the exact binary contract**

```python
def encode_payload(issuance_id: UUID, version: int = 1) -> bytes:
    body = b"SB" + version.to_bytes(1, "big") + issuance_id.bytes
    checksum = zlib.crc32(body).to_bytes(4, "big")
    return body + checksum

def verify_crc(payload: bytes) -> bool:
    return len(payload) == 23 and zlib.crc32(payload[:19]).to_bytes(4, "big") == payload[19:]
```

Derive the CSPRNG seed as `HMAC-SHA256(fingerprint_key, document_nonce || page_index_be32 || profile_version)` and sample non-overlapping tile origins inside page bounds.

- [ ] **Step 4: Run unit and property tests**

Run: `python -m pytest research/python/tests/reference/test_payload.py research/python/tests/reference/test_ecc.py research/python/tests/reference/test_tile_layout.py -v`

Expected: PASS; wrong key, nonce, or page index produces a different layout; identical inputs reproduce the layout.

- [ ] **Step 5: Commit**

```bash
git add research/python
git commit -m "feat(research): add payload ecc and keyed tile layout"
```

### Task A3: Implement robust DWT–DCT–QIM fingerprint candidates

**Owner:** Leader; member reviews visible distortion cases.

**Files:**

- Create: `research/python/src/splitbind_ref/dwt_dct_qim.py`
- Create: `research/python/src/splitbind_ref/synchronization.py`
- Create: `research/python/src/splitbind_ref/fingerprint.py`
- Test: `research/python/tests/reference/test_qim.py`
- Test: `research/python/tests/reference/test_fingerprint_roundtrip.py`
- Test: `research/python/tests/reference/test_geometric_alignment.py`

**Interfaces:**

- `embed_fingerprint(page_bgr, context, profile) -> EmbeddedPage`
- `decode_fingerprint(page_bgr, key, profiles) -> DecodeDecision`
- `align_page(page_bgr, sync_template) -> AlignmentResult`
- `soft_vote(votes, threshold) -> DecodeDecision`

- [ ] **Step 1: Write failing round-trip and wrong-key tests**

```python
def test_clean_roundtrip_recovers_issuance_id(sample_page, embed_context, candidate_profile):
    embedded = embed_fingerprint(sample_page, embed_context, candidate_profile)
    decoded = decode_fingerprint(
        embedded.image, embed_context.fingerprint_key, (candidate_profile,)
    )
    assert decoded.issuance_id == embed_context.issuance_id
    assert decoded.reason == "decoded"

def test_wrong_key_never_attributes(sample_page, embed_context, candidate_profile):
    embedded = embed_fingerprint(sample_page, embed_context, candidate_profile)
    decoded = decode_fingerprint(embedded.image, b"w" * 32, (candidate_profile,))
    assert decoded.issuance_id is None
```

- [ ] **Step 2: Run tests and confirm missing-symbol failures**

Run: `python -m pytest research/python/tests/reference/test_qim.py research/python/tests/reference/test_fingerprint_roundtrip.py research/python/tests/reference/test_geometric_alignment.py -v`

Expected: FAIL because QIM, synchronization, and voting functions do not exist.

- [ ] **Step 3: Implement the reference pipeline**

For each selected tile: convert to luminance, perform one-level Haar DWT, split the selected detail band into 8×8 blocks, apply DCT, encode each bit by quantizing the difference of the configured coefficient pair to an even or odd lattice, invert DCT/DWT, clip to the original bit depth, and preserve chroma. Add an orientation/synchronization template; during decode use ORB keypoints, descriptor matching, and RANSAC homography before extracting repeated codewords.

```python
def qim_embed_pair(a: float, b: float, bit: int, delta: float) -> tuple[float, float]:
    difference = a - b
    lattice = round(difference / delta)
    target = lattice if lattice % 2 == bit else lattice + 1
    correction = (target * delta - difference) / 2.0
    return a + correction, b - correction
```

- [ ] **Step 4: Run reference tests for every candidate combination**

Run: `python -m pytest research/python/tests/reference/test_qim.py research/python/tests/reference/test_fingerprint_roundtrip.py research/python/tests/reference/test_geometric_alignment.py -v`

Expected: PASS for clean round trip; wrong key and corrupted CRC never return a non-null attribution.

- [ ] **Step 5: Commit**

```bash
git add research/python
git commit -m "feat(research): add robust fingerprint reference"
```

### Task A4: Implement attack simulator and truthful benchmark metrics

**Owner:** Member; leader reviews metric definitions and seeds.

**Files:**

- Create: `research/python/src/splitbind_attack/attacks.py`
- Create: `research/python/src/splitbind_attack/ground_truth.py`
- Create: `research/python/src/splitbind_bench/metrics.py`
- Create: `research/python/src/splitbind_bench/runner.py`
- Create: `research/python/scripts/run_benchmark.py`
- Test: `research/python/tests/attack/test_attacks.py`
- Test: `research/python/tests/bench/test_metrics.py`
- Test: `research/python/tests/bench/test_reproducibility.py`

**Interfaces:**

- `apply_attack(image, AttackCase, rng) -> AttackedArtifact`
- `compute_detection_metrics(rows) -> DetectionMetrics`
- `compute_quality_metrics(original, watermarked) -> QualityMetrics`
- `run_matrix(corpus, profiles, matrix, seed, output_dir) -> BenchmarkSummary`

- [ ] **Step 1: Write failing metric truth-table tests**

```python
def test_false_attribution_is_counted_separately():
    rows = [
        Result(expected="a", decoded="a"),
        Result(expected="a", decoded=None),
        Result(expected="a", decoded="b"),
        Result(expected=None, decoded="c"),
    ]
    metrics = compute_detection_metrics(rows)
    assert metrics.true_attribution == 1
    assert metrics.missed_detection == 1
    assert metrics.false_attribution == 2

def test_identical_images_have_perfect_quality(sample_page):
    quality = compute_quality_metrics(sample_page, sample_page)
    assert math.isinf(quality.psnr_db)
    assert quality.ssim == 1.0
```

- [ ] **Step 2: Run tests and observe missing implementations**

Run: `python -m pytest research/python/tests/attack research/python/tests/bench -v`

Expected: FAIL with missing attack and metric modules.

- [ ] **Step 3: Implement every specified transformation with deterministic seeds**

The screenshot cases must include two explicit raster resolutions and one four-point perspective warp. Tamper cases must emit normalized ground-truth rectangles. Combined cases must preserve their ordered operations in the report. Each output row records corpus checksum, algorithm profile hash, attack parameters, seed, decoded ID, confidence, BER, PSNR, SSIM, localization IoU where applicable, elapsed milliseconds, peak RSS, and temporary disk peak.

```python
def apply_attack(image: np.ndarray, case: AttackCase, rng: np.random.Generator) -> AttackedArtifact:
    handlers = {
        "jpeg": jpeg_roundtrip,
        "crop": crop_fraction,
        "resize": resize_scale,
        "rotation": rotate_degrees,
        "brightness_contrast": adjust_brightness_contrast,
        "noise_blur": add_noise_then_blur,
        "screenshot": simulate_screenshot,
        "tamper": apply_tamper_with_ground_truth,
    }
    if case.kind == "combined":
        artifact = AttackedArtifact(image=image, ground_truth=())
        for operation in case.operations:
            artifact = apply_attack(artifact.image, operation, rng)
        return artifact
    return handlers[case.kind](image, case.parameters, rng)


def compute_detection_metrics(rows: list[Result]) -> DetectionMetrics:
    true_attribution = sum(row.expected is not None and row.decoded == row.expected for row in rows)
    missed_detection = sum(row.expected is not None and row.decoded is None for row in rows)
    false_attribution = sum(row.decoded is not None and row.decoded != row.expected for row in rows)
    return DetectionMetrics(true_attribution, missed_detection, false_attribution)
```

- [ ] **Step 4: Run the smoke matrix twice and compare reports**

Run: `python research/python/scripts/run_benchmark.py --profiles contracts/algorithm/fingerprint-candidates.v1.json --corpus fixtures/corpus/corpus-manifest.v1.json --matrix contracts/algorithm/attack-matrix.v1.json --seed 20260827 --smoke --output reports/benchmark-smoke-a`

Run the same command with output `reports/benchmark-smoke-b`.

Expected: normalized CSV/JSON rows are identical except explicitly excluded wall-clock and host-inventory fields.

- [ ] **Step 5: Commit simulator code, not generated reports**

```bash
git add research/python
git commit -m "feat(research): add reproducible attack benchmark harness"
```

### Task A5: Benchmark and promote the fingerprint profile

**Owner:** Leader and member jointly; leader approves promotion.

**Files:**

- Create: `research/python/src/splitbind_bench/promotion.py`
- Create: `research/python/scripts/promote_profile.py`
- Create: `docs/evaluation/fingerprint-profile-v1.md`
- Create on success: `contracts/algorithm/fingerprint-profile.v1.json`
- Test: `research/python/tests/bench/test_promotion.py`

**Interfaces:**

- `eligible_profiles(summary) -> tuple[ProfileScore, ...]`
- `promote_profile(summary, candidates, destination) -> ReleasedProfile`

- [ ] **Step 1: Write failing promotion-gate tests**

```python
def test_profile_with_false_attribution_is_ineligible(summary_factory):
    summary = summary_factory(false_attribution=1, jpeg70_rate=1.0, resize075_rate=1.0)
    assert eligible_profiles(summary) == ()

def test_best_eligible_profile_prefers_quality_then_speed(summary_factory):
    summary = summary_factory(
        profiles=[
            profile("a", ssim=0.961, psnr=39.0, milliseconds=400),
            profile("b", ssim=0.970, psnr=39.2, milliseconds=500),
        ]
    )
    assert eligible_profiles(summary)[0].profile_id == "b"
```

- [ ] **Step 2: Run tests and confirm the promotion code is absent**

Run: `python -m pytest research/python/tests/bench/test_promotion.py -v`

Expected: FAIL with missing promotion module.

- [ ] **Step 3: Implement the exact release predicate**

A profile is eligible only when false attribution is zero, JPEG-70 and resize-0.75 decode rates are each at least 0.95, crop-0.25 decode rate is at least 0.90 for eligible remaining-tile cases, mean PSNR is at least 38 dB, and mean SSIM is at least 0.95. Sort eligible candidates by highest mean SSIM, then highest worst-case required decode rate, then lowest processing time. If no profile is eligible, exit nonzero and retain all measured failures in the evaluation document.

```python
def eligible_profiles(summary: BenchmarkSummary) -> tuple[ProfileScore, ...]:
    eligible = [
        score for score in summary.profiles
        if score.false_attribution == 0
        and score.jpeg70_rate >= 0.95
        and score.resize075_rate >= 0.95
        and score.crop025_rate >= 0.90
        and score.mean_psnr_db >= 38.0
        and score.mean_ssim >= 0.95
    ]
    eligible.sort(
        key=lambda score: (
            -score.mean_ssim,
            -min(score.jpeg70_rate, score.resize075_rate, score.crop025_rate),
            score.processing_ms_per_page,
        )
    )
    return tuple(eligible)
```

- [ ] **Step 4: Run the versioned baseline and promote only an eligible profile**

Run: `python research/python/scripts/run_benchmark.py --profiles contracts/algorithm/fingerprint-candidates.v1.json --corpus fixtures/corpus/corpus-manifest.v1.json --matrix contracts/algorithm/attack-matrix.v1.json --seed 20260827 --output reports/fingerprint-baseline-v1`

Run: `python research/python/scripts/promote_profile.py --summary reports/fingerprint-baseline-v1/summary.json --candidates contracts/algorithm/fingerprint-candidates.v1.json --output contracts/algorithm/fingerprint-profile.v1.json --report docs/evaluation/fingerprint-profile-v1.md`

Expected: either a released profile and exit `0`, or no release file and an explicit nonzero result. Do not proceed to Task A7 without a released profile.

- [ ] **Step 5: Commit the released profile and factual report**

```bash
git add contracts/algorithm/fingerprint-profile.v1.json docs/evaluation/fingerprint-profile-v1.md
git commit -m "research: release measured fingerprint profile v1"
```

### Task A6: Implement semi-fragile integrity watermark and signed manifests

**Owner:** Leader; member supplies tamper ground truth and reviews maps.

**Files:**

- Create: `research/python/src/splitbind_ref/integrity.py`
- Create: `research/python/src/splitbind_ref/manifest.py`
- Create: `research/python/tests/reference/test_integrity.py`
- Create: `research/python/tests/reference/test_manifest.py`
- Modify: `contracts/algorithm/integrity-profile.v1.json`
- Modify: `contracts/jsonschema/internal-manifest-v1.schema.json`
- Modify: `contracts/jsonschema/public-manifest-v1.schema.json`

**Interfaces:**

- `embed_integrity(page, key, nonce, profile) -> EmbeddedIntegrityPage`
- `verify_integrity(page, key, nonce, profile) -> IntegrityDecision`
- `canonicalize_manifest(manifest) -> bytes`
- `sign_manifest(canonical, private_key) -> SignatureEnvelope`
- `public_manifest(internal) -> PublicManifestV1`
- `signed_manifest_pair(internal, private_key) -> SignedManifestPair`

- [ ] **Step 1: Write failing tamper, benign-transform, and privacy tests**

```python
def test_tamper_marks_the_ground_truth_region(watermarked_page, tamper_case, integrity_context):
    attacked = tamper_case.apply(watermarked_page)
    result = verify_integrity(attacked, **integrity_context)
    assert iou(result.suspicious_regions, tamper_case.ground_truth) >= 0.50

def test_public_manifest_omits_recipient(internal_manifest):
    external = public_manifest(internal_manifest)
    assert "recipient_id" not in external.model_dump()

def test_public_canonical_signature_verifies_in_independent_library(internal_manifest, signing_key):
    external = public_manifest(internal_manifest)
    canonical = canonicalize_manifest(external)
    signature = sign_manifest(canonical, signing_key)
    VerifyKey(bytes(signing_key.verify_key)).verify(canonical, signature.signature)
```

- [ ] **Step 2: Run tests and observe missing modules**

Run: `python -m pytest research/python/tests/reference/test_integrity.py research/python/tests/reference/test_manifest.py -v`

Expected: FAIL with missing integrity and manifest functions.

- [ ] **Step 3: Implement deterministic partner-region authentication**

Partition each page into 128×128 regions. Quantize low-frequency DCT content features; compute `HMAC-SHA256(integrity_key, feature || region_index_be32 || document_nonce)`, truncate to 32 bits, and embed the tag into a key-derived partner region rather than the authenticated region itself. Exclude the destination coefficients from feature extraction to prevent circular verification. Report normalized rectangles and stable limitation identifiers for strong compression, geometry failure, or insufficient regions.

Use RFC 8785 JCS for canonicalization and Ed25519 for signatures. Store `key_id`, never a private key, in the manifest.

```python
def region_tag(feature: bytes, region_index: int, nonce: bytes, key: bytes) -> bytes:
    message = feature + region_index.to_bytes(4, "big") + nonce
    return hmac.new(key, message, hashlib.sha256).digest()[:4]


def public_manifest(internal: InternalManifestV1) -> PublicManifestV1:
    return PublicManifestV1(
        schema_version=internal.schema_version,
        issuance_id=internal.issuance_id,
        issued_at=internal.issued_at,
        output_sha256=internal.output_sha256,
        fingerprint_algorithm=internal.fingerprint_algorithm,
        integrity_algorithm=internal.integrity_algorithm,
        signing_key_id=internal.signing_key_id,
    )


def sign_manifest(canonical: bytes, private_key: SigningKey) -> SignatureEnvelope:
    return SignatureEnvelope(algorithm="Ed25519", key_id=private_key.key_id, signature=private_key.sign(canonical))


def signed_manifest_pair(internal: InternalManifestV1, private_key: SigningKey) -> SignedManifestPair:
    external = public_manifest(internal)
    internal_bytes = canonicalize_manifest(internal)
    public_bytes = canonicalize_manifest(external)
    return SignedManifestPair(
        internal=SignedManifest(internal, sign_manifest(internal_bytes, private_key)),
        public=SignedManifest(external, sign_manifest(public_bytes, private_key)),
    )
```

- [ ] **Step 4: Run integrity and manifest tests plus tamper subset**

Run: `python -m pytest research/python/tests/reference/test_integrity.py research/python/tests/reference/test_manifest.py -v`

Run: `python research/python/scripts/run_benchmark.py --profile contracts/algorithm/fingerprint-profile.v1.json --integrity-profile contracts/algorithm/integrity-profile.v1.json --tamper-only --output reports/integrity-baseline-v1`

Expected: unit tests PASS; localization is reported honestly even when below the research target and does not block fingerprint MVP release.

- [ ] **Step 5: Commit**

```bash
git add contracts research/python docs/evaluation
git commit -m "feat(research): add integrity watermark and signed manifest reference"
```

### Task A7: Generate shared vectors and port the released core to Rust

**Owner:** Leader; member reviews regeneration determinism.

**Files:**

- Create: `research/python/scripts/generate_vectors.py`
- Create: `fixtures/vectors/v1/README.md`
- Generate: `fixtures/vectors/v1/*.json`
- Create: `services/worker/Cargo.toml`
- Create: `services/worker/crates/core/Cargo.toml`
- Create: `services/worker/crates/core/src/{lib,contracts,payload,ecc,tile_layout,fingerprint,integrity,manifest}.rs`
- Test: `services/worker/crates/core/tests/{payload,ecc,layout,fingerprint,integrity,manifest}_vectors.rs`

**Interfaces:**

- `generate_vectors(profile_hash: str, seed: int, output: Path) -> None`
- Rust functions mirror the Python interfaces and consume the same profile JSON.

- [ ] **Step 1: Write a failing Rust golden-vector test**

```rust
#[test]
fn payload_vectors_match_python_reference() {
    for case in fixtures::payload_cases() {
        let actual = payload::encode(case.issuance_id, case.version);
        assert_eq!(hex::encode(actual), case.expected_hex);
    }
}
```

- [ ] **Step 2: Generate vectors and observe the missing Rust workspace failure**

Run: `python research/python/scripts/generate_vectors.py --profile contracts/algorithm/fingerprint-profile.v1.json --seed 20260827 --output fixtures/vectors/v1`

Run: `cargo test --manifest-path services/worker/Cargo.toml -p splitbind-core`

Expected: FAIL because the Rust workspace/core crate does not exist.

- [ ] **Step 3: Implement Rust parity without changing vectors**

Implement binary payload, CRC, shortened RS, HMAC tile derivation, QIM coefficient rules, integrity tag mapping, JCS canonicalization, and Ed25519 verification exactly as recorded. Treat any desire to edit a vector as a Python/Rust discrepancy requiring diagnosis; regenerate only through the checked-in generator after an approved profile-version change.

```rust
pub fn encode(issuance_id: Uuid, version: u8) -> Vec<u8> {
    let mut body = Vec::with_capacity(23);
    body.extend_from_slice(b"SB");
    body.push(version);
    body.extend_from_slice(issuance_id.as_bytes());
    let checksum = crc32fast::hash(&body).to_be_bytes();
    body.extend_from_slice(&checksum);
    body
}

pub fn canonical_manifest(value: &InternalManifestV1) -> Result<Vec<u8>, ManifestError> {
    serde_json_canonicalizer::to_vec(value).map_err(ManifestError::Canonicalization)
}
```

- [ ] **Step 4: Run both language suites and verify regeneration is clean**

Run: `python -m pytest research/python/tests -v`

Run: `cargo test --manifest-path services/worker/Cargo.toml -p splitbind-core`

Run the generator again, then: `git diff --exit-code fixtures/vectors/v1`

Expected: PASS and no vector drift.

- [ ] **Step 5: Commit**

```bash
git add services/worker fixtures/vectors research/python/scripts/generate_vectors.py
git commit -m "feat(worker): port released watermark profile to rust"
```

### Task A8: Implement safe PDF/image validation, page pipeline, and image-based PDF output

**Owner:** Leader.

**Files:**

- Create: `services/worker/crates/pdf/Cargo.toml`
- Create: `services/worker/crates/pdf/src/{lib,detect,render,assemble,limits}.rs`
- Test: `services/worker/crates/pdf/tests/{validation,rendering,limits,assembly}.rs`
- Create: `fixtures/corpus/generated/encrypted.pdf`
- Create: `fixtures/corpus/generated/fake-extension.pdf`

**Interfaces:**

- `inspect_input(path, limits) -> InputDescriptor`
- `render_pages(path, limits, on_page) -> ProcessingSummary`
- `assemble_image_pdf(pages, metadata, output) -> OutputDescriptor`

- [ ] **Step 1: Write failing malicious/limit/input tests**

```rust
#[test]
fn rejects_pdf_extension_with_non_pdf_content() {
    let error = inspect_input(fixture("fake-extension.pdf"), Limits::test()).unwrap_err();
    assert_eq!(error.code(), "UNSUPPORTED_CONTENT");
}

#[test]
fn rejects_encrypted_pdf_before_job_processing() {
    let error = inspect_input(fixture("encrypted.pdf"), Limits::test()).unwrap_err();
    assert_eq!(error.code(), "ENCRYPTED_PDF");
}
```

- [ ] **Step 2: Run tests and observe missing-crate failures**

Run: `cargo test --manifest-path services/worker/Cargo.toml -p splitbind-pdf`

Expected: FAIL because `splitbind-pdf` does not exist.

- [ ] **Step 3: Implement content inspection and sequential rendering**

Check magic bytes and parse structure rather than trusting extension/MIME. Use a pinned PDFium library behind `PdfEngine`; reject encryption and page count above 50 before rendering. Before allocating a page buffer, multiply width × height with checked arithmetic and reject above 40,000,000 pixels. Invoke the page callback and release the buffer before rendering the next page. Assemble an image-based PDF with stable page dimensions and no source scripts, attachments, or active content.

```rust
fn checked_pixels(width: u32, height: u32, limits: Limits) -> Result<u64, PdfError> {
    let pixels = u64::from(width)
        .checked_mul(u64::from(height))
        .ok_or_else(|| PdfError::safe("PIXEL_OVERFLOW"))?;
    if pixels > limits.max_pixels { return Err(PdfError::safe("IMAGE_TOO_LARGE")); }
    Ok(pixels)
}

pub fn render_pages<E, F>(engine: &E, path: &Path, limits: Limits, mut on_page: F) -> Result<ProcessingSummary, PdfError>
where
    E: PdfEngine,
    F: FnMut(PageFrame) -> Result<(), PdfError>,
{
    let document = engine.open(path)?;
    if document.is_encrypted() { return Err(PdfError::safe("ENCRYPTED_PDF")); }
    if document.page_count() > limits.max_pages { return Err(PdfError::safe("TOO_MANY_PAGES")); }
    for page_index in 0..document.page_count() {
        let frame = document.render_page(page_index, limits)?;
        checked_pixels(frame.width(), frame.height(), limits)?;
        on_page(frame)?;
    }
    Ok(ProcessingSummary { pages: document.page_count() })
}
```

- [ ] **Step 4: Run tests and a memory smoke case**

Run: `cargo test --manifest-path services/worker/Cargo.toml -p splitbind-pdf`

Run: `cargo run --manifest-path services/worker/Cargo.toml -p splitbind-worker -- inspect fixtures/corpus/generated/sample-multipage.pdf`

Expected: PASS; descriptor reports the exact page count; encrypted/fake/oversized cases use stable safe error codes.

- [ ] **Step 5: Commit**

```bash
git add services/worker/crates/pdf fixtures/corpus/generated
git commit -m "feat(worker): add bounded pdf page pipeline"
```

### Task A9: Build the bounded local worker executor and adapter boundaries

**Owner:** Leader; member writes fault-injection cases.

**Files:**

- Create: `services/worker/crates/runtime/Cargo.toml`
- Create: `services/worker/crates/runtime/src/{lib,config,workspace,cleanup,metrics,cancel}.rs`
- Create: `services/worker/crates/worker/Cargo.toml`
- Create: `services/worker/crates/worker/src/{main,job,issue,verify,ports,local_adapters}.rs`
- Test: `services/worker/crates/runtime/tests/{config,cleanup,sweeper}.rs`
- Test: `services/worker/crates/worker/tests/{issue_local,verify_local,fault_paths}.rs`

**Interfaces:**

- `run_job(context: WorkerContext, request: JobRequestV1) -> JobResultV1`
- `WorkerConfig::from_env(mode) -> Result<WorkerConfig, ConfigError>`
- `WorkspaceGuard::create(root, job_id, attempt) -> WorkspaceGuard`
- Traits `ObjectStore`, `MetadataRepository`, `SecretProvider` defined above.

- [ ] **Step 1: Write failing lifecycle and ceiling tests**

```rust
#[tokio::test]
async fn every_terminal_path_removes_the_workspace() {
    for fault in [Fault::None, Fault::Permanent, Fault::Retryable, Fault::Timeout, Fault::Cancel] {
        let harness = Harness::new(fault).await;
        let _ = run_job(harness.context(), harness.request()).await;
        assert!(!harness.workspace_path().exists(), "fault={fault:?}");
    }
}

#[test]
fn production_rejects_limits_above_coded_ceilings() {
    let error = WorkerConfig::parse(test_env().with("WORKER_CONCURRENCY", "2")).unwrap_err();
    assert_eq!(error.code(), "UNSAFE_PRODUCTION_LIMIT");
}
```

- [ ] **Step 2: Run tests and observe missing-crate failures**

Run: `cargo test --manifest-path services/worker/Cargo.toml -p splitbind-runtime -p splitbind-worker`

Expected: FAIL because the runtime and worker crates do not exist.

- [ ] **Step 3: Implement guarded execution and exact state outcomes**

Create a random workspace under a configured root, store `(job_id, attempt)` in a marker, enforce single-job semaphore, poll cancellation between pages, wrap processing in a 600-second Tokio timeout, and use RAII plus a startup sweeper for orphan workspaces. Upload output, call `head`, compare SHA-256, then return the result; the guard deletes local material on drop. Classify transient storage/network errors as retryable and content/validation/signature errors as permanent.

```rust
pub async fn run_job(context: WorkerContext, request: JobRequestV1) -> JobResultV1 {
    let permit = context.single_job.acquire().await.expect("worker semaphore closed");
    let workspace = match WorkspaceGuard::create(&context.config.workspace_root, request.job_id, request.attempt) {
        Ok(value) => value,
        Err(error) => return JobResultV1::failed(&request, error.safe_code()),
    };
    let execution = tokio::time::timeout(
        Duration::from_secs(600),
        execute_pipeline(&context, &request, workspace.path()),
    ).await;
    drop(permit);
    match execution {
        Ok(Ok(output)) => JobResultV1::succeeded(&request, output),
        Ok(Err(error)) if error.is_retryable() && request.attempt < 2 =>
            JobResultV1::retryable_failed(&request, error.safe_code()),
        Ok(Err(error)) => JobResultV1::failed(&request, error.safe_code()),
        Err(_) => JobResultV1::failed(&request, "JOB_TIMEOUT"),
    }
}
```

- [ ] **Step 4: Run worker, fault, idempotency, and resource harnesses**

Run: `cargo test --manifest-path services/worker/Cargo.toml --workspace`

Run: `cargo run --manifest-path services/worker/Cargo.toml -p splitbind-worker -- issue-local --request fixtures/messages/issuance-request-v1.json`

Run: `cargo run --manifest-path services/worker/Cargo.toml -p splitbind-worker -- verify-local --request fixtures/messages/verification-request-v1.json`

Expected: both jobs produce schema-valid result JSON; rerunning `(job_id, attempt)` does not create a duplicate output; all workspaces are absent afterward.

- [ ] **Step 5: Commit**

```bash
git add services/worker
git commit -m "feat(worker): add bounded job runtime and local executor"
```

## Track Verification Matrix

- `python -m pytest research/python/tests -v`
- `python -m ruff check research/python`
- `python -m mypy research/python/src`
- `cargo fmt --manifest-path services/worker/Cargo.toml --check`
- `cargo clippy --manifest-path services/worker/Cargo.toml --workspace --all-targets -- -D warnings`
- `cargo test --manifest-path services/worker/Cargo.toml --workspace`
- `python research/python/scripts/generate_vectors.py --profile contracts/algorithm/fingerprint-profile.v1.json --seed 20260827 --output fixtures/vectors/v1`
- `git diff --exit-code fixtures/vectors/v1`
- `git diff --check`

## Track Exit Evidence

- Released profile JSON with a hash and factual promotion report.
- Complete attack matrix output for the versioned corpus.
- Python and Rust parity over payload, layout, QIM, integrity, manifest, and decode vectors.
- Independent Ed25519 verification using only the public key.
- Local issuance and verification result events that validate against shared schemas.
- Observed cleanup for success, permanent failure, retryable failure, timeout, cancellation, and orphan sweep.
- Measured peak RSS, processing time/page, and temporary disk peak at input limits.
