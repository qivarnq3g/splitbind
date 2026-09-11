# SplitBind

SplitBind là hệ thống truy vết toàn vẹn văn bản dành cho bài tập lớn môn An toàn thông tin của Nhóm 9. Hệ thống cấp một dấu vân tay riêng cho từng bản PDF gửi tới người nhận, sau đó hỗ trợ xác minh nguồn phát hành và dấu hiệu chỉnh sửa trên tài liệu nghi vấn.

> Trạng thái: **Integrity Release 0.1 đang chạy trên production** tại `splitbind.qivarn.id.vn`.
> Nhánh `main` này chỉ chứa tài liệu và đặc tả; toàn bộ mã ứng dụng nằm ở nhánh `feat/splitbind-mvp`.

## Chức năng lõi

- Cấp phát PDF có robust fingerprint riêng cho từng người nhận
- Phát hiện và hỗ trợ định vị thay đổi bằng semi-fragile watermark
- Xác thực hồ sơ phát hành bằng manifest SHA-256 ký Ed25519
- Trả kết quả kèm mức tin cậy, giới hạn bằng chứng và audit log

## Kiến trúc

Đã triển khai và đang chạy:

- React, TypeScript và Vite cho giao diện
- Django REST Framework cho API và control plane
- Transactional outbox trong PostgreSQL cho hàng đợi công việc; worker là tiến trình Python đọc outbox
- Python cho reference implementation, prototype, test vector và benchmark nghiên cứu
- Azure Linux VM chạy Caddy và Docker Compose (ba dịch vụ: `caddy`, `api`, `worker`)
- Neon PostgreSQL và Cloudflare R2 cho dữ liệu và lưu trữ đối tượng
- Bí mật production nạp qua Docker secret mount chỉ đọc

Kiến trúc mục tiêu, **chưa triển khai**:

- RabbitMQ làm message broker. Hiện chỉ có trong `infra/compose/compose.local.yaml` và `compose.offline.yaml` phục vụ phát triển cục bộ; `compose.production.yaml` không có broker.
- Rust cho worker xử lý PDF và ảnh. Chưa có mã Rust trong repository; worker production hiện là Python.
- Azure Key Vault cho quản lý bí mật. Chưa triển khai; script materialize Key Vault thuộc Task 7 chưa được viết.

Server chính là Azure VM `Standard_B2ls_v2`, Debian 13 x86-64, 2 vCPU, 4 GiB RAM và Standard SSD 32 GiB. Website production chạy tại `splitbind.qivarn.id.vn` với chứng chỉ Let's Encrypt do Caddy cấp tự động; domain gốc `qivarn.id.vn` vẫn phục vụ hệ thống hiện hữu và không bị thay đổi. Máy Mac cùng Lima chỉ là phương án dự phòng.

Thiết kế ưu tiên tính đúng đắn, bảo mật và khả năng tái lập, đồng thời giới hạn nghiêm ngặt RAM, dung lượng tạm và thời gian lưu dữ liệu.

## Tài liệu

- [Đặc tả thiết kế production](docs/superpowers/specs/2026-08-13-splitbind-production-design.md)
- [ADR-001: Kiến trúc production trên Azure](docs/decisions/001-azure-production-architecture.md)
- [Kế hoạch triển khai MVP](docs/superpowers/plans/2026-08-27-splitbind-mvp-master.md)

Tài liệu môn học, thư trao đổi với giảng viên và thông tin thiết bị thành viên được lưu cục bộ, không thuộc phạm vi repository.

## Nguyên tắc an toàn

- Không commit dữ liệu cá nhân, tài liệu thật, secret hoặc khóa production
- Không khẳng định watermark là bằng chứng tuyệt đối về người gây rò rỉ
- Không đưa PDF vào message queue; queue chỉ truyền định danh và metadata tối thiểu
- Mọi đường xử lý thành công, lỗi, timeout và hủy đều phải dọn file tạm
- Chỉ triển khai sau khi đặc tả được nhóm duyệt và có kế hoạch kiểm thử tương ứng

## Giấy phép

Chưa cấp giấy phép mã nguồn mở. Mọi quyền được bảo lưu cho nhóm dự án cho đến khi nhóm thống nhất giấy phép khác.
