import json
import zlib
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[4]
SCHEMA_DIR = ROOT / "contracts" / "jsonschema"


def load_json(relative_path: str) -> dict:
    with (ROOT / relative_path).open(encoding="utf-8") as stream:
        return json.load(stream)


def schema_registry() -> Registry:
    resources = []
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def validate(schema_name: str, instance: dict) -> None:
    schema = load_json(f"contracts/jsonschema/{schema_name}")
    Draft202012Validator(
        schema,
        registry=schema_registry(),
        format_checker=FormatChecker(),
    ).validate(instance)


def test_every_json_schema_is_valid_and_forbids_top_level_extras():
    schemas = sorted(SCHEMA_DIR.glob("*.schema.json"))
    assert len(schemas) == 7
    for path in schemas:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False, path.name


def test_payload_profile_freezes_binary_layout_and_shortened_rs_parameters():
    profile = load_json("contracts/algorithm/payload-profile.v1.json")
    assert profile["schema_version"] == 1
    assert profile["payload"] == {
        "magic_ascii": "SB",
        "schema_version_bytes": 1,
        "issuance_uuid_bytes": 16,
        "crc32_bytes": 4,
        "byte_order": "big-endian",
        "total_bytes": 23,
    }
    assert profile["reed_solomon"] == {
        "field": "GF(256)",
        "primitive_polynomial": "0x11d",
        "parity_symbols": 16,
        "message_bytes": 23,
        "codeword_bytes": 39,
        "correctable_symbol_errors": 8,
    }
    assert profile["interleave_depth"] == 8


def test_payload_profile_publishes_a_real_crc32_golden_payload():
    profile = load_json("contracts/algorithm/payload-profile.v1.json")
    golden = profile["golden_vector"]
    assert golden == {
        "schema_version": 1,
        "issuance_id": "12345678-1234-5678-1234-567812345678",
        "body_hex": "53420112345678123456781234567812345678",
        "crc32_hex": "9ae24281",
        "payload_hex": "534201123456781234567812345678123456789ae24281",
    }
    assert profile["crc32"] == {
        "name": "CRC-32/ISO-HDLC",
        "polynomial": "0x04c11db7",
        "initial_value": "0xffffffff",
        "reflect_input": True,
        "reflect_output": True,
        "xor_output": "0xffffffff",
        "input_bytes": 19,
    }

    body = bytes.fromhex(golden["body_hex"])
    payload = bytes.fromhex(golden["payload_hex"])
    expected_body = b"SB" + b"\x01" + UUID(golden["issuance_id"]).bytes
    assert body == expected_body
    assert len(body) == profile["crc32"]["input_bytes"] == 19
    assert len(payload) == profile["payload"]["total_bytes"] == 23
    assert payload[:19] == body
    assert payload[19:] == bytes.fromhex("9ae24281")
    assert zlib.crc32(payload[:19]).to_bytes(4, "big") == payload[19:]
    assert zlib.crc32(payload[:18]).to_bytes(4, "big") != payload[19:]
    assert zlib.crc32(payload[:20]).to_bytes(4, "big") != payload[19:]


def test_fingerprint_candidate_grid_matches_the_research_sweep():
    candidates = load_json("contracts/algorithm/fingerprint-candidates.v1.json")
    assert candidates == {
        "schema_version": 1,
        "fixed": {
            "wavelet": "haar",
            "wavelet_level": 1,
            "dct_block_size": 8,
            "midband_pairs": [[[1, 2], [2, 1]], [[2, 3], [3, 2]]],
            "ecc_parity_symbols": 16,
            "interleave_depth": 8,
            "sync_detector": "orb-ransac",
        },
        "sweep": {
            "qim_delta": [6.0, 8.0, 10.0, 12.0],
            "tile_size_px": [256, 384],
            "tiles_per_page": [12, 18, 24],
            "payload_repetitions": [3, 5],
        },
    }


def test_integrity_profile_freezes_partner_region_authentication_contract():
    profile = load_json("contracts/algorithm/integrity-profile.v1.json")
    assert profile["schema_version"] == 1
    assert profile["region_size_px"] == 128
    assert profile["authentication"] == {
        "algorithm": "hmac-sha256",
        "tag_bytes": 4,
        "binding_inputs": [
            "content_feature",
            "region_index_be32",
            "document_nonce",
        ],
        "placement": "key-derived-partner-region",
        "exclude_destination_coefficients_from_feature": True,
    }
    assert profile["localization"] == {
        "coordinate_space": "normalized-xywh",
        "score_range": [0.0, 1.0],
    }


