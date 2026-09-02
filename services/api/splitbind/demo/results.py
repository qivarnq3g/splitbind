from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IssuanceProcessingResult:
    organization_id: UUID
    job_id: UUID
    issuance_id: UUID
    input_sha256: str
    output_sha256: str
    output_object_key: str
    algorithm_label: str
    candidate_identifier: str
    canonical_canvas: tuple[int, int]
    pages_processed: int
    processing_ms: int
    limitations: tuple[str, ...]
    cleanup_failures: int


@dataclass(frozen=True, slots=True)
class VerificationProcessingResult:
    organization_id: UUID
    job_id: UUID
    verification_id: UUID
    status: str
    recovered_issuance_id: UUID | None
    input_sha256: str
    algorithm_label: str
    decode_status: str
    fingerprint_confidence: float
    valid_vote_count: int
    exact_file_hash_match: bool
    manifest_signature_valid: bool | None
    pages_analyzed: int
    processing_ms: int
    limitations: tuple[str, ...]
    cleanup_failures: int
