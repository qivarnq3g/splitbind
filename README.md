# SplitBind

SplitBind là hệ thống truy vết toàn vẹn văn bản dành cho bài tập lớn môn An toàn thông tin của Nhóm 9. Hệ thống cấp một dấu vân tay riêng cho từng bản PDF gửi tới người nhận, sau đó hỗ trợ xác minh nguồn phát hành và dấu hiệu chỉnh sửa trên tài liệu nghi vấn.

> Trạng thái: đang ở giai đoạn đặc tả thiết kế. Repository chưa chứa mã ứng dụng chạy được.

## Chức năng lõi

- Cấp phát PDF có robust fingerprint riêng cho từng người nhận
- Phát hiện và hỗ trợ định vị thay đổi bằng semi-fragile watermark
- Xác thực hồ sơ phát hành bằng manifest SHA-256 ký Ed25519
- Trả kết quả kèm mức tin cậy, giới hạn bằng chứng và audit log

## Kiến trúc dự kiến

- React, TypeScript và Vite cho giao diện
- Django REST Framework cho API và control plane
- RabbitMQ cùng transactional outbox cho hàng đợi công việc
- Rust cho worker xử lý PDF và ảnh trong production
- Python cho prototype, test vector và benchmark nghiên cứu
- PostgreSQL, Cloudflare R2, Caddy và Docker Compose

Thiết kế ưu tiên tính đúng đắn, bảo mật và khả năng tái lập, đồng thời giới hạn nghiêm ngặt RAM, dung lượng tạm và thời gian lưu dữ liệu để phù hợp hạ tầng miễn phí.

## Tài liệu

- [Đặc tả thiết kế production](docs/superpowers/specs/2026-08-13-splitbind-production-design.md)

Tài liệu môn học, thư trao đổi với giảng viên và thông tin thiết bị thành viên được lưu cục bộ, không thuộc phạm vi repository.

## Nguyên tắc an toàn

- Không commit dữ liệu cá nhân, tài liệu thật, secret hoặc khóa production
- Không khẳng định watermark là bằng chứng tuyệt đối về người gây rò rỉ
- Không đưa PDF vào message queue; queue chỉ truyền định danh và metadata tối thiểu
- Mọi đường xử lý thành công, lỗi, timeout và hủy đều phải dọn file tạm
- Chỉ triển khai sau khi đặc tả được nhóm duyệt và có kế hoạch kiểm thử tương ứng

## Giấy phép

Chưa cấp giấy phép mã nguồn mở. Mọi quyền được bảo lưu cho nhóm dự án cho đến khi nhóm thống nhất giấy phép khác.
