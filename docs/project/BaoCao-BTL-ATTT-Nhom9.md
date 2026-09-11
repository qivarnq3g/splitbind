---
title: "TÌM HIỂU VÀ ĐỀ XUẤT HỆ THỐNG TRUY VẾT TOÀN VẸN VĂN BẢN"
subtitle: "Báo cáo Bài tập lớn — Môn An toàn thông tin"
author: "Nhóm 9 — Lớp học phần 012012303303"
lang: vi
---

# TÌM HIỂU VÀ ĐỀ XUẤT HỆ THỐNG TRUY VẾT TOÀN VẸN VĂN BẢN

**Báo cáo Bài tập lớn — Môn An toàn thông tin**

| | |
|---|---|
| Đề tài | Tìm hiểu và đề xuất Hệ thống truy vết toàn vẹn văn bản |
| Nhóm thực hiện | Nhóm 9 |
| Lớp học phần | 012012303303 |
| Giảng viên hướng dẫn | TS. Hồ Đăng Thế |
| Hệ thống minh hoạ | SplitBind |

## Phạm vi và quy ước trình bày

Báo cáo bám sát bốn nội dung được giao: lý thuyết kỹ thuật Digital Watermarking; ứng dụng thủy vân trong truy vết thay đổi hình ảnh; ứng dụng ký số trong bảo vệ thông tin truy vết; và so sánh với các kỹ thuật xác minh bảo vệ tính toàn vẹn khác. Bốn nội dung này tương ứng lần lượt với các Chương 2, 3, 4 và 5.

Chương 6 và 7 trình bày hệ thống SplitBind mà nhóm đã hiện thực và đo đạc để kiểm chứng phần lý thuyết. Chương 8 là phần **đề xuất** của nhóm: một chẩn đoán nguyên nhân gốc dựa trên số liệu đo được, kèm phép kiểm chứng đã thực hiện.

Mọi khẳng định kỹ thuật và số liệu trong báo cáo đều được gắn một trong năm nhãn phân định cấp độ tri thức sau, nhằm phân biệt rạch ròi giữa lý thuyết kinh điển, tính năng đã hiện thực, kết quả đo được và giới hạn đã nhận diện:

1. `[Established theory]` — tri thức khoa học kinh điển từ giáo trình, sách chuyên khảo, bài báo khoa học hoặc tiêu chuẩn quốc tế.
2. `[Implemented]` — tính năng hoặc thuật toán đã được cài đặt thành mã nguồn cụ thể.
3. `[Experimentally observed]` — kết quả đo lường sinh ra từ kịch bản benchmark có artifact lưu vết và mã băm SHA-256 xác thực.
4. `[Production]` — tính năng đang hoạt động thực tế trên môi trường máy chủ của phiên bản phát hành hiện hành.
5. `[Limitation]` — giới hạn kỹ thuật đã nhận diện, ranh giới thất bại của thuật toán, hoặc tính năng được chủ động khoá lại.

Nhóm chủ trương công bố giới hạn thay vì che giấu: các kết quả âm tính và các giả thuyết đã bị bác bỏ đều được trình bày đầy đủ, vì chúng là một phần của đóng góp khoa học.

\newpage


# CHƯƠNG 1. GIỚI THIỆU ĐỀ TÀI VÀ QUY ƯỚC NGỮ NGHĨA

### 1.1. Thông tin Đề tài Chính thức
* **Tên đề tài BTL:** Tìm hiểu và đề xuất Hệ thống truy vết toàn vẹn văn bản.
* **Đơn vị thực hiện:** Nhóm 9 - Lớp học phần An toàn thông tin.
* **Bốn yêu cầu cốt lõi của Giảng viên:**
  1. Lý thuyết Kỹ thuật Digital Watermarking.
  2. Ứng dụng watermarking trong truy vết thay đổi hình ảnh.
  3. Ứng dụng ký số trong bảo vệ thông tin truy vết hình ảnh.
  4. So sánh với các kỹ thuật xác minh bảo vệ tính toàn vẹn khác.

### 1.2. Thống nhất Ngữ nghĩa: "Văn bản" (Document) vs "Hình ảnh" (Image)
`[Established theory]` & `[Implemented]`

* **Nghịch lý ban đầu:** Đề tài yêu cầu xây dựng hệ thống truy vết toàn vẹn cho *văn bản*, nhưng các yêu cầu kỹ thuật chi tiết lại yêu cầu nghiên cứu và ứng dụng thủy vân trên *hình ảnh*.
* **Bản chất đường ống xử lý thực tế của SplitBind:**
  1. **Tài liệu PDF là vật chủ nghiệp vụ (Business Document Layer):** Đầu vào và đầu ra của người dùng cuối là các tệp tài liệu số định dạng PDF (`application/pdf`).
  2. **Biểu diễn ảnh trang là vật mang tín hiệu (Signal Representation Layer):** Nhằm hướng tới khả năng chống chịu các kênh rò rỉ ngoại tuyến (in ấn ra giấy, quét lại, chụp màn hình máy tính, chuyển đổi thành ảnh đăng tải lên mạng xã hội), hệ thống chuyển đổi (render) từng trang tài liệu PDF thành mảng điểm ảnh raster hai chiều (kênh độ sáng Luminance) ở độ phân giải xác định (144 hoặc 300 DPI).
  3. **Thủy vân số tác động trên ảnh trang:** Các thuật toán thủy vân số (cả nhúng vết định danh rò rỉ lẫn nhúng thẻ xác thực toàn vẹn) được áp dụng trực tiếp lên biểu diễn ảnh raster của từng trang. Sau khi xử lý tín hiệu, trang ảnh được tái đóng gói trở lại thành tệp PDF hoàn chỉnh.
  4. **Chữ ký số tác động trên toàn văn bản:** Chữ ký số Ed25519 được tạo trên bản tóm lược (manifest) chứa mã băm SHA-256 của toàn bộ tệp PDF phát hành.
* **Phát biểu chuẩn mực dùng xuyên suốt Slide và Báo cáo:**
  > *"Hệ thống truy vết và bảo vệ tính toàn vẹn tài liệu văn bản thông qua kỹ thuật thủy vân số trên biểu diễn ảnh trang (Page-Image Document Watermarking) kết hợp chữ ký số trên hồ sơ cấp phát."*

\newpage

# CHƯƠNG 2. CƠ SỞ LÝ THUYẾT KỸ THUẬT DIGITAL WATERMARKING

### 2.1. Khái niệm và Định nghĩa Chuẩn mực
`[Established theory]` (Giáo trình An toàn Thông tin - HV BCVT & Sách chuyên khảo)

* **Thủy vân số (Digital Watermarking):** Là kỹ thuật nhúng một lượng thông tin số xác định (gọi là thủy vân hoặc watermark - như định danh bản quyền, mã số cấp phát, nhãn toàn vẹn) trực tiếp vào trong dữ liệu đa phương tiện vật chủ (ảnh, tài liệu, âm thanh, video) bằng cách hiệu chỉnh các đặc trưng tín hiệu của vật chủ.
* **Mục tiêu an ninh:** Thông tin thủy vân gắn liền chặt chẽ với nội dung vật chủ; mức độ bền vững (tồn tại qua các phép xử lý tín hiệu) hoặc mức độ mỏng manh (bị phá hủy khi có can thiệp) được thiết kế có chủ đích nhằm phục vụ mục tiêu an ninh cụ thể (như truy vết bản quyền hoặc phát hiện sửa đổi).

### 2.2. Phân loại Kỹ thuật Thủy vân số
`[Established theory]`

#### A. Phân loại theo Miền Nhúng (Embedding Domain)
1. **Miền không gian (Spatial Domain):**
   * *Nguyên lý:* Biến đổi trực tiếp giá trị độ sáng hoặc màu sắc của các điểm ảnh (pixel).
   * *Kỹ thuật tiêu biểu:* LSB (Least Significant Bit - thay thế các bit trọng số thấp nhất), Patchwork, dịch chuyển khối tương quan.
   * *Đặc điểm:* Độ phức tạp tính toán thấp, dung lượng nhúng tiềm năng cao. Độ bền vững phụ thuộc vào cấu trúc của từng lược đồ cụ thể: kỹ thuật LSB điển hình là rất yếu trước các phép xử lý tín hiệu (nén JPEG, lọc làm mịn, biến đổi hình học), trong khi các phương pháp thống kê như Patchwork có khả năng chống chịu tốt hơn trước một số biến dạng tín hiệu tuyến tính.
2. **Miền tần số / Miền biến đổi (Transform Domain):**
   * *Nguyên lý:* Biến đổi ảnh sang miền tần số thông qua các phép biến đổi toán học trực giao, sau đó hiệu chỉnh các hệ số tần số để nhúng tin.
   * *Các phép biến đổi kinh điển:*
     * **DCT (Discrete Cosine Transform):** Biến đổi Cosine rời rạc. Tách ảnh thành các thành phần tần số thấp (năng lượng tập trung), trung bình và cao.
     * **DWT (Discrete Wavelet Transform):** Biến đổi Wavelet rời rạc. Phân rã ảnh theo nhiều mức độ phân giải và định hướng không gian (xấp xỉ LL, chi tiết ngang LH, chi tiết dọc HL, chi tiết chéo HH).
     * **DFT (Discrete Fourier Transform):** Biến đổi Fourier rời rạc. Phép tịnh tiến trong miền không gian làm biến đổi phổ pha nhưng độ lớn phổ biên độ (Fourier magnitude spectrum) có tính chất bất biến đối với phép tịnh tiến.
   * *Vị trí nhúng tối ưu:* Hệ số tần số trung bình (Middle-frequency band). Nhúng vào tần số thấp dễ gây biến dạng trực quan nhận thấy được; nhúng vào tần số cao thường bị các thuật toán nén lossy (như JPEG) loại bỏ. Do đó, dải trung tần là vùng dung hòa / thỏa hiệp phổ biến (standard engineering trade-off) giữa độ vô hình và độ bền vững trong các thiết kế truyền thống.

#### B. Phân loại theo Mức độ Bền vững và Mục đích Sử dụng
1. **Thủy vân bền vững (Robust Watermark):**
   * *Mục đích:* Được thiết kế để sống sót qua một tập hợp xác định các phép biến đổi và tấn công xử lý tín hiệu thông thường (nén lossy, cắt cúp, co giãn, in-scan) trong phạm vi ngưỡng thiết kế, phục vụ truy vết hoặc chứng minh quyền sở hữu.
   * *Ứng dụng:* Bảo vệ bản quyền tác giả (Copyright Protection), truy vết người làm rò rỉ tài liệu (Traitor Tracing / Leak Attribution).
2. **Thủy vân mỏng manh (Fragile Watermark):**
   * *Mục đích:* Được thiết kế để rất nhạy cảm với các sửa đổi ngoài phạm vi cho phép; khi dữ liệu vật chủ bị tác động làm suy biến đặc trưng nhúng, thủy vân bị phá hủy hoặc giải mã sai lệch để cảnh báo có sự can thiệp.
   * *Ứng dụng:* Phục vụ phát hiện can thiệp và xác thực toàn vẹn (Tamper Detection & Content Authentication).