def test_algorithm_vector_envelope_validates_bytes_and_rejects_extras():
    vector = {
        "schema_version": 1,
        "vector_id": "payload.case-001",
        "vector_type": "payload",
        "profile_sha256": "0" * 64,
        "seed": 20260827,
        "input_hex": "12345678123456781234567812345678",
        "expected_hex": "534201123456781234567812345678123456789ae24281",
    }
    validate("algorithm-vector-v1.schema.json", vector)

    with pytest.raises(ValidationError):
        validate("algorithm-vector-v1.schema.json", {**vector, "notes": "not contracted"})
    with pytest.raises(ValidationError):
        validate("algorithm-vector-v1.schema.json", {**vector, "input_hex": "abc"})


def test_attack_matrix_has_every_required_level():
    matrix = load_json("contracts/algorithm/attack-matrix.v1.json")
    assert matrix["schema_version"] == 1
    assert matrix["jpeg_quality"] == [95, 85, 70, 50]
    assert matrix["crop_fraction"] == [0.10, 0.25, 0.50]
    assert matrix["resize_scale"] == [0.50, 0.75, 1.50]
    assert matrix["rotation_degrees"] == [-5, -3, -1, 1, 3, 5]
    assert len(matrix["brightness_contrast"]) == 3
    assert len(matrix["gaussian_noise_blur"]) == 3
    assert len(matrix["screenshot"]) == 3
    assert {case["kind"] for case in matrix["tamper"]} == {
        "replace_text",
        "cover_region",
        "copy_move",
        "insert_object",
    }


def test_attack_matrix_cases_have_executable_parameters():
    matrix = load_json("contracts/algorithm/attack-matrix.v1.json")
    assert all(
        set(case) == {"brightness_factor", "contrast_factor"}
        for case in matrix["brightness_contrast"]
    )
    assert all(
        set(case) == {"noise_sigma", "blur_sigma"}
        for case in matrix["gaussian_noise_blur"]
    )
    assert [case["kind"] for case in matrix["screenshot"]] == [
        "raster",
        "raster",
        "perspective",
    ]
    assert all(case["width_px"] > 0 and case["height_px"] > 0 for case in matrix["screenshot"])
    assert [case["operations"] for case in matrix["combined"]] == [
        ["jpeg", "crop"],
        ["screenshot", "perspective"],
    ]
    for case in matrix["tamper"]:
        rectangle = case["region"]
        assert set(rectangle) == {"x", "y", "width", "height"}
        assert all(0.0 <= rectangle[key] <= 1.0 for key in rectangle)
        assert rectangle["x"] + rectangle["width"] <= 1.0
        assert rectangle["y"] + rectangle["height"] <= 1.0


def test_job_contracts_freeze_fields_and_forbid_extras():
    request = load_json("contracts/jsonschema/job-request-v1.schema.json")
    result = load_json("contracts/jsonschema/job-result-v1.schema.json")
    assert request["additionalProperties"] is False
    assert result["additionalProperties"] is False
    assert set(request["required"]) == {
        "schema_version",
        "message_type",
        "message_id",
        "job_id",
        "attempt",
        "issuance_id",
        "verification_id",
        "input_object_key",
        "input_sha256",
        "deadline_at",
        "correlation_id",
    }
    assert set(result["required"]) == {
        "schema_version",
        "message_type",
        "message_id",
        "job_id",
        "attempt",
        "output_object_key",
        "output_sha256",
        "recovered_issuance_id",
        "verification_status",
        "evidence",
        "metrics",
        "safe_error_code",
        "correlation_id",
    }
    assert "$ref" in result["properties"]["metrics"]
    assert request["x-splitbind-input-limits"] == {
        "max_bytes": 10_485_760,
        "max_pdf_pages": 50,
        "max_image_pixels": 40_000_000,
    }


@pytest.mark.parametrize(
    "fixture_name",
    ["issuance-request-v1.json", "verification-request-v1.json"],
)
def test_request_fixtures_validate_unchanged(fixture_name: str):
    fixture = load_json(f"fixtures/messages/{fixture_name}")
    validate("job-request-v1.schema.json", fixture)


def test_request_kind_requires_exactly_its_pseudonymous_identifier():
    issuance = load_json("fixtures/messages/issuance-request-v1.json")
    verification = load_json("fixtures/messages/verification-request-v1.json")
    assert issuance["issuance_id"] is not None
    assert issuance["verification_id"] is None
    assert verification["issuance_id"] is None
    assert verification["verification_id"] is not None

    invalid = deepcopy(issuance)
    invalid["issuance_id"] = None
    with pytest.raises(ValidationError):
        validate("job-request-v1.schema.json", invalid)


def test_request_fixture_rejects_extra_or_malformed_fields():
    fixture = load_json("fixtures/messages/issuance-request-v1.json")
    with_extra = {**fixture, "recipient_id": "00000000-0000-0000-0000-000000000099"}
    with pytest.raises(ValidationError):
        validate("job-request-v1.schema.json", with_extra)

    malformed_hash = {**fixture, "input_sha256": "ABCDEF"}
    with pytest.raises(ValidationError):
        validate("job-request-v1.schema.json", malformed_hash)


