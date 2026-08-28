"""Streaming, checkpointed execution of the versioned SplitBind benchmark."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import itertools
import json
import math
import os
import platform
import sqlite3
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence
from uuid import UUID

import cv2
import numpy as np
import pypdfium2 as pdfium
from numpy.typing import NDArray

from splitbind_attack.attacks import AttackCase, AttackedArtifact, apply_attack
from splitbind_attack.ground_truth import (
    NormalizedRect,
    Transform,
    compose_transforms,
    merge_regions,
    transform_regions,
)
from splitbind_bench.metrics import Result, compute_detection_metrics, compute_quality_metrics
from splitbind_ref.contracts import fingerprint_candidates
from splitbind_ref.fingerprint import (
    DecodeDecision,
    FingerprintContext,
    candidate_identifier,
    decode_fingerprint,
    embed_fingerprint,
)
from splitbind_ref.tile_layout import derive_tiles


NONDETERMINISTIC_ROW_FIELDS = frozenset({"elapsed_ms", "peak_rss_bytes"})
_SEED_DOMAIN = b"splitbind-benchmark-case-v1\x00"
_IDENTITY_DOMAIN = b"splitbind-benchmark-identity-v1\x00"
_KEY_DOMAIN = b"splitbind-benchmark-key-v1\x00"
_NONCE_DOMAIN = b"splitbind-benchmark-nonce-v1\x00"


@dataclass(frozen=True, slots=True)
class CorpusSource:
    fixture_id: str
    kind: str
    resolved_path: Path
    sha256: str
    pages: int
    ground_truth: tuple[NormalizedRect, ...]


@dataclass(frozen=True, slots=True)
class CorpusPage:
    source: CorpusSource
    page_index: int
    image: NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class FittedCanvas:
    image: NDArray[np.uint8]
    source_to_canvas: Transform


@dataclass(frozen=True, slots=True)
class Candidate:
    values: Mapping[str, int | float]
    profile_sha256: str


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    sources: tuple[CorpusSource, ...]
    candidates: tuple[Candidate, ...]
    attacks: tuple[AttackCase, ...]
    corpus_pages: int
    candidate_count: int
    attack_count: int
    planned_rows: int
    corpus_contract_sha256: str
    profile_contract_sha256: str
    attack_matrix_sha256: str
    plan_sha256: str
    seed: int
    smoke: bool


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    status: str
    complete: bool
    planned_rows: int
    planned_shard_rows: int
    completed_rows: int
    failed_rows: int
    shard_index: int
    shard_count: int
    output_dir: Path


def build_execution_plan(
    corpus: str | Path,
    profiles: str | Path,
    matrix: str | Path,
    seed: int,
    *,
    smoke: bool = False,
) -> ExecutionPlan:
    """Expand the exact manifest/grid/matrix cross product without executing it."""

    seed = _validate_seed(seed)
    corpus_path = Path(corpus).resolve()
    profile_path = Path(profiles).resolve()
    matrix_path = Path(matrix).resolve()
    corpus_document = _load_json(corpus_path)
    profile_document = _load_json(profile_path)
    matrix_document = _load_json(matrix_path)
    sources = _corpus_sources(corpus_path, corpus_document)
    candidates = _candidate_grid(profile_document)
    attacks = _attack_cases(matrix_document)
    if smoke:
        sources = _smoke_sources(sources)
        candidates = candidates[:1]
        attacks = _smoke_attacks(attacks)
    page_count = sum(source.pages for source in sources)
    plan_sha256 = _plan_digest(sources, candidates, attacks)
    return ExecutionPlan(
        sources=sources,
        candidates=candidates,
        attacks=attacks,
        corpus_pages=page_count,
        candidate_count=len(candidates),
        attack_count=len(attacks),
        planned_rows=page_count * len(candidates) * len(attacks),
        corpus_contract_sha256=_sha256_file(corpus_path),
        profile_contract_sha256=_sha256_file(profile_path),
        attack_matrix_sha256=_sha256_file(matrix_path),
        plan_sha256=plan_sha256,
        seed=seed,
        smoke=smoke,
    )


def iter_corpus_pages(
    corpus: str | Path, *, fixture_ids: set[str] | None = None
) -> Iterator[CorpusPage]:
    """Render every declared page, verifying source hashes and page counts."""

    corpus_path = Path(corpus).resolve()
    sources = _corpus_sources(corpus_path, _load_json(corpus_path))
    selected = tuple(
        source for source in sources if fixture_ids is None or source.fixture_id in fixture_ids
    )
    yield from _iter_sources(selected)


def run_matrix(
    corpus: str | Path,
    profiles: str | Path,
    matrix: str | Path,
    seed: int,
    output_dir: str | Path,
    *,
    smoke: bool = False,
    max_rows: int | None = None,
    shard_index: int = 0,
    shard_count: int = 1,
) -> BenchmarkSummary:
    """Run or resume a matrix shard and atomically export truthful evidence.

    Each result is committed to SQLite before the next case starts.  Reusing the
    same output directory resumes only when seed, contracts, smoke mode, and
    shard identity match exactly.
    """

    plan = build_execution_plan(corpus, profiles, matrix, seed, smoke=smoke)
    _validate_shard(shard_index, shard_count)
    if max_rows is not None and (isinstance(max_rows, bool) or max_rows < 1):
        raise ValueError("max_rows must be a positive integer")
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    database_path = destination / "checkpoint.sqlite3"
    identity = _run_identity(plan, shard_index, shard_count)
    started = time.perf_counter_ns()
    target_width, target_height = _benchmark_dimensions(plan.candidates)
    connection = sqlite3.connect(database_path)
    try:
        _initialize_checkpoint(connection, identity)
        existing = {
            row[0] for row in connection.execute("SELECT row_id FROM result_rows")
        }
        new_rows = 0
        global_ordinal = 0
        stop = False
        for raw_page in _iter_sources(plan.sources):
            fitted = _fit_canvas(raw_page.image, target_width, target_height)
            page = fitted.image
            for candidate in plan.candidates:
                scheduled: list[tuple[int, AttackCase, str]] = []
                for attack in plan.attacks:
                    row_id = _row_identifier(
                        raw_page.source.fixture_id,
                        raw_page.page_index,
                        candidate.profile_sha256,
                        attack.case_id,
                    )
                    belongs = global_ordinal % shard_count == shard_index
                    global_ordinal += 1
                    if belongs and row_id not in existing:
                        scheduled.append((global_ordinal - 1, attack, row_id))
                if not scheduled:
                    continue
                context_values = _case_context(
                    plan.seed,
                    raw_page.source.fixture_id,
                    raw_page.page_index,
                    candidate.profile_sha256,
                )
                runtime_profile = {
                    "schema_version": 1,
                    **candidate.values,
                    "document_nonce": context_values[2],
                    "page_index": raw_page.page_index,
                }
                expected_id: UUID | None = None
                embedding_error: Exception | None = None
                watermarked = page
                decode_profile = runtime_profile
                if raw_page.source.kind != "negative_external":
                    expected_id = context_values[0]
                    try:
                        embedded = embed_fingerprint(
                            page,
                            FingerprintContext(
                                issuance_id=expected_id,
                                fingerprint_key=context_values[1],
                                document_nonce=context_values[2],
                                page_index=raw_page.page_index,
                            ),
                            runtime_profile,
                        )
                        watermarked = embedded.image
                        decode_profile = {**runtime_profile, "sync_template": embedded.sync_template}
                    except Exception as error:  # Every planned case remains represented.
                        embedding_error = error
                quality = compute_quality_metrics(page, watermarked)
                for _, attack, row_id in scheduled:
                    if max_rows is not None and new_rows >= max_rows:
                        stop = True
                        break
                    row = _execute_row(
                        plan=plan,
                        source=raw_page.source,
                        page_index=raw_page.page_index,
                        candidate=candidate,
                        attack=attack,
                        row_id=row_id,
                        original=page,
                        watermarked=watermarked,
                        source_to_canvas=fitted.source_to_canvas,
                        runtime_profile=runtime_profile,
                        decode_profile=decode_profile,
                        expected_id=expected_id,
                        key=context_values[1],
                        quality=quality,
                        embedding_error=embedding_error,
                    )
                    connection.execute(
                        "INSERT INTO result_rows(row_id, payload) VALUES (?, ?)",
                        (row_id, _canonical_json(row)),
                    )
                    connection.commit()
                    existing.add(row_id)
                    new_rows += 1
                if stop:
                    break
            if stop:
                break
        summary = _export_artifacts(
            connection,
            destination,
            plan,
            shard_index,
            shard_count,
            wall_clock_elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000.0,
        )
    finally:
        connection.close()
    return summary


def _execute_row(
    *,
    plan: ExecutionPlan,
    source: CorpusSource,
    page_index: int,
    candidate: Candidate,
    attack: AttackCase,
    row_id: str,
    original: NDArray[np.uint8],
    watermarked: NDArray[np.uint8],
    source_to_canvas: Transform,
    runtime_profile: Mapping[str, object],
    decode_profile: Mapping[str, object],
    expected_id: UUID | None,
    key: bytes,
    quality,
    embedding_error: Exception | None,
) -> dict[str, object]:
    case_seed = _case_seed(
        plan.seed, source.fixture_id, page_index, candidate.profile_sha256, attack.case_id
    )
    limitations = [
        "A5 integrity localization is not implemented; tamper ground truth is recorded but localization IoU is not evaluated",
        "peak RSS is the process-lifetime OS high-water mark observed after attack and decode",
        "temporary disk peak is 0 because A4 attacks and decode run in memory; output/checkpoint storage is excluded",
    ]
    decision = DecodeDecision(None, 0.0, 0, None, "not_detected")
    artifact: AttackedArtifact | None = None
    elapsed_ms = 0.0
    error_text: str | None = None
    rss_before = _peak_rss_bytes()
    if embedding_error is None:
        start = time.perf_counter_ns()
        try:
            artifact = apply_attack(
                watermarked, attack, np.random.default_rng(case_seed)
            )
            decision = decode_fingerprint(artifact.image, key, (decode_profile,))
        except Exception as error:  # Preserve failures as data instead of omission.
            error_text = f"{type(error).__name__}: {error}"
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    else:
        error_text = f"embedding {type(embedding_error).__name__}: {embedding_error}"
    peak_rss = max(rss_before, _peak_rss_bytes())

    remaining_tiles: int | None = None
    eligible = True
    eligibility_reason = "eligible"
    if artifact is not None and artifact.retained_region is not None and expected_id is not None:
        remaining_tiles = _remaining_embedded_tiles(
            original.shape[:2], key, runtime_profile, artifact.retained_region
        )
        eligible = remaining_tiles >= 2
        eligibility_reason = (
            "at_least_two_complete_embedded_tiles_remain"
            if eligible
            else "fewer_than_two_complete_embedded_tiles_remain"
        )
    if error_text is not None:
        limitations.append(error_text)

    ground_truth_transform = source_to_canvas
    if artifact is not None:
        ground_truth_transform = compose_transforms(
            artifact.source_to_output, source_to_canvas
        )
    ground_truth = transform_regions(source.ground_truth, ground_truth_transform)
    if artifact is not None:
        ground_truth = merge_regions(
            ground_truth,
            artifact.ground_truth,
        )

    decoded_id = str(decision.issuance_id) if decision.issuance_id is not None else None
    expected_text = str(expected_id) if expected_id is not None else None
    outcome = _outcome(expected_text, decoded_id, decision.reason, error_text)
    profile_for_identifier = dict(runtime_profile)
    row = {
        "schema_version": 1,
        "row_id": row_id,
        "evidence_scope": "research_measurement_only",
        "profile_promoted": False,
        "corpus_contract_sha256": plan.corpus_contract_sha256,
        "corpus_sha256": source.sha256,
        "profile_contract_sha256": plan.profile_contract_sha256,
        "attack_matrix_sha256": plan.attack_matrix_sha256,
        "benchmark_plan_sha256": plan.plan_sha256,
        "algorithm_profile_sha256": candidate.profile_sha256,
        "candidate_id": candidate_identifier(profile_for_identifier).hex(),
        "fixture_id": source.fixture_id,
        "fixture_kind": source.kind,
        "page_index": page_index,
        "attack_id": attack.case_id,
        "attack_kind": attack.kind,
        "attack_parameters": _plain_parameters(attack.parameters),
        "ordered_operations": [operation.kind for operation in attack.operations]
        if attack.operations
        else list(artifact.operations if artifact is not None else (attack.kind,)),
        "seed": plan.seed,
        "case_seed": case_seed,
        "expected_id": expected_text,
        "decoded_id": decoded_id,
        "confidence": float(decision.confidence),
        "bit_error_rate": decision.bit_error_rate,
        "reason": decision.reason if error_text is None else "execution_error",
        "outcome": outcome,
        "valid_vote_count": decision.valid_votes,
        "psnr_db": _finite_json_number(quality.psnr_db),
        "ssim": quality.ssim,
        "quality_data_range": quality.data_range,
        "quality_scope": "original_vs_watermarked_before_attack"
        if expected_id is not None
        else "negative_control_original_vs_unmodified",
        "localization_iou": None,
        "tamper_ground_truth": [rect.as_dict() for rect in ground_truth],
        "ground_truth_coordinate_system": "normalized_attack_output_axis_aligned_envelope",
        "elapsed_ms": elapsed_ms,
        "timing_scope": "attack_and_decode",
        "peak_rss_bytes": peak_rss,
        "peak_rss_scope": "process_lifetime_high_water_observed_after_attack_and_decode",
        "temp_peak_bytes": 0,
        "temp_peak_scope": "attack_and_decode_in_memory_temporary_files_only",
        "eligible": eligible,
        "eligibility_reason": eligibility_reason,
        "remaining_embedded_tiles": remaining_tiles,
        "removed_area_fraction": artifact.removed_area_fraction if artifact is not None else None,
        "limitations": limitations,
    }
    return row


def _attack_cases(document: Mapping[str, object]) -> tuple[AttackCase, ...]:
    if document.get("schema_version") != 1:
        raise ValueError("attack matrix schema_version must be 1")
    cases: list[AttackCase] = []
    for quality in _list(document, "jpeg_quality"):
        cases.append(AttackCase(f"jpeg-q{quality}", "jpeg", {"quality": quality}))
    for fraction in _list(document, "crop_fraction"):
        cases.append(AttackCase(f"crop-f{_slug(fraction)}", "crop", {"fraction": fraction}))
    for scale in _list(document, "resize_scale"):
        cases.append(AttackCase(f"resize-s{_slug(scale)}", "resize", {"scale": scale}))
    for degrees in _list(document, "rotation_degrees"):
        cases.append(AttackCase(f"rotation-d{_slug(degrees)}", "rotation", {"degrees": degrees}))
    for index, parameters in enumerate(_list(document, "brightness_contrast")):
        cases.append(AttackCase(f"brightness-contrast-{index}", "brightness_contrast", parameters))
    for index, parameters in enumerate(_list(document, "gaussian_noise_blur")):
        cases.append(AttackCase(f"noise-blur-{index}", "noise_blur", parameters))
    for index, parameters in enumerate(_list(document, "screenshot")):
        cases.append(AttackCase(f"screenshot-{index}-{parameters['kind']}", "screenshot", parameters))
    for index, parameters in enumerate(_list(document, "combined")):
        names = parameters.get("operations")
        if names == ["jpeg", "crop"]:
            operations = (
                AttackCase("combined-jpeg", "jpeg", {"quality": parameters["jpeg_quality"]}),
                AttackCase("combined-crop", "crop", {"fraction": parameters["crop_fraction"]}),
            )
        elif names == ["screenshot", "perspective"]:
            screen_parameters = {
                "kind": "raster",
                "width_px": parameters["width_px"],
                "height_px": parameters["height_px"],
            }
            operations = (
                AttackCase("combined-screenshot", "screenshot", screen_parameters),
                AttackCase(
                    "combined-perspective",
                    "perspective",
                    {"corner_offsets": parameters["corner_offsets"]},
                ),
            )
        else:
            raise ValueError("combined attack contains unsupported ordered operations")
        cases.append(AttackCase(f"combined-{index}", "combined", parameters, operations))
    for index, parameters in enumerate(_list(document, "tamper")):
        cases.append(AttackCase(f"tamper-{index}-{parameters['kind']}", "tamper", parameters))
    return tuple(cases)


def _candidate_grid(document: Mapping[str, object]) -> tuple[Candidate, ...]:
    if document.get("schema_version") != 1:
        raise ValueError("candidate schema_version must be 1")
    fixed = document.get("fixed")
    canonical_fixed = fingerprint_candidates().get("fixed")
    if not isinstance(fixed, Mapping) or fixed != canonical_fixed:
        raise ValueError(
            "selected candidate fixed contract must exactly match the canonical A3 fixed contract"
        )
    sweep = document.get("sweep")
    if not isinstance(sweep, Mapping):
        raise ValueError("candidate sweep must be a mapping")
    keys = ("qim_delta", "tile_size_px", "tiles_per_page", "payload_repetitions")
    values = [_list(sweep, key) for key in keys]
    candidates = []
    for combination in itertools.product(*values):
        profile = dict(zip(keys, combination, strict=True))
        digest = hashlib.sha256(
            _canonical_json(
                {"schema_version": 1, "fixed": fixed, "candidate": profile}
            ).encode()
        ).hexdigest()
        candidates.append(Candidate(profile, digest))
    return tuple(candidates)


def _corpus_sources(
    corpus_path: Path, document: Mapping[str, object]
) -> tuple[CorpusSource, ...]:
    if document.get("schema_version") != 1:
        raise ValueError("corpus schema_version must be 1")
    raw_entries = _list(document, "entries")
    sources: list[CorpusSource] = []
    seen: set[str] = set()
    for entry in raw_entries:
        if not isinstance(entry, Mapping):
            raise ValueError("corpus entries must be mappings")
        fixture_id = entry.get("fixture_id")
        kind = entry.get("kind")
        relative = entry.get("relative_path")
        sha256 = entry.get("sha256")
        pages = entry.get("pages")
        raw_ground_truth = entry.get("ground_truth_regions", [])
        if not isinstance(fixture_id, str) or not fixture_id or fixture_id in seen:
            raise ValueError("corpus fixture_id must be unique and non-empty")
        if kind not in {"clean_pdf", "clean_image", "negative_external", "tamper_ground_truth"}:
            raise ValueError(f"unsupported corpus kind for {fixture_id}")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError("corpus relative_path must be relative")
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise ValueError("corpus sha256 must be a hexadecimal SHA-256")
        if isinstance(pages, bool) or not isinstance(pages, int) or pages < 1:
            raise ValueError("corpus pages must be a positive integer")
        if not isinstance(raw_ground_truth, list):
            raise ValueError("corpus ground_truth_regions must be a list")
        ground_truth: list[NormalizedRect] = []
        for raw_region in raw_ground_truth:
            if not isinstance(raw_region, Mapping):
                raise ValueError("corpus ground-truth regions must be mappings")
            try:
                ground_truth.append(
                    NormalizedRect(
                        raw_region["x"],
                        raw_region["y"],
                        raw_region["width"],
                        raw_region["height"],
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("corpus ground-truth region is invalid") from error
        if kind == "tamper_ground_truth" and not ground_truth:
            raise ValueError(
                "tamper_ground_truth corpus entries require ground-truth regions"
            )
        resolved = (corpus_path.parent / relative).resolve()
        if not resolved.is_relative_to(corpus_path.parent.resolve()):
            raise ValueError("corpus relative_path escapes the manifest directory")
        sources.append(
            CorpusSource(fixture_id, kind, resolved, sha256, pages, tuple(ground_truth))
        )
        seen.add(fixture_id)
    return tuple(sources)


def _iter_sources(sources: Sequence[CorpusSource]) -> Iterator[CorpusPage]:
    for source in sources:
        if not source.resolved_path.is_file():
            raise FileNotFoundError(f"corpus source is missing: {source.resolved_path}")
        actual_sha = _sha256_file(source.resolved_path)
        if actual_sha != source.sha256:
            raise ValueError(f"corpus checksum mismatch for {source.fixture_id}")
        if source.resolved_path.suffix.lower() == ".pdf":
            document = pdfium.PdfDocument(str(source.resolved_path))
            try:
                if len(document) != source.pages:
                    raise ValueError(f"corpus page count mismatch for {source.fixture_id}")
                for page_index in range(len(document)):
                    page = document[page_index]
                    bitmap = page.render(scale=2.0)
                    try:
                        rgb = bitmap.to_numpy()
                        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                        yield CorpusPage(source, page_index, np.ascontiguousarray(bgr))
                    finally:
                        bitmap.close()
                        page.close()
            finally:
                document.close()
        else:
            image = cv2.imread(str(source.resolved_path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"unable to decode corpus image {source.fixture_id}")
            if source.pages != 1:
                raise ValueError(f"image corpus entry {source.fixture_id} must declare one page")
            yield CorpusPage(source, 0, np.ascontiguousarray(image))


def _remaining_embedded_tiles(
    page_shape: tuple[int, int],
    key: bytes,
    profile: Mapping[str, object],
    retained,
) -> int:
    tile_profile = {
        "schema_version": int(profile["schema_version"]),
        "tile_size_px": int(profile["tile_size_px"]),
        "tiles_per_page": int(profile["tiles_per_page"]),
    }
    tiles = derive_tiles(
        page_shape,
        key,
        profile["document_nonce"],
        int(profile["page_index"]),
        tile_profile,
    )[: int(profile["payload_repetitions"])]
    height, width = page_shape
    left = retained.x * width
    top = retained.y * height
    right = retained.right * width
    bottom = retained.bottom * height
    return sum(
        tile.x >= left
        and tile.y >= top
        and tile.x + tile.width <= right
        and tile.y + tile.height <= bottom
        for tile in tiles
    )


def _fit_canvas(image: NDArray[np.uint8], width: int, height: int) -> FittedCanvas:
    source_height, source_width = image.shape[:2]
    scale = min(width / source_width, height / source_height)
    target_width = max(1, round(source_width * scale))
    target_height = max(1, round(source_height * scale))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    resized = cv2.resize(image, (target_width, target_height), interpolation=interpolation)
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    x0 = (width - target_width) // 2
    y0 = (height - target_height) // 2
    canvas[y0 : y0 + target_height, x0 : x0 + target_width] = resized
    return FittedCanvas(
        image=canvas,
        source_to_canvas=(
            target_width / width,
            0.0,
            x0 / width,
            0.0,
            target_height / height,
            y0 / height,
            0.0,
            0.0,
            1.0,
        ),
    )


def _benchmark_dimensions(candidates: Sequence[Candidate]) -> tuple[int, int]:
    max_tiles = max(int(candidate.values["tiles_per_page"]) for candidate in candidates)
    max_tile_size = max(int(candidate.values["tile_size_px"]) for candidate in candidates)
    pairs = [(columns, max_tiles // columns) for columns in range(1, max_tiles + 1) if max_tiles % columns == 0]
    columns, rows = min(
        ((max(first, second), min(first, second)) for first, second in pairs),
        key=lambda pair: abs(pair[0] / pair[1] - 1.5),
    )
    return columns * max_tile_size, rows * max_tile_size


def _case_context(
    seed: int, fixture_id: str, page_index: int, profile_sha256: str
) -> tuple[UUID, bytes, bytes]:
    binding = (
        seed.to_bytes(8, "big")
        + fixture_id.encode("utf-8")
        + b"\x00"
        + page_index.to_bytes(4, "big")
        + bytes.fromhex(profile_sha256)
    )
    issuance = bytearray(hashlib.sha256(_IDENTITY_DOMAIN + binding).digest()[:16])
    issuance[6] = (issuance[6] & 0x0F) | 0x40
    issuance[8] = (issuance[8] & 0x3F) | 0x80
    key = hashlib.sha256(_KEY_DOMAIN + binding).digest()
    nonce = hashlib.sha256(_NONCE_DOMAIN + binding).digest()[:16]
    return UUID(bytes=bytes(issuance)), key, nonce


def _plan_digest(
    sources: Sequence[CorpusSource],
    candidates: Sequence[Candidate],
    attacks: Sequence[AttackCase],
) -> str:
    def attack_document(case: AttackCase) -> dict[str, object]:
        return {
            "case_id": case.case_id,
            "kind": case.kind,
            "parameters": _plain_parameters(case.parameters),
            "operations": [attack_document(operation) for operation in case.operations],
        }

    document = {
        "sources": [
            {
                "fixture_id": source.fixture_id,
                "kind": source.kind,
                "sha256": source.sha256,
                "pages": source.pages,
            }
            for source in sources
        ],
        "candidates": [candidate.profile_sha256 for candidate in candidates],
        "attacks": [attack_document(attack) for attack in attacks],
    }
    return hashlib.sha256(_canonical_json(document).encode("utf-8")).hexdigest()


def _case_seed(
    seed: int, fixture_id: str, page_index: int, profile_sha256: str, attack_id: str
) -> int:
    material = (
        _SEED_DOMAIN
        + seed.to_bytes(8, "big")
        + fixture_id.encode("utf-8")
        + b"\x00"
        + page_index.to_bytes(4, "big")
        + bytes.fromhex(profile_sha256)
        + attack_id.encode("utf-8")
    )
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _run_identity(plan: ExecutionPlan, shard_index: int, shard_count: int) -> str:
    return _canonical_json(
        {
            "schema_version": 1,
            "seed": plan.seed,
            "smoke": plan.smoke,
            "corpus_contract_sha256": plan.corpus_contract_sha256,
            "profile_contract_sha256": plan.profile_contract_sha256,
            "attack_matrix_sha256": plan.attack_matrix_sha256,
            "plan_sha256": plan.plan_sha256,
            "planned_rows": plan.planned_rows,
            "shard_index": shard_index,
            "shard_count": shard_count,
        }
    )


def _initialize_checkpoint(connection: sqlite3.Connection, identity: str) -> None:
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS result_rows (row_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    observed = connection.execute("SELECT value FROM metadata WHERE key='run_identity'").fetchone()
    if observed is None:
        connection.execute("INSERT INTO metadata(key, value) VALUES ('run_identity', ?)", (identity,))
        connection.commit()
    elif observed[0] != identity:
        raise ValueError("output checkpoint belongs to a different benchmark run")


def _export_artifacts(
    connection: sqlite3.Connection,
    destination: Path,
    plan: ExecutionPlan,
    shard_index: int,
    shard_count: int,
    *,
    wall_clock_elapsed_ms: float,
) -> BenchmarkSummary:
    payloads = [
        json.loads(row[0])
        for row in connection.execute("SELECT payload FROM result_rows ORDER BY row_id")
    ]
    planned_shard_rows = sum(
        ordinal % shard_count == shard_index for ordinal in range(plan.planned_rows)
    )
    completed = len(payloads)
    failed = sum(row["outcome"] == "execution_error" for row in payloads)
    complete_shard = completed == planned_shard_rows
    complete = complete_shard and shard_count == 1
    status = (
        "complete_with_errors"
        if complete and failed
        else "complete"
        if complete
        else "complete_shard_with_errors"
        if complete_shard and failed
        else "complete_shard"
        if complete_shard
        else "partial"
    )
    detection = compute_detection_metrics(
        Result(
            expected=row["expected_id"],
            decoded=row["decoded_id"],
            reason=row["reason"],
            eligible=row["eligible"],
        )
        for row in payloads
    )
    summary_document = {
        "schema_version": 1,
        "status": status,
        "complete": complete,
        "evidence_scope": "research_measurement_only",
        "profile_promoted": False,
        "planned_rows": plan.planned_rows,
        "planned_shard_rows": planned_shard_rows,
        "completed_rows": completed,
        "failed_rows": failed,
        "seed": plan.seed,
        "smoke": plan.smoke,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "wall_clock_elapsed_ms": wall_clock_elapsed_ms,
        "timing_scope": "run_matrix including load, raster normalization, embed, attack, decode, checkpoint, and export",
        "contracts": {
            "corpus_sha256": plan.corpus_contract_sha256,
            "profiles_sha256": plan.profile_contract_sha256,
            "attack_matrix_sha256": plan.attack_matrix_sha256,
            "plan_sha256": plan.plan_sha256,
        },
        "environment": _environment(),
        "detection_metrics": asdict(detection),
        "limitations": [
            "A4 records candidate measurements and does not promote an algorithm profile",
            "A5 integrity localization is unavailable, so localization IoU remains null",
            "process RSS includes prior allocations and is not isolated worker RSS",
            "temporary disk excludes checkpoint and report outputs because attack/decode uses no temporary files",
        ],
    }
    jsonl = "".join(_canonical_json(row) + "\n" for row in payloads)
    _atomic_write_text(destination / "results.jsonl", jsonl)
    _atomic_write_csv(destination / "results.csv", payloads)
    _atomic_write_text(destination / "summary.json", json.dumps(summary_document, indent=2, sort_keys=True) + "\n")
    return BenchmarkSummary(
        status=status,
        complete=complete,
        planned_rows=plan.planned_rows,
        planned_shard_rows=planned_shard_rows,
        completed_rows=completed,
        failed_rows=failed,
        shard_index=shard_index,
        shard_count=shard_count,
        output_dir=destination,
    )


def _atomic_write_text(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        _atomic_write_text(path, "")
        return
    fieldnames = list(rows[0])
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: _canonical_json(value) if isinstance(value, (dict, list)) else value
                        for key, value in row.items()
                    }
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _environment() -> dict[str, object]:
    dependencies = {}
    for distribution in (
        "numpy",
        "opencv-python-headless",
        "pypdfium2",
        "reedsolo",
        "splitbind-ref",
    ):
        try:
            dependencies[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            dependencies[distribution] = "not-installed"
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "opencv": cv2.__version__,
        "pdfium": str(getattr(pdfium, "PDFIUM_INFO", "unknown")),
        "dependencies": dependencies,
    }


def _peak_rss_bytes() -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.argtypes = []
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            process = kernel32.GetCurrentProcess()
            if psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
                return int(counters.PeakWorkingSetSize)
        except (AttributeError, OSError):
            return 0
        return 0
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == "darwin" else value * 1024)
    except (ImportError, OSError):
        return 0


def _smoke_sources(sources: Sequence[CorpusSource]) -> tuple[CorpusSource, ...]:
    positive = next(
        (source for source in sources if source.fixture_id == "image-clean-noise"),
        next(
            (
                source
                for source in sources
                if source.kind in {"clean_image", "tamper_ground_truth"}
            ),
            None,
        ),
    )
    negative = next((source for source in sources if source.kind == "negative_external"), None)
    selected = tuple(source for source in (positive, negative) if source is not None)
    if not selected:
        raise ValueError("smoke mode requires at least one image corpus source")
    return selected


def _smoke_attacks(attacks: Sequence[AttackCase]) -> tuple[AttackCase, ...]:
    preferred = {
        "jpeg-q70",
        "crop-f0p25",
        "resize-s0p75",
        "rotation-d3",
        "brightness-contrast-0",
        "noise-blur-1",
        "screenshot-2-perspective",
        "combined-0",
        "tamper-0-replace_text",
    }
    selected = tuple(case for case in attacks if case.case_id in preferred)
    return selected or tuple(attacks[: min(3, len(attacks))])


def _outcome(expected: str | None, decoded: str | None, reason: str, error: str | None) -> str:
    if error is not None:
        return "execution_error"
    if decoded is not None and decoded == expected:
        return "true_attribution"
    if decoded is not None:
        return "false_attribution"
    if expected is None:
        return "true_negative"
    return reason


def _row_identifier(fixture_id: str, page_index: int, profile_hash: str, attack_id: str) -> str:
    material = f"{fixture_id}\x00{page_index}\x00{profile_hash}\x00{attack_id}".encode()
    return hashlib.sha256(material).hexdigest()


def _plain_parameters(parameters: Mapping[str, object]) -> dict[str, object]:
    return json.loads(_canonical_json(dict(parameters)))


def _finite_json_number(value: float) -> float | str:
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    if math.isnan(value):
        return "NaN"
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as stream:
        document = json.load(stream)
    if not isinstance(document, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return document


def _list(mapping: Mapping[str, object], key: str) -> list:
    value = mapping.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: object) -> str:
    return str(value).replace("-", "m").replace(".", "p")


def _validate_seed(seed: int) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("seed must fit an unsigned 64-bit integer")
    return seed


def _validate_shard(shard_index: int, shard_count: int) -> None:
    if (
        isinstance(shard_index, bool)
        or isinstance(shard_count, bool)
        or not isinstance(shard_index, int)
        or not isinstance(shard_count, int)
        or shard_count < 1
        or not 0 <= shard_index < shard_count
    ):
        raise ValueError("shard_index must be in [0, shard_count)")
