---
title: "Tìm hiểu và đề xuất Hệ thống truy vết toàn vẹn văn bản"
subtitle: "Bài tập lớn An toàn thông tin — Nhóm 9 — GVHD: TS. Hồ Đăng Thế"
lang: vi
---

# MÀN 1 — ĐẶT VẤN ĐỀ

## Bài toán

- Tài liệu nội bộ rò rỉ qua **chụp màn hình, in–scan, chụp lại điện thoại**
- Chữ ký số bảo vệ **bit thô**: đổi một byte là chữ ký hỏng
- Nhưng kênh rò rỉ thật **luôn** làm mất tính toàn vẹn bit
- Cần một cơ chế sống sót qua kênh tín hiệu, không chỉ kênh số

## Bốn nội dung được giao

1. Lý thuyết kỹ thuật **Digital Watermarking**
2. Ứng dụng watermarking trong **truy vết thay đổi hình ảnh**
3. Ứng dụng **ký số** trong bảo vệ thông tin truy vết
4. **So sánh** với các kỹ thuật xác minh toàn vẹn khác

**Nghịch lý "văn bản vs hình ảnh":** hệ thống render trang PDF thành ảnh rồi nhúng — bắc cầu cả hai.

# MÀN 2 — LÝ THUYẾT WATERMARKING (Yêu cầu 1)

## Phân loại kỹ thuật

- Theo **miền nhúng**: miền không gian vs miền tần số (DCT, DWT, DFT)
- Theo **mục tiêu**: bền vững (robust) / bán mỏng manh (semi-fragile) / mỏng manh
- Theo **khả năng trích xuất**: mù (blind) vs không mù

## Tam giác đánh đổi cốt lõi

**Độ bền ↔ Tính vô hình ↔ Dung lượng**

- Không thể tối ưu đồng thời cả ba
- SplitBind đo được đánh đổi này bằng số thật: PSNR **69,31 → 42,47 dB** khi đổi thế hệ
- Cả hai vẫn trên ngưỡng cổng 38 dB

## Điều chế chỉ số lượng tử (QIM)

- Lượng tử hoá hệ số về lưới chẵn/lẻ theo bit cần nhúng
- Bước lượng tử $\Delta$ quyết định đánh đổi bền ↔ vô hình
- Giải mã **mù**: không cần ảnh gốc
- SplitBind dùng Parity-QIM trên dải trung tần, kết hợp trải phổ 64 chip/bit

# MÀN 3 — TRUY VẾT VÀ TOÀN VẸN (Yêu cầu 2)

## Bài toán A — Truy vết nguồn phát hành

- Payload chuẩn hoá **23 byte**: `"SB"` + version + UUID 16B + CRC-32
- Reed–Solomon GF(256), 16 parity → codeword **39 byte**
- Sửa được tối đa 8 symbol lỗi
- Mỗi tile mang **trọn vẹn** codeword một cách độc lập

## Bài toán B — Phát hiện và định vị sửa đổi

- Thủy vân **bán mỏng manh**, lưới khối 128×128
- Đặc trưng DCT tần thấp + thẻ **HMAC-SHA256** cắt 4 byte
- Phân tán khối đối tác (Partner Ring) chống tấn công giả thẻ
- Cơ chế **fail-safe**: mismatch ≥ 10% ⇒ xoá danh sách nghi vấn

## Kết quả định vị can thiệp

- 48 hàng: 12 trang × 4 loại can thiệp
- **IoU tổng hợp = 0,089981**
- **38/48 hàng kích hoạt fail-safe** ⇒ kéo IoU xuống
- Ranh giới thật của phương pháp semi-fragile dựa khối DCT

# MÀN 4 — KÝ SỐ (Yêu cầu 3)

## Kiến trúc "Nhúng trước, Ký sau"

$$h_{out} = \text{SHA-256}(W(D))$$
$$M = \text{JCS}(\{\dots, \text{output\_sha256}: h_{out}, \dots\})$$
$$S = \text{Ed25519.Sign}(sk, M)$$

Manifest chuẩn tắc **RFC 8785** ⇒ độc lập thư viện tuần tự hoá.

## Giải quyết mâu thuẫn watermark ↔ chữ ký số

Hai cơ chế, hai mô hình đe doạ khác nhau:

- **Chữ ký số** — kênh số nguyên bản, toàn vẹn bit, chống chối bỏ
- **Thủy vân bền vững** — kênh analog/lossy, trích định danh để tra cứu manifest

⇒ Phòng thủ theo chiều sâu, **không** mâu thuẫn

## Ba cấp độ minh bạch trạng thái