3. **Thủy vân bán mỏng manh (Semi-fragile Watermark):**
   * *Mục đích:* Chấp nhận (sống sót qua) các phép biến đổi bảo toàn nội dung thông thường (nén JPEG nhẹ, chuyển đổi định dạng), nhưng **bị phá hủy và cảnh báo khi có sự can thiệp làm thay đổi ngữ nghĩa nội dung** (sửa chữ số, xóa đoạn văn, chèn con dấu giả).
   * *Ứng dụng:* Kiểm tra tính toàn vẹn và **định vị vùng bị can thiệp sửa đổi (Tamper Detection & Localization)**.

### 2.3. Tam giác Đánh đổi Cốt lõi (The Fundamental Trade-off Triangle)
`[Established theory]` (Cox et al., Digital Watermarking and Steganography)

Trong thiết kế bất kỳ hệ thống thủy vân số nào, tồn tại một ràng buộc đánh đổi kỹ thuật (Engineering / Design Trade-off) giữa ba yếu tố thường cạnh tranh lẫn nhau:

$$\text{Robustness (Độ bền vững)} \longleftrightarrow \text{Imperceptibility / Fidelity (Độ tàng hình)} \longleftrightarrow \text{Capacity (Dung lượng tải trọng)}$$

* **Độ bền vững (Robustness):** Khả năng sống sót và giải mã chính xác của thủy vân sau khi vật chủ trải qua các phép tấn công tín hiệu và biến dạng hình học.
* **Độ tàng hình / Độ trung thực (Imperceptibility / Fidelity):** Mức độ suy giảm chất lượng cảm nhận trực quan của mắt người đối với ảnh sau khi nhúng thủy vân (đo bằng PSNR, SSIM).
* **Dung lượng (Capacity):** Số lượng bit thông tin có thể nhúng thành công trên một đơn vị diện tích tài liệu.
* *Bản chất đánh đổi kỹ thuật:* Khi tăng cường độ nhúng để tăng độ bền vững (Robustness), chất lượng ảnh dễ bị suy giảm (Fidelity giảm). Nếu tăng dung lượng tải trọng (Capacity cao), khoảng cách giữa các trạng thái lượng tử hóa bị thu hẹp, làm giảm khả năng chịu nhiễu. Do đó, kỹ sư an toàn thông tin phải xác định điểm cân bằng phù hợp với mô hình đe dọa cụ thể.

### 2.4. Kỹ thuật Điều chế Chỉ số Lượng tử hóa (QIM - Quantization Index Modulation)
`[Established theory]` (Chen & Wornell, IEEE Transactions on Information Theory, 2001)

* **Nguyên lý:** QIM là phương pháp nhúng thông tin có sự tham gia của vật chủ (Informed Embedding). Thay vì cộng tín hiệu giả ngẫu nhiên vào ảnh (như Spread Spectrum), QIM chia miền giá trị của các hệ số biến đổi thành tập hợp các lưới lượng tử hóa rời rạc (Lattices) so le nhau.
* **Cơ chế Parity-QIM (Lưới chẵn/lẻ):**
  * Để nhúng bit $m \in \{0, 1\}$ vào hệ số $c$, hệ thống điều chỉnh $c$ về điểm lưới gần nhất sao cho:
    $$\text{round}\left(\frac{c}{\Delta}\right) \pmod 2 = m$$
    Trong đó $\Delta$ là bước lượng tử hóa (Quantization Step / Delta).
  * Khi giải mã, phía nhận chỉ cần lượng tử hóa hệ số nhận được và kiểm tra tính chẵn/lẻ của chỉ số lượng tử, hoàn toàn **không cần ảnh gốc (Blind Extraction)**.

\newpage

# CHƯƠNG 3. ỨNG DỤNG THỦY VÂN TRONG TRUY VẾT VÀ TOÀN VẸN HÌNH ẢNH

Nhóm 9 đã tiếp cận và triển khai thực nghiệm cả hai bài toán ứng dụng độc lập trong an toàn thông tin hình ảnh:
1. **Bài toán A:** Ứng dụng Thủy vân bền vững trong Truy vết nguồn phát hành (Traitor Tracing / Source Attribution).
2. **Bài toán B:** Ứng dụng Thủy vân bán mỏng manh trong Phát hiện & Định vị sửa đổi (Tamper Detection & Localization).

---

### 3.1. Bài toán A: Truy vết Nguồn phát hành (Traitor Tracing)
`[Implemented]` & `[Experimentally observed]`

#### A. Cấu trúc Payload Thực tế trong Mã nguồn
`[Implemented]` (Tệp `research/python/src/splitbind_ref/payload.py: L18-L70` & `contracts/algorithm/payload-profile.v1.json`)

* **Tổng chiều dài:** Đúng 23 byte (184 bit nhị phân).
* **Các trường dữ liệu theo hợp đồng chuẩn hóa:**
  1. `magic_ascii`: Chuỗi định danh giao thức 2 byte (`"SB"` - mã hex `0x5342`).
  2. `schema_version`: 1 byte phiên bản giao thức (giá trị = `1` - mã hex `0x01`).
  3. **`issuance_id` (Định danh cấp phát cốt lõi): Đúng 16 byte (128-bit UUID ngẫu nhiên)**. Định danh này ánh xạ duy nhất tới một lần phát hành cho một người nhận cụ thể trong cơ sở dữ liệu.
  4. `crc32`: 4 byte mã kiểm tra dư thừa vòng (CRC-32/ISO-HDLC) tính trên 19 byte đầu (`magic` + `version` + `issuance_id`).
  *(Tổng cộng: $2 + 1 + 16 + 4 = 23\text{ byte}$)*.
* **Lưu ý học thuật về phân định vai trò an ninh giữa các thành phần:**
  * `CRC-32`: Chỉ đóng vai trò phát hiện lỗi ngẫu nhiên trong kênh truyền và giải mã tín hiệu (transmission error detection), giúp bộ giải mã phát hiện các trường hợp sai lệch bit; CRC-32 không dùng khóa và hoàn toàn không cung cấp tính toàn vẹn mật mã hay khả năng chống giả mạo.
  * `HMAC`: Cung cấp cơ chế xác thực nguồn gốc và toàn vẹn có khóa (keyed authentication / integrity) cho các thẻ xác thực trong thuật toán Semi-fragile.
  * `Chữ ký số Ed25519 trên Manifest`: Cung cấp tính toàn vẹn mật mã, xác thực nguồn gốc phát hành và hỗ trợ đặc tính chống chối bỏ kỹ thuật (non-repudiation) khi danh tính và vòng đời khóa ký được quản lý chặt chẽ theo chính sách tin cậy phù hợp. (Lưu ý: Khóa bí mật nhúng thủy vân không tạo ra đặc tính chống chối bỏ).
* **Mã sửa lỗi Reed-Solomon (ECC):** 23 byte thông điệp kết hợp với 16 byte kiểm tra chẵn lẻ Reed-Solomon trên trường $GF(256)$ tạo thành từ mã (codeword) 39 byte, cho phép tự sửa lỗi tối đa 8 ký hiệu byte bị suy biến trong quá trình giải mã.
* *Kiểm chứng thực tế:* Bộ test suite `test_payload.py` vượt qua 9/9 ca kiểm thử về đóng gói, mã hóa và phục hồi nguyên vẹn `issuance_id`.

#### B. Pipeline Nhúng và Trích xuất Thủy vân DWT-DCT-QIM
`[Implemented]` (`dwt_dct_qim.py`)

1. Trang tài liệu PDF được render thành ảnh độ phân giải cao; tách lấy kênh độ sáng (Luminance).
2. Chia ảnh thành các khối vuông (Tile Layout) và sinh vị trí nhúng bằng bộ sinh số giả ngẫu nhiên an toàn mật mã (CSPRNG).
3. Áp dụng biến đổi Haar DWT cấp 1 để trích xuất dải chi tiết.
4. Chia dải chi tiết thành các khối $8 \times 8$ và áp dụng biến đổi DCT 2 chiều.
5. Mã hóa payload cùng mã sửa lỗi Reed-Solomon (khả năng tự sửa lỗi bit) và nhúng vào hệ số DCT bằng Parity-QIM.
6. Trích xuất và lưu mẫu đồng bộ hình học (SyncTemplate) gồm các điểm đặc trưng ORB tự nhiên của trang tài liệu; khi giải mã, bộ giải mã phát hiện các đặc trưng ORB trên trang bị biến dạng và sử dụng thuật toán RANSAC để ước lượng ma trận biến đổi phối cảnh (Homography), hiệu chỉnh và căn chỉnh trang ảnh về tọa độ chuẩn trước khi trích xuất thủy vân.

#### C. Số liệu Thực nghiệm Đo lường Thật từ Benchmark V1
`[Experimentally observed]` (`docs/evaluation/fingerprint-profile-v1.md`)

* **Quy mô thực nghiệm:** 22 trang tài liệu $\times$ 48 cấu hình thuật toán $\times$ 31 kịch bản tấn công = **32.736 hàng thực nghiệm**.
* **Độ trung thực cảm nhận (Imperceptibility):**
  * Giá trị PSNR đo được trên các ứng viên đạt từ **$65.7\text{ dB}$ đến $70.7\text{ dB}$**.
  * Giá trị SSIM đo được đạt từ **$0.9998$ đến $0.9999$**.
  *(Lưu ý: Đây là chỉ số đo lường trên các mảng điểm ảnh thử nghiệm trước khi tấn công của bộ giải mã nghiên cứu).*
* **Tỷ lệ gán sai nguồn (False Attribution Rate):** **0.00% (0 / 682 hàng)** trên toàn bộ 48 ứng viên. Trong 682 trường hợp benchmark đã xét, không quan sát thấy trường hợp false attribution nào (hệ thống trích xuất chính xác định danh người nhận hoặc báo lỗi kiểm tra CRC-32 / Reed-Solomon và từ chối giải mã, không gán nhầm sang định danh người nhận khác).

#### D. Ranh giới Giới hạn Kỹ thuật Thực tế (Limitations)
`[Limitation]`

* Mặc dù được thiết kế theo hướng bền vững (Robust), thuật toán nghiên cứu **chưa đạt tiêu chuẩn bền vững mức độ Production**:
  * **Nén JPEG chất lượng 70 (JPEG-70):** Tỷ lệ giải mã thành công đạt $0 / 12$ ($0\%$). Nén JPEG làm suy biến nặng nề các lưới lượng tử hóa QIM.
  * **Co giãn kích thước 0.75x (Resize-0.75):** Tỷ lệ giải mã thành công đạt $0 / 12$ ($0\%$). Hệ cơ sở DCT vẫn giữ nguyên tính trực giao toán học; tuy nhiên phép co giãn làm thay đổi lưới lấy mẫu không gian (sampling grid), nội suy lại các giá trị điểm ảnh và làm xô lệch ranh giới căn chỉnh (block alignment) của các khối $8 \times 8$, làm biến đổi các hệ số tần số và phá vỡ sự đồng bộ của lưới lượng tử hóa QIM.
  * **Cắt cúp 25% diện tích (Crop-0.25):** Tỷ lệ giải mã phụ thuộc từng ứng viên, dao động từ $10\%$ đến $66\%$. Mẫu đồng bộ ORB gặp khó khăn khi tài liệu có nhiều mảng màu trơn.
