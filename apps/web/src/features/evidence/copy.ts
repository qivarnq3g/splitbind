import type { components } from "../../api/generated/schema";

export const LIMITATION_COPY: Record<string, string> = {
  no_watermark_not_exclusion: "Không phát hiện watermark không có nghĩa tài liệu chắc chắn không thuộc hệ thống.",
  partial_not_attribution: "Bằng chứng hiện có chưa đủ ngưỡng để gán nguồn phát hành.",
  match_not_actor_proof: "Khớp bản cấp phát không chứng minh người nhận đã sửa, làm rò rỉ hoặc phát tán tài liệu.",
  technical_not_legal: "Đây là tín hiệu kỹ thuật, không phải kết luận pháp lý.",
  "fingerprint.experimental_unreleased_v2": "Dấu vân tay này là ứng viên thử nghiệm và chưa được phát hành.",
  "fingerprint.transformed_attribution_unavailable": "Nhận diện fingerprint sau biến đổi chưa khả dụng.",
  "fingerprint.not_gate_g1_evidence": "Kết quả này chưa phải bằng chứng đạt cổng đánh giá phát hành.",
  "evidence.not_proof_of_leak_edit_or_distribution": "Kết quả không chứng minh ai đã làm rò rỉ, chỉnh sửa hoặc phân phối tài liệu.",
  "integrity.not_evaluated": "Demo không đánh giá watermark toàn vẹn hoặc định vị vùng chỉnh sửa.",
};

export const STATUS_COPY = {
  VERIFIED_INTACT: {
    label: "Đã xác minh toàn vẹn",
    inference: "Các tín hiệu được cung cấp phù hợp với một bản cấp phát hợp lệ và chưa phát hiện thay đổi trong phạm vi đã phân tích.",
  },
  SOURCE_IDENTIFIED_MODIFIED: {
    label: "Khớp nguồn, có dấu hiệu thay đổi",
    inference: "Tín hiệu đủ để liên hệ tài liệu với một bản cấp phát và cho thấy nội dung có thể đã thay đổi; kết quả không xác định người thực hiện hành vi.",
  },
  PARTIAL_EVIDENCE: {
    label: "Bằng chứng một phần",
    inference: "Đã quan sát được dữ liệu watermark nhưng bằng chứng chưa đủ để gán nguồn phát hành.",
  },
  NO_WATERMARK: {
    label: "Không phát hiện watermark",
    inference: "Không phát hiện dữ liệu watermark trong phần tài liệu đã phân tích; kết quả này không loại trừ tài liệu khỏi hệ thống.",
  },
  INVALID_MANIFEST: {
    label: "Manifest không hợp lệ",
    inference: "Hồ sơ chữ ký hoặc thuật toán không qua xác minh, vì vậy không thể dựa vào manifest để kết luận nguồn hay tính toàn vẹn.",
  },
  PROCESSING_FAILED: {
    label: "Xử lý thất bại",
    inference: "Hệ thống chưa tạo được kết quả kiểm chứng từ đầu vào này. Không thể suy luận nguồn phát hành hoặc tính toàn vẹn.",
  },
} as const;

export type VerificationStatus = keyof typeof STATUS_COPY;

type AlgorithmLabel = components["schemas"]["AlgorithmLabelEnum"] | components["schemas"]["NullEnum"] | null | undefined;

const INTEGRITY_NON_EXACT_COPY = {
  label: "Không khớp file đã cấp phát",
  inference: "Tệp không khớp chính xác với bản đã cấp phát.",
} as const;

export function isIntegrityNonExact(
  algorithmLabel: AlgorithmLabel,
  exactFileHashMatch: boolean | null | undefined,
): boolean {
  return algorithmLabel === "integrity_release_v1" && exactFileHashMatch === false;
}

export function verificationCopy(
  status: VerificationStatus,
  algorithmLabel: AlgorithmLabel,
  exactFileHashMatch: boolean | null | undefined,
) {
  if (status === "PROCESSING_FAILED" || status === "INVALID_MANIFEST") return STATUS_COPY[status];
  return isIntegrityNonExact(algorithmLabel, exactFileHashMatch) ? INTEGRITY_NON_EXACT_COPY : STATUS_COPY[status];
}

export const STATUS_LIMITATIONS: Record<VerificationStatus, string[]> = {
  VERIFIED_INTACT: ["match_not_actor_proof", "technical_not_legal"],
  SOURCE_IDENTIFIED_MODIFIED: ["match_not_actor_proof", "technical_not_legal"],
  PARTIAL_EVIDENCE: ["partial_not_attribution", "technical_not_legal"],
  NO_WATERMARK: ["no_watermark_not_exclusion", "technical_not_legal"],
  INVALID_MANIFEST: ["technical_not_legal"],
  PROCESSING_FAILED: ["technical_not_legal"],
};
