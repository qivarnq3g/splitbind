const MESSAGES: Record<string, string> = {
  DEMO_PDF_PAGE_LIMIT:
    "Tệp có nhiều trang hơn mức hệ thống xử lý được. Chọn tệp ngắn hơn hoặc tách bớt trang rồi thử lại.",
  DEMO_PDF_FILE_LIMIT:
    "Tệp vượt quá dung lượng cho phép. Chọn tệp nhỏ hơn rồi thử lại.",
  DEMO_INPUT_FILE_LIMIT:
    "Tệp vượt quá dung lượng cho phép. Chọn tệp nhỏ hơn rồi thử lại.",
  DEMO_PDF_RASTER_LIMIT:
    "Tổng diện tích các trang vượt ngân sách xử lý ảnh. Tệp có trang khổ lớn hoặc độ phân giải cao bất thường.",
  DEMO_INPUT_RASTER_LIMIT:
    "Tổng diện tích các trang vượt ngân sách xử lý ảnh. Tệp có trang khổ lớn hoặc độ phân giải cao bất thường.",
  DEMO_PDF_ENCRYPTED:
    "Tệp PDF đang được đặt mật khẩu hoặc hạn chế quyền. Gỡ bảo vệ rồi tải lại.",
  DEMO_PDF_INVALID:
    "Không đọc được cấu trúc tệp PDF. Tệp có thể hỏng hoặc không phải PDF hợp lệ.",
  DEMO_INPUT_FORMAT_INVALID:
    "Định dạng tệp không được chấp nhận cho thao tác này.",
  DEMO_IMAGE_INVALID:
    "Không đọc được tệp ảnh. Ảnh có thể hỏng hoặc ở định dạng không hỗ trợ.",
  DEMO_PDF_RENDER_FAILED:
    "Hệ thống không dựng được ảnh trang từ tệp này. Thử lại với bản PDF khác của cùng tài liệu.",
  DEMO_PDF_OUTPUT_FAILED:
    "Hệ thống không ghi được tệp kết quả. Hãy thử lại.",
  DEMO_INPUT_CHECKSUM_MISMATCH:
    "Tệp nhận được không khớp mã băm đã khai báo. Tải lại tệp rồi thử lần nữa.",
  DEMO_JOB_DEADLINE_EXCEEDED:
    "Quá trình xử lý vượt thời gian cho phép. Tệp nhỏ hơn sẽ xử lý kịp.",
  DEMO_JOB_CANCELLED: "Công việc đã bị hủy.",
  DEMO_MODE_DISABLED: "Tính năng này hiện đang tắt trên bản đang chạy.",
  DEMO_STORAGE_UNAVAILABLE:
    "Kho lưu trữ tạm thời không phản hồi. Thử lại sau ít phút.",
  DEMO_INPUT_STORAGE_FAILED:
    "Không đọc được tệp từ kho lưu trữ. Tải lại tệp rồi thử lần nữa.",
  DEMO_INPUT_STORAGE_REJECTED:
    "Kho lưu trữ từ chối tệp này. Tải lại tệp rồi thử lần nữa.",
  DEMO_OUTPUT_STORAGE_FAILED:
    "Không lưu được tệp kết quả. Hãy thử lại.",
  DEMO_FINGERPRINT_DECODE_FAILED:
    "Không đọc được dấu vết trong tệp. Kết quả chưa đủ căn cứ để kết luận.",
  DEMO_FINGERPRINT_KEY_INVALID:
    "Khóa nhận diện dấu vết không hợp lệ trên bản đang chạy.",
};

const GENERIC =
  "Hệ thống không hoàn tất được công việc này. Hãy thử lại, hoặc gửi mã lỗi bên dưới nếu cần hỗ trợ.";

export function describeJobError(code: string | null | undefined): string | null {
  if (!code) return null;
  return MESSAGES[code] ?? GENERIC;
}