* **Kết luận học thuật:** Thuật toán chứng minh tính khả thi của việc nhúng định danh 128-bit với độ trung thực tín hiệu cao trên mảng điểm ảnh, nhưng còn hạn chế trước các biến đổi phi tuyến và nén lossy nặng. Một hướng nghiên cứu tiếp theo có thể xem xét là Deep Watermarking (như kiến trúc HiDDeN, StegaStamp) kết hợp mạng nơ-ron tích chập tự mã hóa (Autoencoder) bên cạnh việc tối ưu hóa bước lượng tử hóa thích nghi theo đặc trưng cục bộ.

---

### 3.2. Bài toán B: Thủy vân Bán mỏng manh Phát hiện & Định vị Sửa đổi (Tamper Localization)
`[Implemented]` & `[Experimentally observed]`

#### A. Kiến trúc Thuật toán Semi-fragile Phân tán
`[Implemented]` (`research/python/src/splitbind_ref/integrity.py`)

1. **Phân vùng ảnh:** Trang tài liệu được chia thành lưới các khối vuông kích thước $128 \times 128$ pixel.
2. **Trích xuất đặc trưng nội dung (Feature Extraction):**
   * Áp dụng DCT trên từng khối $128 \times 128$.
   * Trích xuất 16 hệ số tần số thấp tại tọa độ `[0,0]` đến `[3,3]`.
   * Lượng tử hóa với bước 512.0 để loại bỏ biến động nhiễu nhỏ nhưng giữ lại đặc trưng cấu trúc nội dung.
3. **Tạo thẻ xác thực (Authentication Tag):**
   * Tính toán thẻ 4 byte (Truncated HMAC 32-bit): $\text{Tag} = \text{HMAC-SHA256}(K, \text{Feature} \parallel \text{Index} \parallel \text{Nonce})[0..3]$.
   * *Lưu ý về biên độ an toàn mật mã (Security Margin):* Thẻ HMAC-SHA256 được cắt ngắn xuống 4 byte (32 bit) để phù hợp với dung lượng nhúng giới hạn của từng khối ảnh. Về mặt tiêu chuẩn kỹ thuật, RFC 2104 khuyến nghị thẻ xác thực rút gọn không nên dưới 80 bit; hướng dẫn NIST cho phép cắt ngắn trong các môi trường tài nguyên hạn chế nhưng lưu ý độ dài dưới 64 bit không được khuyến khích rộng rãi cho ứng dụng an ninh cao. Trong prototype nghiên cứu của SplitBind, việc giữ bí mật khóa $K$ ngăn chặn kẻ tấn công tính toán có chủ đích thẻ đúng cho nội dung giả mạo tùy ý; tuy nhiên do độ dài thẻ chỉ là 32 bit, vẫn tồn tại xác suất đoán ngẫu nhiên $1/2^{32} \approx 2.33 \times 10^{-10}$ cho mỗi khối. Đây là giới hạn về biên độ an toàn mật mã của prototype nghiên cứu, không thể xem là mức an ninh hoàn chỉnh cho môi trường sản xuất thực tế.
4. **Phân tán khối đối tác (Partner Region Ring):**
   * Dùng hàm băm có khóa ánh xạ mỗi khối tới 3 khối đối tác khác trên trang tài liệu.
5. **Nhúng thẻ:** Nhúng 3 bản sao của thẻ xác thực vào 3 khối đối tác bằng Parity-QIM ($\Delta = 48.0$).

#### B. Cơ chế Xác minh và Định vị
`[Implemented]`

* Khi kiểm tra, hệ thống trích xuất thẻ từ các khối đối tác và so khớp với thẻ tính lại từ nội dung khối hiện tại.
* Nếu có ít nhất 2 trong 3 bản sao đối tác báo không khớp, khối đó được đánh dấu là khối nghi vấn (`suspicious`) và hệ thống xuất ra tọa độ hình chữ nhật chuẩn hóa `NormalizedRect(x, y, width, height)` để khoanh vùng can thiệp tiềm năng.

#### C. Số liệu Đo lường Thực nghiệm Thật
`[Experimentally observed]` (`docs/evaluation/integrity-profile-v1.md`)

* **Bộ dữ liệu thử nghiệm:** 12 trang tài liệu $\times$ 4 loại tấn công can thiệp = **48 hàng thực nghiệm**.
* **Bốn loại tấn công can thiệp được đánh giá:**
  1. `replace_text`: Thay thế một vùng văn bản (sửa nội dung chữ số/từ ngữ).
  2. `cover_region`: Che khuất một vùng thông tin bằng mảng màu.
  3. `copy_move`: Sao chép một vùng nội dung và dán sang vị trí khác trên trang.
  4. `insert_object`: Chèn thêm một đối tượng/hình ảnh mới vào trang tài liệu.
* **Kết quả đo lường chỉ số IoU (Intersection over Union) thực tế:**
  * **Chỉ số IoU tổng hợp (Aggregate Localization IoU):** **`0.089981` (xấp xỉ 0.09)**.
  * Chi tiết theo từng dạng can thiệp:
    * `copy_move`: $\text{IoU} = \mathbf{0.187500}$ (8 hàng bị kích hoạt giới hạn).
    * `insert_object`: $\text{IoU} = \mathbf{0.117736}$ (9 hàng bị kích hoạt giới hạn).
    * `replace_text`: $\text{IoU} = \mathbf{0.054687}$ (9 hàng bị kích hoạt giới hạn).
    * `cover_region`: $\text{IoU} = \mathbf{0.000000}$ (12/12 hàng bị kích hoạt giới hạn).

#### D. Giải thích Nguyên nhân Kỹ thuật và Giới hạn Thực nghiệm
`[Limitation]` & `[Established theory]`

* **Không được dùng từ "định vị tốt" hay "chính xác cao":** Kết quả IoU ~ 0.09 là mức độ nhận diện khiêm tốn ở giai đoạn nghiên cứu ban đầu.
* **Nguyên nhân chính dẫn đến IoU ~ 0.09 (Cơ chế Fail-safe):**
  * Thuật toán cài đặt chính sách bảo vệ an toàn nghiêm ngặt: Khi phát hiện tỷ lệ khối không khớp $\ge 10\%$ trên toàn trang (`mismatch_ratio >= 0.10`), hệ thống kích hoạt cơ chế nhận diện nén mạnh (`strong_compression`) hoặc lỗi hình học (`geometry_failure`).
  * Khi cơ chế này kích hoạt, hệ thống **chủ động xóa danh sách vùng nghi vấn (`suspicious = ()`)** để không đưa ra bản đồ định vị sai lệch cho người dùng.
  * Trong thực nghiệm, do các phép tấn công can thiệp chiếm diện tích đáng kể, **38 trên tổng số 48 hàng thử nghiệm đã kích hoạt cơ chế hạn chế này**, làm giảm mạnh giá trị IoU trung bình toàn bộ tập mẫu.
* **Ý nghĩa học thuật:** Kết quả thực nghiệm phản ánh trung thực năng lực và ranh giới kỹ thuật thực tế của phương pháp Semi-fragile phân tán dựa trên khối DCT truyền thống: mô hình minh chứng quy trình phát hiện và định vị can thiệp trên ảnh trang tài liệu, nhưng độ chính xác định vị hình học (IoU) còn rất hạn chế trong điều kiện can thiệp diện tích lớn do bị chi phối bởi cơ chế fail-safe bảo vệ trước nén mạnh. Ranh giới này khẳng định sự cần thiết của các nghiên cứu sâu hơn về phân rã đặc trưng đa tỉ lệ hoặc mạng nơ-ron học sâu trong bài toán bảo vệ tính toàn vẹn hình ảnh.

\newpage

# CHƯƠNG 4. ỨNG DỤNG CHỮ KÝ SỐ TRONG BẢO VỆ THÔNG TIN TRUY VẾT

### 4.1. Phân định Ba Cấp độ Kiến trúc (Bắt buộc không đánh đồng)
`[Established theory]`, `[Implemented]` & `[Production]`

Để bảo vệ bài báo cáo trước hội đồng chuyên môn, nhóm phân định rạch ròi ba cấp độ:

* **Cấp độ A (Payload Layer):** Thủy vân số mang định danh nhị phân là mã số cấp phát `issuance_id` (128-bit UUID).
* **Cấp độ B (Architectural Linkage Layer):** Về mặt kiến trúc và cơ sở dữ liệu, `issuance_id` là khóa chính (`primary key`) liên kết trực tiếp tới bản ghi cấp phát (`Issuance Record`), từ đó truy xuất Manifest đã được ký số Ed25519 và thông tin người nhận tài liệu.
* **Cấp độ C (Production Capability Layer):** Trên môi trường vận hành thực tế (Production Release 0.1), hệ thống áp dụng cơ chế xác thực toàn vẹn tệp chính xác (Exact-file integrity qua SHA-256) và **chưa kích hoạt bộ trích xuất thủy vân tự động trên server**.

---

### 4.2. Kiến trúc Hồ sơ Toàn vẹn (Signed Manifest)
`[Implemented]` & `[Production]` (Tệp `services/api/splitbind/release/manifest.py: L58-L120`)

Hệ thống không ký trực tiếp lên file PDF nhị phân, mà sử dụng mô hình **Hồ sơ Toàn vẹn Chuẩn hóa (Signed Manifest)** nhằm thiết lập liên kết mật mã (cryptographic binding) chặt chẽ giữa tài liệu phát hành và các siêu dữ liệu truy vết nghiệp vụ (`issuance_id`, `recipient_id`, `source_sha256`, `output_sha256`, `signing_key_id`...), được chuẩn tắc hóa qua RFC 8785 và ký bằng Ed25519:

```
+-----------------------------------------------------------------------------+
|                          INTERNAL MANIFEST PAYLOAD                          |
|  - schema_version: 1                                                        |
|  - issuance_id: "de5cf342-faf4-4cc7-a581-f8899467bc13" (Khóa liên kết)     |
|  - recipient_id: "89904907-4a28-4bdb-853d-cb4fa783290c" (Người nhận)       |
|  - source_sha256: Hash tệp gốc ban đầu                                      |
|  - output_sha256: Hash tệp sau khi cấp phát                                 |
|  - signing_key_id: "key-integrity-20260908-01"                             |
+-----------------------------------------------------------------------------+
                                       │
                                       ▼
                       RFC 8785 JSON Canonicalization (JCS)
             (Tạo chuỗi nhị phân UTF-8 xác định, bất biến thứ tự key)
                                       │
                                       ▼
                         Ed25519 Private Key Signing
                                       │
                                       ▼
               {"algorithm": "Ed25519", "signature": "Base64..."}
```

* **Vai trò của SHA-256:** Bảo vệ tính toàn vẹn bit thô của tài liệu nguồn và tài liệu phát hành (`source_sha256`, `output_sha256`). Dưới các giả định an toàn mật mã của SHA-256 (hiệu ứng thác lũ và tính kháng va chạm), bất kỳ sự thay đổi bit nào trên tệp PDF đều được kỳ vọng về mặt thống kê sẽ tạo ra bản tóm lược (digest) khác biệt hoàn toàn.
* **Vai trò của Ed25519:** Chữ ký số hiệu năng cao trên đường cong Edwards Curve 25519 (RFC 8032). Ký trên biểu diễn chuẩn hóa RFC 8785 để xác thực nguồn gốc cơ quan phát hành và bảo vệ tính toàn vẹn của hồ sơ truy vết. Về mặt mật mã học, chữ ký số cung cấp đặc tính chống chối bỏ kỹ thuật (cryptographic non-repudiation); giá trị chứng cứ pháp lý ràng buộc trong thực tế phụ thuộc vào quy trình định danh chủ thể, quản lý khóa riêng và chính sách chứng thư theo khuôn khổ pháp luật hiện hành.
* **Chuẩn hóa RFC 8785 JCS:** Tạo biểu diễn JSON xác định / chuẩn tắc (canonical representation) độc lập với thư viện tuần tự hóa, bảo đảm đầu vào của hàm băm và chữ ký số luôn ổn định, lặp lại được (deterministic input for hashing and signing).

