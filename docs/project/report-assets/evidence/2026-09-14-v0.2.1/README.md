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

## Tám phép thử truy vết

Cấp phát trên hệ thống thật, tải bản cấp phát về, biến đổi rồi nộp lại qua đúng biểu mẫu
xác minh. Bốn vật mang khác nhau để không kết luận dựa trên một loại ảnh duy nhất.

| Tệp | Vật mang | Phép biến đổi | Kết quả |
|---|---|---|---|
| `traced-control-lossless.jpg` | Ảnh nền phẳng | Mã hoá lại PNG, điểm ảnh giữ nguyên | Truy được nguồn dù mã băm khác |
| `not-traced-jpeg-q70.jpg` | Ảnh nền phẳng | Nén JPEG 70 | Không truy được |
| `not-traced-resize-075-jpeg-q70.jpg` | Ảnh nền phẳng | Thu nhỏ 0.75 rồi nén JPEG 70 | Không truy được |
| `not-traced-textured-jpeg-q70.jpg` | Trang chữ dày, nhiều kết cấu | Nén JPEG 70 | Không truy được |
| `not-traced-resize-075-lossless.jpg` | Trang chữ dày, nhiều kết cấu | Thu nhỏ 0.75, không nén | Không truy được |
| `not-traced-pdf-page-jpeg-q70.jpg` | Trang render từ PDF đã cấp phát | Nén JPEG 70 | Không truy được |
| `not-traced-screenshot-distorted-issue.jpg` | Trang chữ dày, cấp phát ở 1400 x 1980 | Chụp màn hình 1920 x 1080, thu nhỏ 0.545, viền đen | Không truy được |
| `traced-screenshot-canonical-*.jpg` | Ảnh chuyển sắc, cấp phát ở đúng 1152 x 2304 | Chụp màn hình 1920 x 1080, thu nhỏ 0.469, viền đen | **Truy được nguồn** |

Hai hàng cuối chứng minh hệ thống truy được ảnh chụp màn hình thu nhỏ hơn một nửa. Chúng
khác nhau ở hai biến cùng lúc nên chưa quy được nguyên nhân; phép đo tách biến ở Mục
4.2.4.5 của báo cáo cho thấy biến quyết định là vật mang, không phải kích thước cấp phát.

`traced-screenshot-canonical-headline.jpg` còn cho thấy một khiếm khuyết giao diện: dòng
kết luận lớn ghi "Chưa đủ bằng chứng xác minh" trong khi bảng chi tiết ở
`traced-screenshot-canonical-matched.jpg` ghi đúng mã hồ sơ cấp phát đã khớp.

Ảnh `traced-control-lossless.jpg` được đưa vào báo cáo thành Hình 4.4, bản đầy đủ nằm ở
`../../figures/ui-verification-traced.png`.

## Chi tiết kỹ thuật trên trang kết quả

| Tệp | Nội dung |
|---|---|
| `verification-detail-panel.jpg` | Panel chi tiết, thuật ngữ đã đổi thành "Chữ ký manifest" |
| `verification-scope-with-tracing.jpg` | Câu thông báo phạm vi đã nói tới việc đọc thủy vân |
