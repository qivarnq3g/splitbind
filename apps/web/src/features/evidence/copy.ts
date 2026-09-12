import type { components } from "../../api/generated/schema";

export const LIMITATION_COPY: Record<string, string> = {
  no_watermark_not_exclusion: "Không phát hiện watermark không có nghĩa tài liệu chắc chắn không thuộc hệ thống.",
  partial_not_attribution: "Bằng chứng hiện có chưa đủ ngưỡng để gán nguồn phát hành.",
  match_not_actor_proof: "Khớp bản cấp phát không chứng minh người nhận đã sửa, làm rò rỉ hoặc phát tán tài liệu.",
  technical_not_legal: "Đây là tín hiệu kỹ thuật, không phải kết luận pháp lý.",
  "fingerprint.experimental_unreleased_v2": "Dấu vân tay này là ứng viên thử nghiệm và chưa được phát hành.",
  "fingerprint.transformed_attribution_unavailable": "Nhận diện fingerprint sau biến đổi chưa khả dụng.",
  "fingerprint.recall_below_release_gate":
    "Nhận diện fingerprint sau biến đổi đang bật ở mức nghiên cứu: khi nhận ra thì đúng, nhưng nhiều trường hợp không nhận ra. Không nhận ra không có nghĩa là tệp sai nguồn.",
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

export const INTEGRITY_SCOPE = "Kiểm tra này đối chiếu toàn bộ tệp bằng SHA-256 và xác minh chữ ký của hồ sơ cấp phát trong tổ chức. Không định vị vùng chỉnh sửa hay xác định người chỉnh sửa, làm lộ hoặc phát tán tài liệu.";

export function integrityVerdict(
  status: VerificationStatus,
  exactMatch: boolean | null | undefined,
  signatureValid: boolean | null | undefined,
) {
  if (status === "PROCESSING_FAILED") return {
    ...STATUS_COPY.PROCESSING_FAILED, tone: "error" as const,
    next: "Thử lại với tệp PDF nguồn. Nếu lỗi lặp lại, gửi mã kiểm chứng cho quản trị viên.",
  };
  if (status === "INVALID_MANIFEST" || signatureValid === false) return {
    label: "Hồ sơ cấp phát không hợp lệ",
    inference: "Hồ sơ cấp phát không vượt qua kiểm tra xác thực. Chưa thể xác nhận tính toàn vẹn của tệp.",
    tone: "error" as const,
    next: "Liên hệ đơn vị cấp phát để kiểm tra hồ sơ trước khi sử dụng tài liệu.",
  };
  if (status === "VERIFIED_INTACT" && exactMatch === true && signatureValid === true) return {
    label: "Tệp khớp bản cấp phát",
    inference: "Mã SHA-256 khớp chính xác với bản cấp phát và chữ ký hồ sơ hợp lệ. Tệp không thay đổi so với bản đã cấp phát.",
    tone: "success" as const,
    next: "Giữ nguyên tệp này để đối chiếu khi cần. Lưu mã kiểm chứng cùng hồ sơ tài liệu.",
  };
  if (status === "NO_WATERMARK" && exactMatch === false && signatureValid == null) return {
    label: "Chưa tìm thấy bản cấp phát khớp",
    inference: "Không tìm thấy bản cấp phát có mã SHA-256 trùng với tệp trong tổ chức. Kết quả này chưa đủ để kết luận tệp đã bị chỉnh sửa.",
    tone: "warning" as const,
    next: "Chọn đúng PDF đã tải từ SplitBind, chưa lưu lại hoặc chuyển đổi. Nếu vẫn không khớp, kiểm tra với đơn vị cấp phát.",
  };
  return {
    label: "Chưa đủ bằng chứng xác minh",
    inference: "Chưa xác nhận đồng thời được bản cấp phát khớp và chữ ký hợp lệ. Không thể kết luận tính toàn vẹn của tệp.",
    tone: "warning" as const,
    next: "Kiểm tra các bằng chứng bên dưới và liên hệ đơn vị cấp phát với mã kiểm chứng này.",
  };
}

export function verificationCopy(
  status: VerificationStatus,
  algorithmLabel: AlgorithmLabel,
  exactFileHashMatch: boolean | null | undefined,
  signatureValid?: boolean | null,
) {
  if (algorithmLabel === "integrity_release_v1") return integrityVerdict(status, exactFileHashMatch, signatureValid);
  return STATUS_COPY[status];
}

export const STATUS_LIMITATIONS: Record<VerificationStatus, string[]> = {
  VERIFIED_INTACT: ["match_not_actor_proof", "technical_not_legal"],
  SOURCE_IDENTIFIED_MODIFIED: ["match_not_actor_proof", "technical_not_legal"],
  PARTIAL_EVIDENCE: ["partial_not_attribution", "technical_not_legal"],
  NO_WATERMARK: ["no_watermark_not_exclusion", "technical_not_legal"],
  INVALID_MANIFEST: ["technical_not_legal"],
  PROCESSING_FAILED: ["technical_not_legal"],
};