---

### 4.3. Giải quyết "Mâu thuẫn giữa Thủy vân số và Chữ ký số"
`[Established theory]` (Giải quyết thắc mắc của Giảng viên TS. Hồ Đăng Thế)

* **Vấn đề Giảng viên nêu ra:** *"Chữ ký số đòi hỏi tính toàn vẹn từng bit (1 bit đổi là hỏng chữ ký). Thủy vân số lại chủ động làm thay đổi điểm ảnh/dữ liệu của tệp. Hai kỹ thuật này có mâu thuẫn triệt tiêu lẫn nhau không?"*
* **Lời giải kỹ thuật của Nhóm 9 (Nguyên lý Phân tầng Trách nhiệm):**
  1. **Không có mâu thuẫn về thứ tự thực thi trong kiến trúc tích hợp đề xuất:** Quy trình cấp phát nhúng thủy vân vào tài liệu trước, sau đó mới tính toán mã băm SHA-256 trên tài liệu đã mang thủy vân, đóng gói vào hồ sơ Manifest và thực hiện ký số Ed25519 trên biểu diễn chuẩn tắc RFC 8785:
     $$h_{\text{output}} = \text{SHA-256}(W(D))$$
     $$M = \text{JCS}(\{\text{"schema\_version"}: 1, \text{"issuance\_id"}: \text{id}, \dots, \text{"output\_sha256"}: h_{\text{output}}, \dots\})$$
     $$S = \text{Ed25519.Sign}(sk, M)$$
     *(Lưu ý ngữ cảnh triển khai: Công thức trên mô tả **Kiến trúc tích hợp đề xuất** cho toàn hệ thống. Phiên bản Production Release 0.1 hiện hành thực hiện ký Manifest trên tệp cấp phát nguyên bản, trong khi đường ống nhúng/trích xuất thủy vân bền vững $W(D)$ hiện được hoàn thiện ở tầng mã nguồn tham chiếu nghiên cứu).*
     Chữ ký số bảo vệ tính toàn vẹn và chống giả mạo của hồ sơ cấp phát chứa mã băm của văn bản đã mang thủy vân dưới các giả định an toàn mật mã của SHA-256 và Ed25519.
  2. **Giải quyết phân kỳ về mô hình đe dọa (Threat Model):**
     * **Kênh toàn vẹn số (Digital / Exact Channel):** Nếu tài liệu được truyền qua kênh số nguyên bản, hệ thống dùng **Mã băm SHA-256 + Chữ ký số Ed25519 trên Manifest** để xác minh rằng biểu diễn nhị phân của tệp nhận được khớp hoàn toàn với bản tóm lược (digest) đã ký, dưới các giả định an toàn về tính kháng va chạm của SHA-256 và tính không thể giả mạo của Ed25519.
     * **Kênh rò rỉ biến đổi (Analog / Lossy Leak Channel):** Nếu tài liệu bị in ra giấy, chụp màn hình, hoặc nén gửi qua mạng xã hội, tệp bị biến đổi các byte nhị phân thô nên mã băm của tệp nghi vấn sẽ không còn khớp với `output_sha256` ghi trong Manifest. Bản thân chữ ký Ed25519 trên Manifest gốc vẫn hoàn toàn hợp lệ (chứng minh Manifest không bị giả mạo), nhưng giá trị hash trong đó xác nhận tệp nghi vấn không phải là tệp nguyên bản phát hành. Về mặt lý thuyết thiết kế, **Thủy vân số bền vững (Robust Watermark)** được kỳ vọng đóng vai trò là cơ chế chủ động (proactive) sống sót qua biến đổi tín hiệu để trích xuất lại `issuance_id`, từ đó làm cầu nối đối chiếu ngược về Manifest gốc đã ký số trong cơ sở dữ liệu. Tuy nhiên, cần phân định rõ ràng giữa **mục tiêu thiết kế lý thuyết** và **năng lực thực nghiệm hiện tại**: prototype nghiên cứu của SplitBind mới chỉ kiểm chứng thực nghiệm khả năng khôi phục một phần dưới phép cắt cúp Crop-0.25 (tỷ lệ giải mã 10% - 66%) và thất bại trước JPEG-70 cũng như Resize-0.75 (0/12), do đó được giữ ở tầng nghiên cứu để tiếp tục hoàn thiện. (Bên cạnh thủy vân, các kỹ thuật điều tra số khác như perceptual hashing, đối soát OCR văn bản cũng có thể hỗ trợ nhưng thủy vân nhúng sẵn định danh trực tiếp trong nội dung ảnh).
  * **Kết luận:** Hai cơ chế không triệt tiêu nhau mà tạo thành **Hai tầng phòng thủ bổ trợ nhau (Defense-in-Depth)**.

---

### 4.4. Minh bạch Ngữ nghĩa Trạng thái trên Production (`NO_WATERMARK`)
`[Production]` & `[Limitation]`

* Trên backend API, trạng thái tra cứu mã băm không khớp trả về mã enum nội bộ là `NO_WATERMARK` kèm thông điệp hạn chế `integrity.transformed_attribution_unavailable`.
* **Trên giao diện Web người dùng (`apps/web`):** Hệ thống không dùng từ "Không có watermark", mà hiển thị chuẩn mực:
  * Nhãn: **"Chưa tìm thấy bản cấp phát khớp"**.
  * Diễn giải: *"Không tìm thấy bản cấp phát có mã SHA-256 trùng với tệp trong tổ chức. Kết quả này chưa đủ để kết luận tệp đã bị chỉnh sửa."*
  * Thông báo phạm vi: *"Kiểm tra này đối chiếu toàn bộ tệp bằng SHA-256 và xác minh chữ ký của hồ sơ cấp phát trong tổ chức. Không định vị vùng chỉnh sửa hay xác định người chỉnh sửa, làm lộ hoặc phát tán tài liệu."*
* Điều này chứng minh tính trung thực kỹ thuật, không ngụy tạo việc đã chạy bộ quét thủy vân trên production khi thực tế chỉ kiểm tra tính toàn vẹn tệp chính xác.

\newpage

# CHƯƠNG 5. SO SÁNH CÁC KỸ THUẬT XÁC MINH BẢO VỆ TÍNH TOÀN VẸN

`[Established theory]` (Tổng hợp từ Giáo trình William Stallings, Giáo trình Mật mã học & Tài liệu Steganography)

### 5.1. Bảng Ma trận So sánh Đa chiều Toàn diện (7 Tiêu chí $\times$ 6 Kỹ thuật)

| Tiêu chí So sánh | Hàm băm Mật mã (Cryptographic Hash) | Mã xác thực Thông điệp (HMAC / MAC) | Chữ ký số (Digital Signature) | Thủy vân Bền vững (Robust Watermark) | Thủy vân Bán mỏng manh (Semi-fragile WM) | Giấu tin Bí mật (Steganography) |
|---|---|---|---|---|---|---|
| **1. Mục tiêu An ninh Chính** | Kiểm tra toàn vẹn bit thô (đối soát nguyên bản, phát hiện lỗi). | Xác thực nguồn gốc và tính toàn vẹn thông điệp giữa các bên chia sẻ khóa. | Xác thực nguồn gốc phát hành, toàn vẹn bit, chống chối bỏ. | Truy vết rò rỉ (traitor tracing), bảo vệ bản quyền qua kênh lossy. | Phát hiện can thiệp và định vị vùng bị sửa đổi nội dung trên ảnh. | Giấu sự tồn tại của kênh liên lạc bí mật trong vật mang. |
| **2. Độ Bền trước Nén/Biến đổi** | Không chịu được biến đổi nếu yêu cầu exact match: một thay đổi nhỏ được kỳ vọng tạo digest khác. | Không chịu được biến đổi thông điệp: tag cũ sẽ không còn xác minh cho thông điệp mới dưới giả định an toàn của MAC. | **Không:** Phép xác minh tệp thất bại khi có bất kỳ biến đổi byte nào (digest không khớp). | **Cao:** Thiết kế để sống sót qua nén lossy, crop, resize, in-scan trong ngưỡng. | **Trung bình / Chọn lọc:** Bền trước nén nhẹ; báo động khi sửa nội dung. | **Thấp:** Thường bị phá hủy khi vật mang bị nén lại hoặc biến đổi. |
| **3. Khả năng Định vị Vùng Sửa** | Không hỗ trợ (chỉ biết mã băm không khớp). | Không hỗ trợ (chỉ biết thẻ MAC không hợp lệ). | Không hỗ trợ (chỉ biết chữ ký không hợp lệ). | Không hỗ trợ (chỉ giải mã định danh nhúng). | **Có hỗ trợ:** Xuất tọa độ vùng nghi vấn. | Không hỗ trợ. |
| **4. Tính Nhạy cảm Từng Bit** | Rất nhạy với thay đổi bit, có hiệu ứng thác lũ (avalanche effect): bất kỳ thay đổi nhỏ nào đều được kỳ vọng về mặt thống kê sẽ tạo ra bản tóm lược (digest) khác biệt hoàn toàn. | Thay đổi thông điệp làm thẻ MAC hợp lệ cũ không còn xác minh được, dưới các giả định an toàn của hàm băm và HMAC. | Thay đổi biểu diễn được ký làm phép xác minh chữ ký số thất bại, dưới các giả định an toàn của thuật toán ký. | Rất thấp (chống chịu biến đổi tín hiệu trong ngưỡng thiết kế). | Có chọn lọc (bỏ qua nhiễu nhẹ, nhạy với sửa ngữ nghĩa). | Trung bình đến cao (nhạy cảm với tái lượng tử hóa). |
| **5. Dung lượng Tải trọng** | Cố định (SHA-256: 32 B, SHA-512: 64 B). | Cố định theo hàm băm nền (HMAC-SHA256: 32 B, có thể cắt ngắn thẻ). | Cố định theo thuật toán (Ed25519: 64 B; RSA-2048: 256 B). | Rất nhỏ (vài byte đến vài chục byte; SplitBind: 23 bytes). | Nhỏ đến trung bình (thẻ xác thực theo khối $128 \times 128$). | Linh hoạt theo thiết kế (tối ưu hóa đánh đổi giữa dung lượng và khả năng chống phân tích ẩn mật / steganalysis). |
| **6. Yêu cầu Quản lý Khóa** | Không cần khóa (Unkeyed primitive). | Khóa đối xứng bí mật (Symmetric Shared Key). | Cặp khóa bất đối xứng (Private/Public). Phân phối qua PKI CA, pinning hoặc Web of Trust. | Có thể dùng khóa/seed tùy thiết kế; SplitBind dùng secret seed/key để chọn vị trí nhúng. | Khóa đối xứng HMAC tạo thẻ và khóa định tuyến đối tác (Ring Key). | Có thể dùng stego-key tùy lược đồ; cũng tồn tại phương pháp không dùng khóa. |
| **7. Giá trị Pháp lý / Chống Chối bỏ** | Không có tính chứng thực nguồn gốc hay chống chối bỏ. | Không có tính chống chối bỏ (bên nhận có cùng khóa có thể tự tạo MAC). | **Cung cấp tính chống chối bỏ mật mã học;** giá trị pháp lý phụ thuộc quản lý khóa và luật sở tại. | Bằng chứng kỹ thuật hỗ trợ điều tra số nội bộ; cần bằng chứng bổ trợ. | Bằng chứng kỹ thuật định vị vùng sửa đổi phục vụ giám định số. | Không có giá trị chứng cứ pháp lý công khai. |

