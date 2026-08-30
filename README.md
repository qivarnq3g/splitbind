# SplitBind

SplitBind là hệ thống truy vết toàn vẹn văn bản dành cho bài tập lớn môn An toàn thông tin của Nhóm 9. Hệ thống cấp một dấu vân tay riêng cho từng bản PDF gửi tới người nhận, sau đó hỗ trợ xác minh nguồn phát hành và dấu hiệu chỉnh sửa trên tài liệu nghi vấn.

> Trạng thái: MVP đang được triển khai. Repository đã có reference implementation, Django control plane, OpenAPI đã sinh và typed TypeScript client; worker Rust, giao diện React hoàn chỉnh và deployment vẫn chưa hoàn thành.

## Chức năng lõi

- Cấp phát PDF có robust fingerprint riêng cho từng người nhận
- Phát hiện và hỗ trợ định vị thay đổi bằng semi-fragile watermark
- Xác thực hồ sơ phát hành bằng manifest SHA-256 ký Ed25519
- Trả kết quả kèm mức tin cậy, giới hạn bằng chứng và audit log

## Kiến trúc đã chốt

- React, TypeScript và Vite cho giao diện
- Django REST Framework cho API và control plane
- RabbitMQ cùng transactional outbox cho hàng đợi công việc
- Rust cho worker xử lý PDF và ảnh trong production
- Python cho prototype, test vector và benchmark nghiên cứu
- Azure Linux VM chạy Caddy và Docker Compose
- Neon PostgreSQL, Cloudflare R2 và Azure Key Vault cho dữ liệu và bí mật

Server chính là Azure VM `Standard_B2ls_v2`, Debian 13 x86-64, 2 vCPU, 4 GiB RAM và Standard SSD 32 GiB. Compute host đã được cấp phát nhưng phải giữ deallocated cho đến khi có release candidate và budget guardrail đã được xác minh. Website production sẽ dùng `splitbind.qivarn.id.vn`; domain gốc `qivarn.id.vn` vẫn phục vụ hệ thống hiện hữu. Máy Mac cùng Lima chỉ là phương án dự phòng.

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
