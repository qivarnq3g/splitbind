# Ảnh chụp ngày 15/09/2026, bản `integrity-v0.2.3`

Chụp tại `https://splitbind.qivarn.id.vn` sau khi bản `integrity-v0.2.3` được đưa lên vận
hành, dựng từ commit `eebc221`. Cửa sổ trình duyệt 1472x812.

Bản này đổi hai thứ so với `integrity-v0.2.1`: dòng kết luận nói rõ khi hệ thống truy được
nguồn, và hồ sơ tham số thủy vân chuyển sang ứng viên mạnh hơn.

## Ca truy vết thành công

| Tệp | Nội dung |
|---|---|
| `issuance-image-result.jpg` | Cấp phát một ảnh, kèm dòng nêu năng lực của hệ thống |
| `traced-screenshot-headline.jpg` | Dòng kết luận mới: "Truy được nguồn, tệp đã bị biến đổi" |
| `traced-screenshot-matched.jpg` | Bảng chi tiết: "hai giá trị khác nhau" nhưng vẫn ghi đúng mã hồ sơ cấp phát |

Tệp đem xác minh là ảnh chụp màn hình 1920 x 1080 dựng từ chính bản cấp phát, thu nhỏ còn
0,469 và có viền đen. Mã băm khác hẳn mã băm đã ký, nên kết luận chỉ có thể đến từ thủy vân.

Ảnh `traced-screenshot-headline.jpg` là thứ thay thế ảnh cũ trong báo cáo. Trước bản
`integrity-v0.2.2`, chính tình huống này lại hiện "Chưa đủ bằng chứng xác minh", vì hàm
dựng kết luận không có nhánh cho trạng thái truy được nguồn.

## Ca thất bại trên trang văn bản

| Tệp | Nội dung |
|---|---|
| `not-traced-text-page-jpeg-q70.jpg` | Trang chữ phông thật, nén JPEG 70, không truy được |

Đây là phép thử đã bác bỏ dự đoán của nhóm về hồ sơ tham số mới. Trang chữ dùng phông thật,
tỉ lệ điểm tối 9,24 phần trăm, cấp phát rồi nén JPEG chất lượng 70. Hệ thống trả
`insufficient_sync_evidence`, tức khâu đồng bộ không tìm được mẫu pilot, y như trước khi
đổi hồ sơ. Giữ lại vì báo cáo trình bày cả kết quả âm tính.

Số liệu đầy đủ ở Mục 4.3.4 của báo cáo.