---

### 5.2. Phân tích Tương phản Chuyên sâu Giữa các Cặp Kỹ thuật

#### A. Thủy vân số (Watermarking) vs Giấu tin Bí mật (Steganography)
* **Điểm tương đồng:** Cùng sử dụng kỹ thuật nhúng dữ liệu vào vật mang đa phương tiện mà không làm thay đổi cảm nhận trực quan của con người.
* **Sự khác biệt cốt lõi:**
  * *Steganography:* Mục tiêu tối thượng là **giấu sự tồn tại của hành vi truyền tin** (kẻ nghe lén không được biết có thông điệp ẩn). Các yếu tố dung lượng (capacity), khả năng chống phân tích ẩn mật (steganalysis resistance) và độ bền vững (robustness) là các bài toán đánh đổi phụ thuộc vào mục tiêu thiết kế của từng sơ đồ; nếu kênh truyền bị can thiệp làm mất dữ liệu nhúng, liên lạc bí mật có thể thất bại.
  * *Watermarking:* Sự tồn tại của thủy vân có thể được công bố công khai. Mục tiêu tối thượng là **gắn chặt thông điệp vào vật chủ**; thuật toán được thiết kế để gây khó khăn tối đa cho kẻ tấn công khi cố loại bỏ thủy vân mà không làm suy giảm nghiêm trọng giá trị sử dụng của vật chủ trong ngưỡng thiết kế xác định. Tuy nhiên, không có thủy vân nào mặc nhiên bất khả xóa trong mọi điều kiện tấn công tùy ý.

#### B. Thủy vân số (Watermarking) vs Chữ ký số (Digital Signature)
* **Digital Signature:** Bảo vệ văn bản trên biểu diễn số nguyên bản (exact representation). Bất kỳ sự thay đổi byte nào đều khiến chữ ký ban đầu không còn hợp lệ; chữ ký số không tự cung cấp cơ chế so khớp hay phục hồi đối với các bản chuyển đổi analog/lossy (như in-scan, chụp ảnh màn hình).
* **Watermarking:** Tồn tại trên kênh tín hiệu trực quan (Visual representation). Về mặt lý thuyết thiết kế, thủy vân bền vững hướng tới cung cấp cơ chế trích xuất định danh để làm cầu nối đối chiếu ngay cả khi tài liệu đã bị biến đổi qua kênh analog/lossy (cắt xén, in-scan, chụp lại màn hình). Trong thực nghiệm của SplitBind, năng lực này phụ thuộc thế hệ thuật toán. Ở thế hệ **V1**, giải mã bị phá vỡ hoàn toàn trước JPEG-70 và Resize-0.75 (0/12 cả hai) và chỉ khôi phục một phần dưới Crop-0.25. Ở thế hệ nghiên cứu **V3**, đo trên đúng cùng corpus và cùng bộ cổng, giải mã đạt 9/12 với JPEG-70, 9/12 với Crop-0.25 và 8/12 với Resize-0.75; đáng chú ý là JPEG-70 và Crop-0.25 **không gây mất mát nào so với kênh không bị tấn công** (chi tiết phân rã ở Mục 7.2.2). Dù vậy V3 vẫn không đạt cổng phát hành 0.95 và mang phạm vi bằng chứng `research_measurement_only`, nên toàn bộ phân hệ thủy vân bền vững được giữ ở tầng nghiên cứu tham chiếu thay vì đưa lên production. Số liệu đầy đủ và ranh giới ở Mục 7.2.

\newpage

# CHƯƠNG 6. HỆ THỐNG SPLITBIND: KIẾN TRÚC VÀ HIỆN THỰC

### 6.1. Sơ đồ Kiến trúc Hệ thống SplitBind
`[Production]` & `[Implemented]`

Hệ thống được tổ chức thành hai phân hệ độc lập:

```
                            [ CLIENT BROWSER ]
                                    │
                               HTTPS / TLS
                                    ▼
                         [ Caddy Reverse Proxy ]
                                    │
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
        [ React Frontend UI ]               [ Django API Backend ]
         (apps/web - Vite)                   (services/api)
                  │                                   │
                  │                            Database Queries
                  │                                   ▼
                  │                        [ Neon PostgreSQL 18 ]
                  │                         (Metadata & Manifests)
                  │                                   │
                  ▼                                   ▼
          Direct Presigned S3               [ Cloudflare R2 Bucket ]
                  └───────────────────────────────► (PDF Objects)

─────────────────────────────────────────────────────────────────────────────
                TẦNG NGHIÊN CỨU & KIỂM THỬ THUẬT TOÁN (RESEARCH)
  [ Python Reference Codec ] ──► [ Synthetic Corpus ] ──► [ Attack Matrix ]
    - DWT-DCT-QIM Fingerprint                             - 31 Image Attacks
    - Semi-fragile HMAC Tamper                            - 4 Tamper Attacks
```

### 6.2. Hai Quy trình Nghiệp vụ Cốt lõi
`[Production]`

1. **Quy trình Cấp phát Tài liệu (Issuance Workflow):**
   * Quản trị viên tải lên tệp PDF nguồn $\rightarrow$ Hệ thống sinh mã cấp phát ngẫu nhiên `issuance_id` $\rightarrow$ Đóng dấu thông tin cấp phát $\rightarrow$ Tính toán mã băm SHA-256 của tệp nguồn và tệp phát hành $\rightarrow$ Tạo cấu trúc Manifest chuẩn hóa theo RFC 8785 $\rightarrow$ Ký số bằng khóa riêng Ed25519 $\rightarrow$ Lưu trữ hồ sơ cấp phát và cung cấp link tải an toàn.
2. **Quy trình Xác minh Tính toàn vẹn (Verification Workflow):**
   * Người kiểm tra tải lên tệp PDF nghi vấn $\rightarrow$ Hệ thống tính toán mã băm SHA-256 của tệp $\rightarrow$ Tra cứu đối chiếu với cơ sở dữ liệu cấp phát $\rightarrow$ Xác minh chữ ký số Ed25519 của Manifest $\rightarrow$ Trả về kết quả: `VERIFIED_INTACT` (Khớp hoàn toàn) hoặc `Chưa tìm thấy bản cấp phát khớp`.

\newpage

# CHƯƠNG 7. KẾT QUẢ THỰC NGHIỆM

Mọi con số trình bày trên Slide thuyết trình và Báo cáo bắt buộc phải sử dụng chính xác các giá trị sau.

> **Lưu ý phạm vi:** bảng dưới đây là số liệu của **thế hệ thuật toán V1**. Kết quả đo của thế hệ **V3** nằm riêng ở **Mục 7.2** và không thay thế bất kỳ giá trị nào trong bảng này. Khi trích dẫn độ bền thủy vân, luôn nói rõ đang nói về thế hệ nào.

| Số liệu Thực nghiệm | Giá trị Khóa Chính xác | Nguồn Gốc Tệp Artifact (SHA-256) | Đối tượng Đo lường & Pipeline | Ý nghĩa Chứng minh Kỹ thuật |
|---|---|---|---|---|
| **PSNR Trang PDF** | **`41.69 dB`** | `artifacts/task-1-fidelity/fidelity-report.json` | 1 trang tài liệu PDF kết quả thực tế ở độ phân giải 144 DPI. | Thể hiện mức độ suy biến tín hiệu thấp theo chỉ số đo lường khách quan ($\text{PSNR} > 40\text{ dB}$ trên ảnh render), dù không thay thế cho nghiên cứu cảm nhận thị giác chủ quan (MOS / User Study). |
| **SSIM Trang PDF** | **`0.9825`** | `artifacts/task-1-fidelity/fidelity-report.json` | Đo cấu trúc ảnh giữa trang PDF gốc và trang PDF đã xử lý ở 144 DPI. | Thể hiện mức độ tương đồng cấu trúc ký tự rất cao ($\text{SSIM} > 0.98$) theo mô hình đánh giá cấu trúc khách quan. |
| **PSNR Bộ mã hóa Nghiên cứu** | **`65.7 - 70.7 dB`** | `docs/evaluation/fingerprint-profile-v1.md` | Mảng điểm ảnh thử nghiệm trước tấn công của bộ giải mã nghiên cứu. | Chứng minh thuật toán Parity-QIM trên dải trung tần có mức độ nhiễu lượng tử hóa rất thấp ở tầng mảng điểm ảnh. |
| **SSIM Bộ mã hóa Nghiên cứu** | **`0.9998 - 0.9999`** | `docs/evaluation/fingerprint-profile-v1.md` | Mảng điểm ảnh thử nghiệm trước tấn công của bộ giải mã nghiên cứu. | Độ toàn vẹn cấu trúc điểm ảnh ở tầng thuật toán thuần túy. |
| **Quy mô Thực nghiệm V1** | **`32.736 hàng`** | `fingerprint-profile-v1.md` (SHA-256: `e4e9898f...`) | 22 trang $\times$ 48 ứng viên thuật toán $\times$ 31 kịch bản tấn công. | Mô tả quy mô quét tham số của benchmark V1 (22 trang $\times$ 48 ứng viên $\times$ 31 kịch bản tấn công). |
| **Tỷ lệ Gán sai (False Attribution)** | **`0.00%` (0 / 682)** | `fingerprint-profile-v1.md` | 682 hàng kiểm tra trên 48 ứng viên thuật toán. | Trong toàn bộ 682 trường hợp benchmark đã xét, không quan sát thấy bất kỳ ca gán sai định danh nào (hệ thống giải mã đúng hoặc từ chối giải mã do lỗi CRC-32 / Reed-Solomon). |
| **Quy mô Benchmark Can thiệp** | **`48 hàng`** | `docs/evaluation/integrity-profile-v1.md` | 12 trang $\times$ 4 loại tấn công can thiệp (`replace_text`, `cover_region`, `copy_move`, `insert_object`). | Quy mô thực nghiệm đánh giá khả năng định vị sửa đổi của thuật toán Semi-fragile. |
| **IoU Định vị Can thiệp** | **`0.089981` (~0.09)** | `docs/evaluation/integrity-profile-v1.md` | Chỉ số giao trên hợp (IoU) tổng hợp trên toàn bộ 48 hàng thử nghiệm. | Minh bạch giới hạn thuật toán: 38/48 hàng kích hoạt cơ chế fail-safe bảo vệ trước nén mạnh, làm giảm IoU. |
| **Tỷ lệ giải mã JPEG-70 & Resize** | **`0%` (0 / 12)** | `fingerprint-profile-v1.md` | Thực nghiệm dưới nén JPEG Q=70 và co giãn 0.75x. | Minh chứng lý do thuật toán được giữ ở tầng nghiên cứu và chưa đưa lên production. |

---