| Cấp | Nội dung | Trạng thái |
|---|---|---|
| A | Payload + ECC | `[Implemented]` |
| B | Kiến trúc liên kết watermark ↔ manifest | `[Implemented]` |
| C | Vận hành thực tế | `[Production]` — chỉ toàn vẹn tệp chính xác |

# MÀN 5 — SO SÁNH (Yêu cầu 4)

## Ma trận 7 tiêu chí × 6 kỹ thuật

So sánh: Hash · HMAC · Chữ ký số · Robust WM · Semi-fragile WM · Steganography

Bảy tiêu chí: mục tiêu an ninh · độ bền trước biến đổi · khả năng định vị · độ nhạy từng bit · dung lượng · quản lý khoá · giá trị pháp lý

## Ba cặp tương phản then chốt

- **Watermarking vs Steganography** — công khai sự tồn tại vs giấu sự tồn tại
- **Watermarking vs Chữ ký số** — kênh thị giác vs kênh bit nguyên bản
- **CRC-32 vs HMAC** — lỗi ngẫu nhiên vs toàn vẹn mật mã có khoá

# MÀN 6 — HIỆN THỰC, THỰC NGHIỆM, KẾT LUẬN

## Hệ thống chạy thực tế

- React + TypeScript + Vite · Django REST · worker Python
- Caddy + Docker Compose trên Azure VM, TLS Let's Encrypt tự động
- PostgreSQL (Neon) + lưu trữ đối tượng S3-compatible
- Ảnh container ghim theo **digest bất biến**, không dùng tag động

## Số liệu thực nghiệm đã khoá — thế hệ V1

| Chỉ số | Giá trị |
|---|---|
| PSNR trang PDF | **41,69 dB** |
| SSIM trang PDF | **0,9825** |
| Quy mô benchmark V1 | **32.736 hàng** |
| Tỷ lệ gán sai | **0,00%** (0/682) |
| IoU định vị | **0,089981** |

## Tiến hoá thuật toán V1 → V3

Cùng corpus, cùng cổng, cùng mẫu số:

| Chỉ số | V1 | V3 |
|---|---:|---:|
| JPEG-70 | 0/12 | **9/12** |
| Resize-0.75 | 0/12 | **8/12** |
| Crop-0.25 | 1/3 | **9/12** |
| Lỗi thực thi | 31/682 | **0/352** |

Bốn thay đổi: dải nhúng `HL→LL` · bước lượng tử · đồng bộ 8 giả thuyết · **trải phổ**

## Chẩn đoán nguyên nhân gốc — đóng góp của nhóm

Bộ giải mã chỉ sinh giả thuyết hình học cho **ba** trường hợp: giữ nguyên, co giãn đều, và cắt cúp tại **đúng một tỉ lệ cứng** `0,8660`.

**Tương quan không ngoại lệ trên 286 hàng đo:**

- Có giả thuyết đúng ⇒ **7–11/12**
- Thiếu giả thuyết đúng ⇒ **0–2/12**

Nghịch lý chứng minh: crop **10%** (2/12) tệ hơn crop **25%** (7/12) — vì 25% chính là tỉ lệ được cứng hoá.

## Kiểm chứng: bóc viền letterbox

| Màn hình | Thô | Sau khi bóc viền |
|---|---:|---:|
| **1920×1080** | **0/12** | **9/12** |
| 1366×768 | 0/12 | 0/12 |

- 9/12 **đúng bằng** tỉ lệ resize-0.50
- **Không đổi một tham số nào** của thủy vân
- ~20 dòng tiền xử lý tất định

## Ba lớp thất bại, không phải một

| Lớp | Dấu hiệu | Cách sửa |
|---|---|---|
| Không tạo được ứng viên | `insufficient_sync_evidence` | Chuẩn hoá khung — **đã kiểm chứng** |
| Tạo ứng viên **sai** | `payload_not_detected` + đổi kích thước | Ước lượng tỉ lệ cắt |
| Sóng mang chết | `payload_not_detected`, không đổi kích thước | Giới hạn thật |

⇒ **Hai trong ba lớp không phải vấn đề của thủy vân**

## Kết luận

**Đạt được:** bốn nội dung đề bài, kiểm chứng bằng hệ thống chạy thật, 0 gán sai trên 482 hàng, pregate tái lập được.

**Đóng góp:** chẩn đoán nguyên nhân gốc + phép kiểm chứng có tính tiên đoán (0/12 → 9/12).

**Giới hạn — nói rõ:** thủy vân bền vững **chưa đạt cổng phát hành**, giữ ở tầng nghiên cứu; production chỉ chạy toàn vẹn tệp chính xác. **Không kết quả nào chứng minh danh tính người làm rò rỉ.**

**Hướng tiếp:** chuẩn hoá khung → ước lượng tỉ lệ cắt → hai trục độc lập → chọn sóng mang theo nội dung.
