# Ảnh chụp ngày 14/09/2026, bản `integrity-v0.2.1`

Chụp tại `https://splitbind.qivarn.id.vn` sau khi bản `integrity-v0.2.1` được đưa lên
vận hành, dựng từ commit `52751f2`. Cửa sổ trình duyệt 1436x840.

## Trang giới thiệu

| Tệp | Nội dung |
|---|---|
| `landing-01-hero.jpg` | Phần mở đầu và mục 02 |
| `landing-02-issuance.jpg` | Mục 03, ba bước nhúng thủy vân, băm và ký |
| `landing-03-verification-boundary.jpg` | Mục 04 và 05, nêu rõ điều hệ thống không kết luận |

## Cấp phát một tài liệu ảnh

| Tệp | Nội dung |
|---|---|
| `issuance-form-image-selected.jpg` | Biểu mẫu đã chọn một tệp PNG, kèm dòng nêu năng lực của hệ thống |
| `issuance-image-result.jpg` | Cấp phát thành công cho tài liệu ảnh |
| `issuance-download-name-png.png` | Đường dẫn tải về do API trả ra, đuôi `.png` và tên `mau-tai-lieu-splitbind-b4401e85.png` |

Ảnh cuối là bằng chứng cho bản vá đuôi tệp: trước `integrity-v0.2.1`, chỗ này là `.pdf`.

## Sáu phép thử truy vết

Cấp phát trên hệ thống thật, tải bản cấp phát về, biến đổi rồi nộp lại qua đúng biểu mẫu
xác minh. Ba vật mang khác nhau để không kết luận dựa trên một loại ảnh duy nhất.

| Tệp | Vật mang | Phép biến đổi | Kết quả |
|---|---|---|---|
| `traced-control-lossless.jpg` | Ảnh nền phẳng | Mã hoá lại PNG, điểm ảnh giữ nguyên | Truy được nguồn dù mã băm khác |
| `not-traced-jpeg-q70.jpg` | Ảnh nền phẳng | Nén JPEG 70 | Không truy được |
| `not-traced-resize-075-jpeg-q70.jpg` | Ảnh nền phẳng | Thu nhỏ 0.75 rồi nén JPEG 70 | Không truy được |
| `not-traced-textured-jpeg-q70.jpg` | Trang chữ dày, nhiều kết cấu | Nén JPEG 70 | Không truy được |
| `not-traced-resize-075-lossless.jpg` | Trang chữ dày, nhiều kết cấu | Thu nhỏ 0.75, không nén | Không truy được |
| `not-traced-pdf-page-jpeg-q70.jpg` | Trang render từ PDF đã cấp phát | Nén JPEG 70 | Không truy được |

Ảnh đầu là ảnh quan trọng nhất của cả bộ và được đưa vào báo cáo thành Hình 4.4, bản đầy
đủ nằm ở `../../figures/ui-verification-traced.png`.

Năm ảnh còn lại là kết quả âm tính và được giữ lại vì chúng bác bỏ chính giả thuyết đầu
tiên của nhóm. Ban đầu nhóm cho rằng ảnh mẫu quá phẳng nên ít chỗ giấu tín hiệu; hai phép
thử sau dùng vật mang nhiều kết cấu hơn hẳn và vẫn trượt. Giả thuyết thứ hai là chỉ nén mới phá tín hiệu, còn thu nhỏ thuần tuý thì phục hồi khung
ảnh sẽ cứu được; hàng thu nhỏ không nén bác bỏ nốt. Kết luận đúng là trên đường đi thật
của sản phẩm, mọi phép biến đổi làm đổi điểm ảnh đều khiến hệ thống mất khả năng truy vết.

## Chi tiết kỹ thuật trên trang kết quả

| Tệp | Nội dung |
|---|---|
| `verification-detail-panel.jpg` | Panel chi tiết, thuật ngữ đã đổi thành "Chữ ký manifest" |
| `verification-scope-with-tracing.jpg` | Câu thông báo phạm vi đã nói tới việc đọc thủy vân |