## 7.2. BỔ SUNG: KẾT QUẢ ĐO THẾ HỆ V3 (KHÔNG THAY THẾ FROZEN METRICS V1)

`[Experimentally observed]` `[Limitation]`

Bảng Frozen Metrics ở trên là số liệu của **thế hệ thuật toán V1**. Dự án đã phát triển tiếp lên V3 và có một lần chạy benchmark hoàn chỉnh chưa được đưa vào bảng khóa. Mục này trình bày kết quả đó dưới nhãn riêng; **mọi con số V1 ở Mục 7.1 giữ nguyên, không sửa đổi**.

Nguồn: `reports/fingerprint-pregate-v3/`, ngày 2026-09-06, `status: complete`, `planned_rows` 352 = `completed_rows` 352, `execution_errors: 0`, `false_attributions: 0`, 4 ứng viên, 12 quan sát chất lượng mỗi ứng viên.

- `plan_sha256`: `efa3b78646f340600fae07eb60fc0c861a2c5b29734173ba0974c37242c696aa`
- `results_csv_sha256`: `e0b1ba7d90b7c5c4ca9a4212a4abe5cbf29232286eda68bdba6a4f5e543bf983`
- `results_sha256`: `69de7db807a69217dade43426d7f9f9e021a9073cfa78fb0d9eb5df489632938`

### 7.2.1. Đối chiếu V1 và V3 trên cùng một corpus

Ứng viên tốt nhất của V3: `da34231d8ae5b50c0271cd5d06a794a780c0a1c051d791d9e1d7d778ce1e9d56`.

| Chỉ số | V1 tốt nhất | V3 tốt nhất | Mẫu số |
|---|---:|---:|---:|
| Giải mã JPEG-70 | 0 / 12 (0.000) | **9 / 12 (0.750)** | 12 |
| Giải mã Resize-0.75 | 0 / 12 (0.000) | **8 / 12 (0.667)** | 12 |
| Giải mã Crop-0.25 | 1 / 3 (0.333) | **9 / 12 (0.750)** | 12 |
| Lỗi thực thi | 31 / 682 | **0 / 352** | — |
| Gán sai định danh | 0 | **0** | — |
| PSNR tối thiểu | 69.31 dB | 42.47 dB | 12 |
| SSIM tối thiểu | 0.99992 | 0.9554 | 12 |

**Phép so sánh này có kiểm soát.** Cả hai thế hệ được đo trên cùng một hợp đồng corpus `e5837cd446ab9c9959ba3fc4b85d205ec9d80e91efc6f801d139810b088a77ef`, cùng định nghĩa cổng (JPEG-70 và resize-0.75 tối thiểu 0.95, crop-0.25 tối thiểu 0.90, quần thể chất lượng đúng 12) và cùng mẫu số 12 cặp ứng viên/trang dương tính. Do đó chênh lệch quy được cho thế hệ thuật toán, không phải do đổi tập dữ liệu hay đổi cách đo.

**Đánh đổi chất lượng.** PSNR tối thiểu giảm từ 69.31 dB xuống 42.47 dB và SSIM tối thiểu từ 0.99992 xuống 0.9554. Cả hai **vẫn vượt ngưỡng cổng chất lượng** (38 dB PSNR, 0.95 SSIM), nên đánh đổi nằm trong ngân sách thiết kế. Cần nói chính xác: phần giảm chất lượng này phát sinh ở bước V1 → V2 (đổi dải nhúng `HL → LL` và nâng bước lượng tử), còn phần tăng độ bền lại đến ở bước V2 → V3 (thêm trải phổ). V2 đã chứng minh rằng chỉ nâng bước lượng tử thì trả giá chất lượng mà **không** thu được độ bền (xem Câu hỏi 9).

### 7.2.2. Phân rã: 0.750 là trần của kênh sạch, không phải thiệt hại do tấn công

Đọc 9/12 thành "V3 sống sót 75% trước JPEG-70" là **sai**. Phân rã 88 hàng của ứng viên tốt nhất theo trang bị trượt:

| Tấn công | Số trang trượt | Trùng đúng các trang mà `identity` trượt? | Trượt thêm so với `identity` |
|---|---:|---|---:|
| `identity` (không tấn công) | 3 | — | — |
| JPEG-70 | 3 | **Có** | **0** |
| Crop-0.25 | 3 | **Có** | **0** |
| Resize-0.75 | 4 | Không | **1** |

Cả 3 trang trượt của `identity` đều thuộc đúng một fixture `pdf-multi-mixed` (trang 0, 1, 2). Mỗi hàng đều có `outcome: partial`, `valid_vote_count: 1`, `confidence: 0.3333` và **`bit_error_rate: 0.0`** — bộ giải mã khôi phục payload **không sai một bit nào** rồi chủ động từ chối kết luận, vì mới có 1 trong 3 lần lặp payload cho phiếu tile hợp lệ trong khi cơ chế fail-safe đòi nhiều hơn.

Phát biểu đúng là: **dưới JPEG-70 và cắt cúp trung tâm 0.25, V3 giải mã đúng bằng mức nó đạt được trên kênh không bị tấn công — không mất thêm hàng nào.** Khoảng trống 3/12 còn lại là giới hạn đặt tile và độ phủ phiếu trên một fixture đa trang, không phải thiệt hại do nén hay cắt cúp. Chỉ Resize-0.75 gây thiệt hại tấn công thật sự, và đúng một hàng: `image-clean-noise` trang 0, `not_detected`, 0 phiếu hợp lệ.

Điều này khớp với bất biến sắp xếp tile chống cắt cúp: tiền tố payload phải giữ được tối thiểu `max(2, ceil(0.60 × payload_repetitions))` tile nguyên vẹn. Với `payload_repetitions = 3`, ngưỡng là 2 phiếu, còn `pdf-multi-mixed` chỉ cho 1. Fixture này phơi bày đúng ràng buộc đặt tile — khuyết tật nằm ở **vị trí đặt**, không phải ở tái dựng hình học và cũng không phải ở độ bền kênh truyền.

### 7.2.3. Hiệu năng và tài nguyên đo được

Đo trên toàn bộ 352 hàng:

| Chỉ số | Phạm vi đo | n | Trung bình | Trung vị | P95 | Lớn nhất |
|---|---|---:|---:|---:|---:|---:|
| Thời gian (ms) | `attack_and_decode` | 352 | 5195.6 | 4427.5 | 12176.1 | 16567.0 |
| Peak RSS (MiB) | `process_lifetime_high_water_observed_after_attack_and_decode` | 352 | 1005.0 | 1014.0 | 1014.0 | 1014.0 |
| Temp disk (MiB) | `attack_and_decode_in_memory_temporary_files_only` | 352 | 0.0 | 0.0 | 0.0 | 0.0 |

Chất lượng trên 192 hàng có PSNR hữu hạn, phạm vi `original_vs_watermarked_before_attack`, thang dữ liệu 255:

| Chỉ số | Nhỏ nhất | Trung bình | Lớn nhất |
|---|---:|---:|---:|
| PSNR (dB) | 42.32 | 43.40 | 44.14 |
| SSIM | 0.9532 | 0.9760 | 0.9932 |

Temp disk bằng 0 ở mọi hàng vì toàn bộ pipeline tấn công và giải mã chạy trong bộ nhớ, không ghi tệp tạm.

### 7.2.4. Ranh giới bắt buộc phải nêu kèm

`[Limitation]`

- `evidence_scope` của lần chạy là `research_measurement_only`. Chính bản tóm tắt tuyên bố V3 pre-gate là **bộ lọc kiểm soát chi phí có tính tất định, không phải bằng chứng phát hành**, và chỉ đo `identity`, JPEG 70, resize 0.75, cắt cúp trung tâm 0.25.
- `profile_promoted: False` và `qualified_candidate_ids: []` vì 0.750 và 0.667 không đạt cổng 0.95. **V3 không đủ điều kiện promote lên production trên bằng chứng này.**
- Không slide hay đoạn báo cáo nào được mô tả V3 như năng lực đã phát hành. Phiên bản đang chạy trên production vẫn là Integrity Release 0.1 dùng V2.
- Ngược lại, cũng không được trình bày con số 0/12 của V1 như "độ bền thủy vân của dự án" mà không nói rõ đó là thế hệ V1. Trên cùng corpus, thế hệ nghiên cứu hiện tại đạt 0.750 ở JPEG-70.

\newpage

# CHƯƠNG 8. ĐỀ XUẤT KIẾN TRÚC V4: CHẨN ĐOÁN NGUYÊN NHÂN GỐC VÀ HƯỚNG SỬA

`[Experimentally observed]` `[Implemented]` `[Limitation]`

Đề bài yêu cầu "tìm hiểu và **đề xuất**" một hệ thống. Phần này là đóng góp đề xuất của nhóm: một chẩn đoán nguyên nhân gốc dựa trên số đo, một phép kiểm chứng đã thực hiện, và kiến trúc V4 rút ra từ đó.

## 8.1. Chẩn đoán: nút thắt nằm ở tập giả thuyết hình học, không ở thủy vân

Đọc `geometry_v3.search_geometry_v3`, bộ giải mã chỉ sinh ứng viên chuẩn tắc từ đúng ba nguồn:

1. `identity` — chỉ khi raster bị tấn công có đúng kích thước chuẩn tắc.
2. `pure_resize` — chỉ khi **hai trục co giãn cùng một tỉ lệ**, sai số `geometry_ratio_tolerance = 0.001`.
3. `center_crop` — chỉ cho các tỉ lệ nằm trong `profile.crop_retained_scales`, vốn bị đóng băng ở **đúng một giá trị** `0.8660254037844386`.

Ngoài ba trường hợp đó, bộ giải mã **không sinh được giả thuyết hình học nào**, nên tầng payload không bao giờ được chạy tới — bất kể sóng mang mạnh đến đâu.

## 8.2. Bằng chứng: tương quan hoàn hảo giữa "có giả thuyết" và "truy vết được"

Đo trên 286 hàng, 0 lỗi thực thi (`run_v5_envelope.py`, 2026-09-11):

| Phép biến đổi | Kích thước ra | Giả thuyết **đúng** có sẵn? | `decode_status` chủ đạo | Truy vết được |
|---|---|---|---|---:|
| crop 0.10 (cạnh 0.9487) | 1457×2914 | **không** (0.9486 ∉ {0.8660}) | `partial` 5, `payload_not_detected` 5 | 2/12 |
| crop 0.25 (cạnh 0.8660) | 1330×2660 | **có** (`center_crop`) | `decoded` 7, `partial` 5, **`payload_not_detected` 0** | **7/12** |
| crop 0.50 (cạnh 0.7071) | 1086×2172 | **không** | `payload_not_detected` 12 | 0/12 |
| JPEG 50 | không đổi | **có** (`identity`) | `payload_not_detected` 12 | 0/12 |
| resize 0.75 / 0.50 / 1.50 | co giãn đều | **có** (`pure_resize`) | phần lớn `decoded` | 10 / 9 / 11 /12 |
| screenshot 1920×1080 | 1080×1920 | **không** (tỉ lệ khung lệch) | `payload_not_detected` 7, `insufficient_sync` 5 | 0/12 |
| screenshot 1366×768 | 768×1366 | **không** | `insufficient_sync_evidence` 12 | 0/12 |

**Mọi phép biến đổi có sẵn giả thuyết đúng đều đạt 7–11/12, trừ JPEG-50. Mọi phép thiếu giả thuyết đúng đều đạt 0–2/12.**

