export class SafeApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SafeApiError";
  }
}

type ApiErrorBody = { code?: string; detail?: string } | Record<string, string[]>;

const SAFE_CODES: Record<string, string> = {
  UPLOAD_SIZE: "Tệp vượt quá giới hạn cho phép. Chọn tệp nhỏ hơn rồi thử lại.",
  UPLOAD_EXPIRED: "Phiên tải lên đã hết hạn. Tạo lại bản cấp phát.",
  UPLOAD_METADATA_MISMATCH: "Tệp tải lên không khớp thông tin ban đầu. Chọn lại tệp rồi thử lại.",
  PROMOTION_STATE: "Tệp chưa sẵn sàng để cấp phát. Tải lại tệp rồi thử lại.",
  PROMOTION_ALREADY_RESERVED: "Tệp này đã được dùng cho một quy trình khác. Chọn lại tệp rồi thử lại.",
};

export function safeApiMessage(status: number, error: ApiErrorBody | undefined): string {
  if (error && "code" in error && typeof error.code === "string") {
    const mapped = SAFE_CODES[error.code];
    if (mapped) return mapped;
  }
  if (status === 401 || status === 403) return "Phiên đăng nhập không còn quyền thực hiện thao tác này.";
  if (status === 404) return "Không tìm thấy dữ liệu trong phạm vi được cấp quyền.";
  if (status === 409) return "Trạng thái dữ liệu đã thay đổi. Tải lại trang rồi thử lại.";
  if (status === 429) return "Có quá nhiều yêu cầu. Chờ một lát rồi thử lại.";
  if (status >= 500) return "Dịch vụ đang tạm thời không sẵn sàng. Thử lại sau.";
  return "Yêu cầu chưa được chấp nhận. Kiểm tra dữ liệu rồi thử lại.";
}
