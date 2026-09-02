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