Cần chính xác một điểm: với các phép cắt, **vẫn có** giả thuyết được sinh ra — `pure_resize` kích hoạt vì cắt giữa làm hai trục co cùng tỉ lệ — nhưng nó **căn sai**, kéo vùng đã cắt ra full canvas. Khuyết tật không nằm ở việc *không sinh* giả thuyết mà ở *độ phủ*: ứng viên đúng vắng mặt trong khi một ứng viên sai trông hợp lý chiếm chỗ. Đó là lý do các hàng này báo `payload_not_detected` (đã căn, không thấy tín hiệu) thay vì `insufficient_sync_evidence` (chưa từng căn được).

**Bằng chứng sắc nhất cho luận điểm tối ưu quá mức:** crop 0.25 là phép cắt **duy nhất có 0 hàng `payload_not_detected`**. Mọi trang đều sinh được ít nhất bằng chứng một phần, và chỉ ở đó. Đúng như dự đoán "giả thuyết đúng tồn tại cho tỉ lệ này và không tỉ lệ nào khác", và **không giải thích được bằng cường độ tín hiệu**, vì crop 0.10 bỏ đi ít hơn.

### Ba lớp thất bại khác nhau, không phải một

| Lớp | Dấu hiệu | Ví dụ | Cách sửa |
|---|---|---|---|
| **1. Không tạo được ứng viên** | `insufficient_sync_evidence` | screenshot 1366, phối cảnh | Chuẩn hoá khung ảnh — **đã kiểm chứng**: 0/12 → 9/12 ở 1920×1080 |
| **2. Tạo ứng viên sai** | `payload_not_detected` **kèm đổi kích thước** | crop 0.10, crop 0.50 | Ước lượng tỉ lệ cắt thay vì liệt kê một giá trị cứng |
| **3. Ứng viên đúng, sóng mang chết** | `payload_not_detected` **không đổi kích thước** | JPEG 50; screenshot 1366 sau khi bóc viền | Lớp **duy nhất** mà các lever tham số từng là câu chuyện đúng — và cả ba lever đó đã bị bác bỏ bằng đo đạc |

Phải phân loại thất bại theo `decode_status` cộng với việc raster có đổi kích thước hay không, **trước khi** đề xuất bất kỳ biện pháp nào.

Hai hệ quả phải nói thẳng:

- **Kết quả crop 0.25 bị tối ưu quá mức cho chính benchmark.** `crop_retained_scales = [sqrt(0.75)]` chính xác là tỉ lệ cạnh mà `crop_fraction = 0.25` tạo ra — đúng phép cắt duy nhất mà pre-gate đo. Bộ giải mã được cứng hoá để hoàn tác đúng phép tấn công mà nó bị chấm điểm. Đó là lý do một phép cắt **nhẹ hơn** (10%) lại tệ hơn một phép cắt nặng hơn (25%): vô lý nếu giải thích bằng cường độ tín hiệu, hoàn toàn hợp lý nếu giải thích bằng độ phủ giả thuyết.
- **Screenshot hỏng vì một lý do cơ bản hơn và không liên quan.** Đặt trang 1536×3072 vào màn hình 1920×1080 kèm viền letterbox cho hai tỉ lệ 0.703 và 0.625 — không khớp, nên cả `pure_resize` lẫn `center_crop` đều không kích hoạt. Bộ giải mã báo `insufficient_sync_evidence` vì nó **chưa từng tạo ra ứng viên nào**.

## 8.3. Kiểm chứng: bóc viền letterbox khôi phục truy vết screenshot

Chẩn đoán trên sinh ra một dự đoán kiểm chứng được: nếu bỏ viền đồng màu của màn hình, hai tỉ lệ sẽ khớp lại và giả thuyết `pure_resize` sẵn có sẽ kích hoạt. Kết quả đo trên 12 trang dương tính:

| Màn hình | Ảnh thô | Sau khi bóc viền |
|---|---:|---:|
| **1920×1080** | **0/12** | **9/12** |
| 1366×768 | 0/12 | 0/12 |

**9/12 đúng bằng tỉ lệ của resize-0.50** — chính là điều dự đoán đòi hỏi: bỏ viền đi thì screenshot *chính là* một phép co giãn đều, mà bộ giải mã vốn đã xử lý được. Thủy vân, ECC, tham số trải phổ và vị trí tile **giữ nguyên không đổi**; phần sửa chỉ khoảng hai mươi dòng tiền xử lý tất định: tìm màu viền theo trung vị bốn cạnh rồi cắt các hàng/cột nằm trong dung sai của màu đó.

Hai kích thước màn hình hỏng vì hai lý do khác nhau, và phép bóc viền tách bạch được chúng:

- Ở 1920×1080, sau khi bóc, trang nằm ở tỉ lệ 0.625. Hai tỉ lệ khớp, `pure_resize` kích hoạt, truy vết phục hồi. **Đây chưa bao giờ là vấn đề của thủy vân.**
- Ở 1366×768, trang nằm ở 683×1366, tỉ lệ 0.4447. Trạng thái chuyển từ `insufficient_sync_evidence` sang `payload_not_detected` — hình học giờ thành công và chính **payload** mới là thứ chết. 0.4447 thấp hơn mốc resize-0.50 vốn đạt 9/12, nên đây là **giới hạn phân giải thật** của sóng mang.

Chuyển dịch mã trạng thái đó là công cụ chẩn đoán đáng dùng: `insufficient_sync_evidence` nghĩa là chưa tạo được ứng viên, hỏng ở **hình học**; `payload_not_detected` nghĩa là đã căn được trang và **tín hiệu** đã mất.

## 8.4. Kiến trúc V4 đề xuất

Xếp theo tỉ lệ lợi ích trên chi phí đo được:

**Tầng 1 — Chuẩn hoá khung ảnh trước khi giải mã (đã kiểm chứng).**
Bóc viền đồng màu; mở rộng sang phát hiện biên trang và khử nghiêng. Bộ giải mã V3 ngầm giả định đầu vào đã được đóng khung giống hệt bản phát hành, trong khi **kênh rò rỉ thật không bao giờ như vậy**. Đây là tầng cho nhiều độ bền nhất trên mỗi dòng mã.

**Tầng 2 — Ước lượng tỉ lệ cắt thay vì liệt kê.**
Thay `crop_retained_scales` cố định bằng tìm kiếm tỉ lệ, hoặc ước lượng tỉ lệ từ tương quan log-polar của pilot (hạ tầng này **đã có sẵn** trong `synchronization_v2.py`). Xoá điểm tối ưu quá mức tại 0.25 và làm crop 0.10 / 0.50 trở nên xử lý được.

**Tầng 3 — Cho phép hai trục co giãn độc lập.**
Ràng buộc `ratios_agree` loại bỏ mọi phép biến đổi đổi tỉ lệ khung. Nới nó ra cho phép xử lý ảnh bị kéo méo và bù phối cảnh.

**Tầng 4 — Chọn sóng mang theo nội dung (chưa kiểm chứng).**
Chấm điểm tile ứng viên theo kết cấu trước khi chọn, vẫn tất định từ khoá. Giải quyết việc *trang nào* hỏng **bên trong** một phép biến đổi mà bộ giải mã đã hoàn tác được — hiệu ứng thứ cấp thật, nhưng không phải nguyên nhân của các thất bại diện rộng.

## 8.5. Cái gì kiến trúc này không sửa được

`[Limitation]`

- **Giới hạn phân giải là thật.** Dưới tỉ lệ khoảng 0.45, payload chết kể cả khi hình học hoàn hảo. Không tầng nào ở trên chạm tới điều đó; muốn sửa phải tăng dung lượng hoặc giảm payload, và nhóm đã đo được rằng nâng `qim_delta` **không** phải lối ra (V2 quét 24→64, trần vẫn 3/12).
- **JPEG-50 là thất bại sóng mang thật** (lớp 3): hình học đúng vì ảnh không đổi kích thước, nhưng nén phá huỷ tín hiệu. Đây là giới hạn mà không tầng kiến trúc nào ở trên chạm tới được, và ba lever tham số đã bị bác bỏ bằng đo đạc, nên hướng duy nhất còn lại là tăng dung lượng kênh hoặc giảm payload.
- **Toàn bộ số trong phần này đến từ harness nghiên cứu, không phải pre-gate**, và khác pre-gate ở cách dẫn xuất RNG tấn công cùng việc cấp mẫu đồng bộ ORB cho bộ giải mã. Không được trộn với Mục 7.2, và không được trình bày như năng lực đã phát hành. Production vẫn chạy V2 với xác thực toàn vẹn tệp chính xác.

## 8.6. Vì sao chẩn đoán này có được

Đáng ghi nhận về mặt phương pháp: chẩn đoán trên chỉ tìm ra được **vì dự án đã ghi lại bằng chứng đúng cách**. Mã trạng thái phân biệt `insufficient_sync_evidence` với `payload_not_detected` là thứ tách được hai nguyên nhân; hợp đồng tấn công có sẵn họ `screenshot` để đo; corpus khoá theo hash làm phép so sánh có kiểm soát. Một dự án ghi chép cẩu thả sẽ không để lại gì để kiểm toán.

\newpage

# CHƯƠNG 9. KẾT LUẬN

## 9.1. Kết quả đạt được

Báo cáo đã hoàn thành bốn nội dung được giao. Về lý thuyết, nhóm trình bày cơ sở kỹ thuật Digital Watermarking, phân loại theo miền nhúng và theo mục tiêu an ninh, cùng bài toán đánh đổi giữa độ bền, tính vô hình và dung lượng tải trọng (Chương 2). Về ứng dụng, nhóm phân tích vai trò của thủy vân bền vững trong truy vết nguồn phát hành và của thủy vân bán mỏng manh trong định vị can thiệp (Chương 3), vai trò của chữ ký số Ed25519 trên manifest chuẩn tắc RFC 8785 trong bảo vệ thông tin truy vết (Chương 4), và đặt sáu kỹ thuật toàn vẹn cạnh nhau trên bảy tiêu chí an ninh (Chương 5).

Điểm khác biệt của báo cáo nằm ở chỗ toàn bộ phần lý thuyết đều được kiểm chứng bằng một hệ thống hiện thực đầy đủ. SplitBind không dừng ở mô hình: hệ thống đã được triển khai và vận hành thực tế, cấp phát PDF có chữ ký số, xác minh toàn vẹn tệp chính xác, và ghi nhận toàn bộ quá trình vào audit log (Chương 6). Phần thủy vân bền vững được phát triển qua ba thế hệ thuật toán và đo đạc trên corpus khoá theo mã băm, với kết quả được trình bày trung thực kể cả khi bất lợi (Chương 7).

## 9.2. Đóng góp chính

Đóng góp có giá trị nhất của nhóm không phải một con số độ bền, mà là một **chẩn đoán nguyên nhân gốc** (Chương 8).

Qua ba thế hệ, nhóm đã lần lượt kiểm chứng và **bác bỏ** cả ba hướng tinh chỉnh tham số của thiết kế: bước lượng tử hóa, số tile trên trang, và các tham số trải phổ. Mỗi lần bác bỏ dựa trên một loại bằng chứng khác nhau: một sweep 1408 hàng, một lần đọc mã nguồn, và một thí nghiệm 192 hàng. Kết quả âm tính đó dẫn tới câu hỏi đúng, và câu trả lời là: **độ bền của hệ thống không bị giới hạn bởi thủy vân, mà bởi tập giả thuyết hình học của bộ giải mã.**