def test_request_fixtures_contain_no_recipient_data_urls_or_binary_payloads():
    for fixture_name in ["issuance-request-v1.json", "verification-request-v1.json"]:
        fixture = load_json(f"fixtures/messages/{fixture_name}")
        serialized = json.dumps(fixture, sort_keys=True).lower()
        assert "recipient" not in serialized
        assert "presigned" not in serialized
        assert "private_key" not in serialized
        assert "https://" not in serialized
        assert "pdf_bytes" not in serialized


def test_job_result_and_nested_evidence_validate_against_shared_refs():
    result = {
        "schema_version": 1,
        "message_type": "job.succeeded",
        "message_id": "20000000-0000-4000-8000-000000000001",
        "job_id": "20000000-0000-4000-8000-000000000002",
        "attempt": 0,
        "output_object_key": "outputs/demo/result.pdf",
        "output_sha256": "a" * 64,
        "recovered_issuance_id": "20000000-0000-4000-8000-000000000003",
        "verification_status": "VERIFIED_INTACT",
        "evidence": {
            "fingerprint_confidence": 0.97,
            "valid_vote_count": 12,
            "analyzed_page_count": 2,
            "manifest_signature_valid": True,
            "exact_file_hash_match": True,
            "integrity_score": 0.99,
            "suspicious_regions": [],
            "limitations": ["geometry_alignment_not_evaluated"],
        },
        "metrics": {
            "processing_ms": 1500,
            "pages_processed": 2,
            "peak_rss_bytes": 104857600,
            "temp_peak_bytes": 2048,
            "cleanup_failures": 0,
        },
        "safe_error_code": None,
        "correlation_id": "20000000-0000-4000-8000-000000000004",
    }
    validate("job-result-v1.schema.json", result)

    invalid = deepcopy(result)
    invalid["evidence"]["fingerprint_confidence"] = 1.01
    with pytest.raises(ValidationError):
        validate("job-result-v1.schema.json", invalid)


def test_metrics_schema_has_exact_five_non_negative_integer_fields():
    schema = load_json("contracts/jsonschema/job-metrics-v1.schema.json")
    expected = {
        "processing_ms",
        "pages_processed",
        "peak_rss_bytes",
        "temp_peak_bytes",
        "cleanup_failures",
    }
    assert set(schema["required"]) == expected
    assert set(schema["properties"]) == expected
    for field in expected:
        assert schema["properties"][field] == {"type": "integer", "minimum": 0}


def test_internal_and_public_manifest_fields_are_separately_frozen():
    internal = load_json("contracts/jsonschema/internal-manifest-v1.schema.json")
    public = load_json("contracts/jsonschema/public-manifest-v1.schema.json")
    assert set(internal["required"]) == {
        "schema_version",
        "issuance_id",
        "document_id",
        "recipient_id",
        "issued_at",
        "source_sha256",
        "output_sha256",
        "fingerprint_algorithm",
        "integrity_algorithm",
        "signing_key_id",
        "retention_policy_id",
    }
    assert set(public["required"]) == {
        "schema_version",
        "issuance_id",
        "issued_at",
        "output_sha256",
        "fingerprint_algorithm",
        "integrity_algorithm",
        "signing_key_id",
    }
    assert {"document_id", "recipient_id", "source_sha256", "retention_policy_id"}.isdisjoint(
        public["properties"]
    )
    assert internal["x-signature"] == {
        "algorithm": "Ed25519",
        "canonicalization": "RFC8785-JCS",
        "scope": "internal-manifest-canonical-bytes",
        "detached": True,
    }
    assert public["x-signature"] == {
        "algorithm": "Ed25519",
        "canonicalization": "RFC8785-JCS",
        "scope": "public-manifest-canonical-bytes",
        "detached": True,
    }


def test_public_manifest_rejects_private_projection_fields():
    public_manifest = {
        "schema_version": 1,
        "issuance_id": "30000000-0000-4000-8000-000000000001",
        "issued_at": "2026-08-27T12:00:00Z",
        "output_sha256": "b" * 64,
        "fingerprint_algorithm": "splitbind-fingerprint-v1",
        "integrity_algorithm": "splitbind-integrity-v1",
        "signing_key_id": "test-signing-key-v1",
    }
    validate("public-manifest-v1.schema.json", public_manifest)

    for private_field in ["document_id", "recipient_id", "input_object_key", "email"]:
        invalid = {**public_manifest, private_field: "not-public"}
        with pytest.raises(ValidationError):
            validate("public-manifest-v1.schema.json", invalid)
