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

## Ba phép thử truy vết

Cùng một bản cấp phát, biến đổi ba kiểu rồi đem xác minh lại qua đúng giao diện web.

| Tệp | Phép biến đổi | Kết quả |
|---|---|---|
| `traced-control-lossless.jpg` | Mã hoá lại PNG, điểm ảnh giữ nguyên | Truy được nguồn dù mã băm khác |
| `not-traced-jpeg-q70.jpg` | Nén JPEG chất lượng 70 | Không truy được |
| `not-traced-resize-075-jpeg-q70.jpg` | Thu nhỏ 0.75 rồi nén JPEG 70 | Không truy được |

Ảnh đầu là ảnh quan trọng nhất của cả bộ và được đưa vào báo cáo thành Hình 4.4, bản đầy
đủ nằm ở `../../figures/ui-verification-traced.png`. Hai ảnh sau là kết quả âm tính, giữ
lại vì báo cáo trình bày cả hai chiều. Ảnh mẫu dùng trong phép thử gần như toàn nền phẳng,
tức là vật mang khó nhất, nên hai kết quả âm tính này không so sánh được với số liệu
benchmark đo trên corpus trang tài liệu thật.

## Chi tiết kỹ thuật trên trang kết quả

| Tệp | Nội dung |
|---|---|
| `verification-detail-panel.jpg` | Panel chi tiết, thuật ngữ đã đổi thành "Chữ ký manifest" |
| `verification-scope-with-tracing.jpg` | Câu thông báo phạm vi đã nói tới việc đọc thủy vân |