Bằng chứng cho kết luận này là một tương quan không có ngoại lệ trên 286 hàng đo: mọi phép biến đổi mà bộ giải mã có sẵn giả thuyết đúng đều đạt 7–11 trên 12, mọi phép thiếu giả thuyết đúng đều đạt 0–2 trên 12. Chẩn đoán sau đó được xác nhận bằng một phép thử có tính tiên đoán: bóc viền letterbox của ảnh chụp màn hình đưa tỉ lệ truy vết từ **0/12 lên 9/12** ở độ phân giải 1920×1080, mà **không thay đổi bất kỳ tham số nào của thủy vân**.

Từ đó, nhóm phân tách được ba lớp thất bại vốn bị gộp chung dưới nhãn "thủy vân không đủ bền": không tạo được ứng viên hình học, tạo ứng viên sai, và ứng viên đúng nhưng sóng mang đã chết. Chỉ lớp thứ ba mới thực sự là vấn đề của thủy vân.

## 9.3. Giới hạn

`[Limitation]`

Nhóm nêu rõ các giới hạn sau, và không trình bày chúng như đã giải quyết:

- Phân hệ thủy vân bền vững **chưa đạt cổng phát hành** và được giữ ở tầng nghiên cứu. Phiên bản vận hành chỉ kích hoạt xác thực toàn vẹn tệp chính xác bằng SHA-256 và chữ ký Ed25519.
- Dưới tỉ lệ co giãn khoảng 0,45, payload không còn khôi phục được kể cả khi hình học chính xác. Đây là giới hạn phân giải thật của sóng mang.
- Định vị can thiệp đạt IoU tổng hợp khoảng 0,09 do cơ chế fail-safe kích hoạt trên phần lớn kịch bản có diện tích can thiệp lớn.
- Kết quả thủy vân bền vững mang phạm vi bằng chứng nghiên cứu, chưa phải bằng chứng phát hành.
- **Không kết quả nào trong báo cáo chứng minh danh tính người làm rò rỉ, chỉnh sửa hay phát tán tài liệu.** Thủy vân và chữ ký số cung cấp tín hiệu kỹ thuật phục vụ điều tra, không phải kết luận pháp lý về hành vi của một cá nhân.

## 9.4. Hướng phát triển

Thứ tự ưu tiên rút ra trực tiếp từ chẩn đoán ở Chương 8: chuẩn hoá khung ảnh trước khi giải mã (đã kiểm chứng hiệu quả); ước lượng tỉ lệ cắt thay vì liệt kê một giá trị cứng; cho phép hai trục co giãn độc lập để xử lý biến dạng phối cảnh; và cuối cùng mới là chọn sóng mang theo nội dung. Xa hơn, hướng bước lượng tử thích nghi theo mô hình thị giác người và các kiến trúc học sâu như HiDDeN hoặc StegaStamp là lối đi cho lớp thất bại thứ ba, lớp duy nhất mà cường độ sóng mang thực sự là nút thắt.

\newpage


# TÀI LIỆU THAM KHẢO

Tất cả các trích dẫn trong bài thuyết trình và báo cáo thuyết minh được định dạng theo chuẩn IEEE:

* **Sách Chuyên khảo Quốc tế:**
  1. [1] W. Stallings, *Cryptography and Network Security: Principles and Practice*, 7th ed. Boston, MA, USA: Pearson, 2017, ch. 11-14.
  2. [2] I. J. Cox, M. L. Miller, J. A. Bloom, J. Fridrich, and T. Kalker, *Digital Watermarking and Steganography*, 2nd ed. Burlington, MA, USA: Morgan Kaufmann, 2007.

* **Giáo trình Đại học trong Nước:**
  3. [3] Hoàng Xuân Dậu, *Giáo trình Cơ sở An toàn Thông tin*, Hà Nội: Học viện Công nghệ Bưu chính Viễn thông, 2020.
  4. [4] T. T. Tùng, *Giáo trình Mật mã học & Hệ thống Thông tin An toàn*. Hà Nội: Nhà xuất bản Thông tin và Truyền thông, 2011.

* **Bài báo Khoa học Tiêu biểu:**
  5. [5] B. Chen and G. W. Wornell, "Quantization index modulation: a class of provably good methods for digital watermarking and information embedding," *IEEE Transactions on Information Theory*, vol. 47, no. 4, pp. 1423-1443, May 2001, doi: 10.1109/18.923725.
  6. [6] J. Zhu, R. Kaplan, A. Johnson, and L. Fei-Fei, "HiDDeN: Hiding Data with Deep Networks," in *Proc. European Conference on Computer Vision (ECCV)*, Munich, Germany, 2018, pp. 657-672, doi: 10.1007/978-3-030-01267-0_40.
  7. [7] M. Tancik, B. Mildenhall, and R. Ng, "StegaStamp: Invisible Hyperlinks in Physical Photographs," in *Proc. IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)*, Seattle, WA, USA, 2020, pp. 2117-2126.

* **Tiêu chuẩn Kỹ thuật và Giao thức Quốc tế:**
  8. [8] A. Rundgren, B. Jordan, and S. Erdtman, "JSON Canonicalization Scheme (JCS)," Internet Engineering Task Force (IETF), RFC 8785, June 2020. [Online]. Available: https://www.rfc-editor.org/rfc/rfc8785
  9. [9] S. Josefsson and I. Liusvaara, "Edwards-Curve Digital Signature Algorithm (EdDSA)," Internet Engineering Task Force (IETF), RFC 8032, January 2017. [Online]. Available: https://www.rfc-editor.org/rfc/rfc8032
  10. [10] National Institute of Standards and Technology (NIST), "Secure Hash Standard (SHS)," Federal Information Processing Standards Publication (FIPS PUB) 180-4, August 2015.
  11. [11] National Institute of Standards and Technology (NIST), "The Keyed-Hash Message Authentication Code (HMAC)," Federal Information Processing Standards Publication (FIPS PUB) 198-1, July 2008.
  12. [12] H. Krawczyk, M. Bellare, and R. Canetti, "HMAC: Keyed-Hashing for Message Authentication," Internet Engineering Task Force (IETF), RFC 2104, February 1997. [Online]. Available: https://www.rfc-editor.org/rfc/rfc2104
  13. [13] National Institute of Standards and Technology (NIST), "Implementation Guidance for FIPS 140-3 and the Cryptographic Module Verification Program," NIST CSRC, April 2026. [Online]. Available: https://csrc.nist.gov/projects/cryptographic-module-validation-program/fips-140-3-ig-announcements

\newpage

# PHỤ LỤC A. MA TRẬN TRUY VẾT KHẲNG ĐỊNH VÀ BẰNG CHỨNG

Bảng đối chiếu toàn diện giữa các tuyên bố kỹ thuật trong tài liệu với bằng chứng thực tế trong kho lưu trữ:

| Khẳng định Kỹ thuật / Số liệu | Phân loại Nhãn | Bằng chứng Thực tế / Đường dẫn Mã nguồn | Trạng thái Kiểm chứng |
|---|---|---|---|
| Cấu trúc Payload nhúng đúng 23 byte (`magic`, `version`, `UUID`, `CRC32`) | `[Implemented]` | `contracts/algorithm/payload-profile.v1.json: L3-L10`, `research/python/src/splitbind_ref/payload.py: L18-L33` | Đã kiểm chứng: 9/9 tests pass trong `test_payload.py`. |
| Mã sửa lỗi Reed-Solomon 39 byte từ 23 byte payload | `[Implemented]` | `contracts/algorithm/payload-profile.v1.json: L20-L27`, `research/python/src/splitbind_ref/payload.py` | Đã kiểm chứng qua hợp đồng thuật toán cố định. |
| Thuật toán thủy vân DWT-DCT-QIM với ORB-RANSAC | `[Implemented]` | `research/python/src/splitbind_ref/dwt_dct_qim.py` | Đã kiểm chứng qua pipeline mã hóa/giải mã tham chiếu. |
| Số liệu PSNR 41.69 dB và SSIM 0.9825 trên trang PDF | `[Experimentally observed]` | `artifacts/task-1-fidelity/fidelity-report.json` | Đã kiểm chứng: Đo lường khách quan trên trang PDF render 144 DPI. |
| Quy mô Benchmark V1: 32.736 hàng thực nghiệm | `[Experimentally observed]` | `docs/evaluation/fingerprint-profile-v1.md` (Mã băm SHA-256: `e4e9898f...`) | Đã kiểm chứng: 22 trang $\times$ 48 ứng viên $\times$ 31 kịch bản tấn công. |
| Tỷ lệ gán sai 0.00% (0 / 682 hàng) | `[Experimentally observed]` | `docs/evaluation/fingerprint-profile-v1.md: Table 4` | Đã kiểm chứng trên tập mẫu benchmark V1 đã xét. |
| Ranh giới thất bại trước JPEG-70 và Resize-0.75 | `[Limitation]` | `docs/evaluation/fingerprint-profile-v1.md: Section 5` | Đã kiểm chứng: 0/12 ca giải mã thành công trong benchmark. |
| Thuật toán Semi-fragile Tamper Localization khối $128 \times 128$ | `[Implemented]` | `research/python/src/splitbind_ref/integrity.py` | Đã kiểm chứng mã nguồn cài đặt DCT + HMAC-SHA256 + Partner Ring. |
| Quy mô Benchmark Can thiệp 48 hàng, Aggregate IoU = 0.089981 | `[Experimentally observed]` | `docs/evaluation/integrity-profile-v1.md: Table 2` | Đã kiểm chứng: 12 trang $\times$ 4 loại tấn công; 38/48 hàng kích hoạt fail-safe. |
| Chuẩn hóa RFC 8785 JCS và ký số Ed25519 trên Manifest | `[Implemented]` & `[Production]` | `services/api/splitbind/release/manifest.py: L58-L120` | Đã kiểm chứng qua hàm `build_signed_issuance_manifest` và `_sign` với Ed25519 trên Azure. |
| Trạng thái UI minh bạch "Chưa tìm thấy bản cấp phát khớp" | `[Production]` & `[Limitation]` | `apps/web/src/features/evidence/copy.ts: L46-L81`, `apps/web/src/pages/VerifyDocumentPage.tsx` | Đã kiểm chứng logic hiển thị trạng thái và thông báo phạm vi trên giao diện web production. |
| Phân định rạch ròi ba cấp độ A (Payload), B (Kiến trúc), C (Production) | `[Implemented]` & `[Production]` (Thiết kế Kiến trúc Dự án) | `docs/superpowers/specs/2026-08-13-splitbind-production-design.md: Section 1-3`, `docs/decisions/001-azure-production-architecture.md` | Đã kiểm chứng thống nhất trong hồ sơ đặc tả thiết kế kiến trúc SplitBind. |

---

> **HẾT TÀI LIỆU CƠ SỞ TRI THỨC**  
> *Đã hoàn tất đóng băng kỹ thuật và biên tập chuẩn hóa học thuật ngày 10/09/2026.*  
> *Chính thức phê duyệt bàn giao cho thành viên thực hiện Slide Thuyết trình (PPTX) và Báo cáo Thuyết minh.*
