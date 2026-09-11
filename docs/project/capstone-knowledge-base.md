# TÀI LIỆU CƠ SỞ TRI THỨC BÁO CÁO BÀI TẬP LỚN AN TOÀN THÔNG TIN
## ĐỀ TÀI: TÌM HIỂU VÀ ĐỀ XUẤT HỆ THỐNG TRUY VẾT TOÀN VẸN VĂN BẢN (SPLITBIND)
### Nhóm 9 - Lớp học phần: 012012303303 - Giảng viên hướng dẫn: TS. Hồ Đăng Thế

---

> **MỤC ĐÍCH TÀI LIỆU:**
> Tài liệu này là **Nguồn Chân lý Duy nhất (Single Source of Truth - SSOT)** đúc kết toàn bộ cơ sở lý thuyết, kết quả thực nghiệm, thiết kế kiến trúc và số liệu đo lường đã được đóng băng kỹ thuật (Technical Content Freeze). Thành viên phụ trách làm Slide Thuyết trình (PPTX) và Báo cáo Thuyết minh (DOCX/PDF) bắt buộc phải bám sát cấu trúc, thuật ngữ, số liệu và các nhãn phân định cấp độ tri thức trong tài liệu này; tuyệt đối không tự ý suy diễn hoặc phóng đại tính năng hệ thống.

---

## HỆ THỐNG NHÃN PHÂN ĐỊNH CẤP ĐỘ TRI THỨC (EPISTEMIC LABELS)

Mọi nội dung, khẳng định kỹ thuật và số liệu trong tài liệu này đều được gắn một trong 5 nhãn định chuẩn nhận thức sau:

1. `[Established theory]`: Tri thức khoa học kinh điển trích xuất từ giáo trình an toàn thông tin, sách chuyên khảo, bài báo khoa học hoặc tiêu chuẩn quốc tế (RFC, ISO, FIPS).
2. `[Implemented]`: Tính năng, mô hình hoặc thuật toán đã được cài đặt thành mã nguồn cụ thể trong kho lưu trữ của dự án.
3. `[Experimentally observed]`: Kết quả đo lường, metric kiểm thử được sinh ra từ các kịch bản thực nghiệm benchmark có artifact lưu vết và mã băm SHA-256 xác thực trên đĩa.
4. `[Production]`: Tính năng đang hoạt động thực tế trên môi trường máy chủ đám mây Azure (`https://splitbind.qivarn.id.vn`) trong phiên bản phát hành hiện hành (Integrity Release 0.1).
5. `[Limitation]`: Giới hạn kỹ thuật đã được nhận diện, các ranh giới thất bại của thuật toán, hoặc tính năng được chủ động khóa lại / chưa đưa lên môi trường production.

---

# PHẦN 1: ĐỀ TÀI VÀ QUY ƯỚC NGỮ NGHĨA TOÀN BỘ BÀI BÁO CÁO

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

---

# PHẦN 2: CƠ SỞ LÝ THUYẾT DIGITAL WATERMARKING (PHỤC VỤ YÊU CẦU 1)

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

---

# PHẦN 3: ỨNG DỤNG THỦY VÂN TRONG TRUY VẾT & TOÀN VẸN HÌNH ẢNH (PHỤC VỤ YÊU CẦU 2)

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

---

# PHẦN 4: ỨNG DỤNG KÝ SỐ TRONG BẢO VỆ THÔNG TIN TRUY VẾT (PHỤC VỤ YÊU CẦU 3)

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

---

# PHẦN 5: MA TRẬN SO SÁNH CÁC KỸ THUẬT TOÀN VẸN (PHỤC VỤ YÊU CẦU 4)

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

---

# PHẦN 6: CASE STUDY HỆ THỐNG SPLITBIND VÀ KIẾN TRÚC THỰC THI

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

---

# PHẦN 7: BẢNG TỔNG HỢP SỐ LIỆU THỰC NGHIỆM ĐÃ KHÓA (FROZEN METRICS)

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

---

# PHẦN 8: SỔ TAY HƯỚNG DẪN TRẢ LỜI PHẢN BIỆN (DEFENSE Q&A CHEATSHEET)

Dành cho các thành viên tham gia buổi bảo vệ trước Hội đồng và Giảng viên:

### Câu hỏi 1: Tại sao lại kết hợp Thủy vân số và Chữ ký số? Hai cơ chế này có mâu thuẫn không khi thủy vân làm đổi bit còn chữ ký số yêu cầu toàn vẹn bit?
* **Trả lời trọng tâm:**
  1. *Về mặt kỹ thuật:* Không hề có mâu thuẫn về thứ tự thực thi. Kiến trúc tích hợp đề xuất áp dụng nguyên tắc "Nhúng trước, Ký sau": Thuật toán nhúng thông tin thủy vân vào tài liệu trước, sau đó mới tính toán mã băm SHA-256 trên tệp đã nhúng hoàn chỉnh để đóng gói vào hồ sơ Manifest chuẩn tắc RFC 8785 và ký số Ed25519:
     $$h_{\text{output}} = \text{SHA-256}(W(D))$$
     $$M = \text{JCS}(\{\text{"schema\_version"}: 1, \text{"issuance\_id"}: \text{id}, \dots, \text{"output\_sha256"}: h_{\text{output}}, \dots\})$$
     $$S = \text{Ed25519.Sign}(sk, M)$$
     Chữ ký số Ed25519 ký trên hồ sơ Manifest chuẩn hóa độc lập với thư viện tuần tự hóa, bảo vệ tính toàn vẹn và chống giả mạo của mã băm văn bản đã mang thủy vân dưới các giả định an toàn mật mã.
  2. *Về mặt kiến trúc:* Hai cơ chế giải quyết hai mô hình đe dọa (threat models) khác nhau:
     * Chữ ký số trên Manifest bảo vệ tính toàn vẹn bit và chống chối bỏ trên kênh truyền số nguyên bản (Exact-bit digital channel). Nếu tệp bị sửa đổi hoặc nén lại, chữ ký trên Manifest gốc vẫn hoàn toàn hợp lệ (chứng minh Manifest không bị giả mạo), nhưng mã băm của tệp nghi vấn không còn khớp với `output_sha256` ghi trong Manifest.
     * Về mặt lý thuyết thiết kế, thủy vân số bền vững đóng vai trò là cơ chế chủ động (proactive) hướng tới khả năng sống sót qua các kênh rò rỉ biến đổi tín hiệu (Analog/lossy leak channels như in ra giấy, quét lại, chụp màn hình điện thoại) làm mất tính toàn vẹn bit thô, cho phép giải mã lấy lại `issuance_id` để làm cầu nối tra cứu hồ sơ Manifest gốc đã ký trong hệ thống. Cần lưu ý rằng khả năng này phụ thuộc thế hệ thuật toán: thế hệ V1 không vượt qua JPEG-70 và Resize-0.75 (0/12 cả hai), còn thế hệ nghiên cứu V3 đo trên cùng corpus đạt 9/12 với JPEG-70, 9/12 với Crop-0.25 và 8/12 với Resize-0.75. Dù vậy V3 vẫn dưới cổng phát hành 0.95 nên toàn bộ phân hệ được giữ ở tầng nghiên cứu (xem Mục 7.2 và Câu hỏi 3b).
  * *Kết luận:* Hai cơ chế tạo thành chiến lược phòng thủ theo chiều sâu (Defense-in-Depth).

### Câu hỏi 2: Tại sao kết quả định vị can thiệp (IoU) trong báo cáo chỉ đạt xấp xỉ 0.09? Thuật toán có sử dụng được trong thực tế không?
* **Trả lời trọng tâm:**
  * Chỉ số IoU tổng hợp ~ 0.09 là kết quả thực nghiệm trung thực từ 48 kịch bản tấn công trên 12 trang tài liệu benchmark.
  * Nguyên nhân kỹ thuật cốt lõi: Thuật toán cài đặt cơ chế an toàn chủ động (Fail-safe): Khi tỷ lệ khối không khớp trên trang vượt quá 10% (`mismatch_ratio >= 0.10`), hệ thống nhận diện đây là biến đổi toàn cục (nén JPEG mạnh hoặc lỗi hình học) chứ không phải can thiệp cục bộ, và chủ động xóa danh sách vùng nghi vấn (`suspicious = ()`) để tránh cảnh báo sai cho người dùng.
  * Trong thực nghiệm, do các kịch bản can thiệp có diện tích tương đối lớn so với kích thước khối $128 \times 128$, có tới **38 / 48 hàng thử nghiệm** đã kích hoạt cơ chế fail-safe này, dẫn đến giá trị IoU tính trên toàn bộ tập mẫu bị kéo giảm.
  * *Bài học học thuật:* Kết quả phản ánh rõ ranh giới kỹ thuật của phương pháp Semi-fragile dựa trên khối DCT truyền thống: thuật toán nhạy cảm với diện tích can thiệp lớn và dễ nhầm lẫn giữa can thiệp diện rộng với nén ảnh toàn cục. Đây là căn cứ khoa học cho thấy cần phát triển tiếp lên các mô hình trích xuất đặc trưng đa tỉ lệ hoặc mạng nơ-ron học sâu.

### Câu hỏi 3: Trên hệ thống chạy thực tế (Production), tính năng Thủy vân số đã hoạt động như thế nào?
* **Trả lời trọng tâm:**
  * Nhóm áp dụng quy trình kiểm soát chất lượng phần mềm nghiêm ngặt (Release Gate): Chỉ những thuật toán đạt độ bền vững $\ge 95\%$ trước các kênh biến đổi thực tế mới được phép đưa vào quy trình tự động trên môi trường vận hành máy chủ.
  * Ứng viên tốt nhất hiện nay thuộc thế hệ V3, đạt 9/12 (0.750) với JPEG-70, 9/12 với Crop-0.25 và 8/12 (0.667) với Resize-0.75. Các con số này vượt xa thế hệ V1 nhưng **vẫn dưới cổng phát hành $\ge 95\%$**, nên phiên bản Production Release 0.1 hiện chỉ kích hoạt cơ chế xác thực toàn vẹn tệp chính xác bằng Chữ ký số Ed25519 và mã băm SHA-256 trên đám mây Azure (`https://splitbind.qivarn.id.vn`). Đây là quyết định kỷ luật kỹ thuật: cổng chất lượng không được hạ xuống cho vừa kết quả.
  * Phân hệ thủy vân DWT-DCT-QIM và định vị can thiệp Semi-fragile được tổ chức và kiểm định hoàn chỉnh trong Tầng nghiên cứu (Research Benchmark Suite).
  * Trên giao diện người dùng web (`apps/web`), hệ thống hiển thị minh bạch nhãn *"Chưa tìm thấy bản cấp phát khớp"* chứ không tuyên bố sai lệch rằng đã thực hiện quét thủy vân tự động.

### Câu hỏi 3b: Báo cáo ghi tỷ lệ giải mã 0% trước JPEG-70. Vậy thủy vân của nhóm có hoạt động không?

* **Trả lời trọng tâm:**
  * Con số 0/12 là của **thế hệ V1**, không phải kết quả cuối cùng của nhóm. Nhóm đã lặp qua ba thế hệ thuật toán, và thế hệ **V3** đo trên **đúng cùng một corpus** (`e5837cd4…88a77ef`), **cùng bộ cổng** và **cùng mẫu số 12** cho kết quả khác hẳn:

    | Chỉ số | V1 | V3 |
    |---|---:|---:|
    | JPEG-70 | 0/12 | **9/12** |
    | Resize-0.75 | 0/12 | **8/12** |
    | Crop-0.25 | 1/3 | **9/12** |
    | Lỗi thực thi | 31/682 | **0/352** |

  * **Điểm mạnh nhất nằm ở phân rã, không ở con số 0.750.** Khi tách 88 hàng của ứng viên tốt nhất theo trang bị trượt, JPEG-70 và Crop-0.25 trượt **đúng ba trang mà phép đo không tấn công (`identity`) cũng trượt — không thêm hàng nào**. Nghĩa là dưới nén JPEG chất lượng 70 và cắt cúp trung tâm 25%, thuật toán giải mã **đúng bằng mức nó đạt trên kênh sạch**. Chỉ Resize-0.75 gây thiệt hại thật, và đúng một hàng.
  * Ba trang trượt đó thuộc cùng một fixture `pdf-multi-mixed`, đều có `outcome: partial`, `valid_vote_count: 1` và **`bit_error_rate: 0.0`** — bộ giải mã khôi phục payload **không sai một bit nào** rồi chủ động từ chối kết luận vì mới có 1 trong 3 lần lặp payload cho phiếu hợp lệ. Đây là **fail-safe đúng thiết kế**, không phải giải mã sai. Nguyên nhân là ràng buộc đặt tile: tiền tố payload cần tối thiểu `max(2, ceil(0.60 × 3)) = 2` tile nguyên vẹn, fixture này chỉ cho 1.
  * **Giá phải trả:** V3 hạ PSNR tối thiểu từ 69.31 dB xuống 42.47 dB và SSIM từ 0.99992 xuống 0.9554 để đổi lấy độ bền. Cả hai vẫn trên ngưỡng cổng (38 dB, 0.95). Đây chính là bài toán đánh đổi dung lượng–độ bền–tính vô hình được thể hiện bằng số đo thật.
  * **Ranh giới phải nêu:** phạm vi bằng chứng là `research_measurement_only`, `profile_promoted: False`, `qualified_candidate_ids: []`. V3 **chưa đủ điều kiện promote**, và production vẫn chạy V2. Nhóm không hạ cổng 0.95 để tuyên bố thành công.
  * **Không gán sai một lần nào** trong toàn bộ 352 hàng V3 và 682 hàng V1. Thuộc tính này quan trọng hơn tỷ lệ giải mã đối với bài toán truy vết: hệ thống thà từ chối kết luận còn hơn chỉ sai người.

### Câu hỏi 4: Sự khác nhau căn bản giữa Thủy vân số (Watermarking) và Giấu tin bí mật (Steganography) là gì?
* **Trả lời trọng tâm:**
  * Sự khác biệt cốt lõi nằm ở **Mục tiêu an ninh** và **Độ bền vững trước tấn công**:
    * *Steganography:* Mục tiêu tối thượng là giấu giếm **sự tồn tại của hành vi truyền tin** (kẻ nghe lén không được biết có thông điệp ẩn). Thiết kế tập trung vào việc giảm thiểu khả năng bị phát hiện bởi các thuật toán phân tích ẩn mật (steganalysis resistance); các yếu tố dung lượng tải trọng và độ bền vững là những bài toán đánh đổi phụ thuộc vào mục tiêu cụ thể của từng lược đồ giấu tin.
    * *Watermarking:* Sự tồn tại của dấu vết có thể được công bố công khai. Mục tiêu tối thượng là **gắn chặt thông điệp vào vật chủ**; về mặt lý thuyết thiết kế, thủy vân bền vững (Robust Watermark) hướng tới việc **khó bị gỡ bỏ trong phạm vi mô hình đe dọa và các ngưỡng biến đổi xác định** (nếu cố tình làm suy biến tín hiệu vượt ngưỡng để hủy thủy vân thì thường làm suy giảm nghiêm trọng chất lượng thị giác của vật chủ), tuy nhiên không bảo đảm bất khả xóa trong mọi điều kiện tấn công tùy ý. (Trên prototype nghiên cứu của SplitBind, độ bền vững hiện mới được kiểm chứng thành công một phần trước phép cắt cúp 25% và thất bại trước JPEG-70 cũng như Resize-0.75). Ưu tiên độ bền vững trước các phép xử lý tín hiệu.

### Câu hỏi 5: Phân biệt Kỹ thuật Thủy vân số (Watermarking) nói chung và Kỹ thuật Đánh dấu định danh (Fingerprinting / Traitor Tracing)?
* **Trả lời trọng tâm:**
  * *Thủy vân số truyền thống (Bảo vệ bản quyền - Copyright Watermarking):* Nhúng cùng một thông tin bản quyền (ví dụ tên tác giả hoặc mã bản quyền của tổ chức) vào mọi bản sao phân phối. Mục tiêu là chứng minh quyền sở hữu tài sản trí tuệ.
  * *Kỹ thuật Đánh dấu định danh (Fingerprinting / Traitor Tracing):* Nhúng các thông tin định danh **khác nhau** (`issuance_id` riêng biệt) vào từng bản sao được cấp phát cho từng người nhận cụ thể. Khi tài liệu bị phát tán trái phép ra ngoài, nếu thủy vân được trích xuất thành công và `issuance_id` ánh xạ tới bản ghi cấp phát hợp lệ trong cơ sở dữ liệu, hệ thống sẽ xác định được bản sao rò rỉ xuất phát từ lần cấp phát nào, phục vụ công tác truy cứu trách nhiệm rò rỉ thông tin nội bộ.

### Câu hỏi 6: Tại sao SplitBind lại chia làm hai thuật toán thủy vân riêng biệt (Robust Watermark và Semi-fragile Watermark)? Không thể gộp thành một thuật toán được sao?
* **Trả lời trọng tâm:**
  * Việc phân tách xuất phát từ bài toán đánh đổi kỹ thuật (Engineering / Design Trade-off) giữa các mục tiêu an ninh thường cạnh tranh lẫn nhau:
    * *Robust Watermark (DWT-DCT-QIM):* Ưu tiên tối đa hóa khả năng sống sót qua các phép biến đổi tín hiệu để khôi phục toàn vẹn 128 bit định danh `issuance_id`.
    * *Semi-fragile Watermark (Block DCT + HMAC):* Ưu tiên độ nhạy cảm cục bộ với các thay đổi ngữ nghĩa nội dung để phát hiện các dấu hiệu can thiệp, đánh dấu khối nghi vấn và hỗ trợ khoanh vùng vị trí can thiệp.
  * Trong thực tế, việc thiết kế một thuật toán vừa có khả năng bỏ qua biến đổi trên diện rộng vừa nhạy bén khoanh vùng can thiệp cục bộ là thách thức kỹ thuật rất lớn. Việc phân tách thành hai bài toán độc lập là lựa chọn kiến trúc có chủ đích và phù hợp của nhóm nhằm đảm bảo tính khả thi thực nghiệm và tách bạch trách nhiệm nghiệp vụ.

### Câu hỏi 7: Mã băm mật mã (Cryptographic Hash như SHA-256) có phải là một thuật toán mã hóa (Encryption) không?
* **Trả lời trọng tâm:**
  * **Hoàn toàn không.** Đây là quan niệm sai lầm phổ biến cần phân định rạch ròi:
    * *Mã hóa (Encryption):* Là phép biến đổi hai chiều có khóa nhằm bảo vệ tính bí mật (Confidentiality). Tùy thuộc vào hệ mật mã, quá trình này có thể sử dụng cùng một khóa bí mật chung cho cả mã hóa và giải mã ($C = E_K(P)$ và $P = D_K(C)$ trong mật mã đối xứng), hoặc sử dụng cặp khóa bất đối xứng (khóa công khai dùng để mã hóa và khóa riêng tương ứng dùng để giải mã: $C = E_{pk}(P)$ và $P = D_{sk}(C)$ theo định nghĩa NIST). Mã hóa luôn được thiết kế để cho phép khôi phục lại bản rõ ban đầu khi sở hữu đúng khóa giải mã hợp lệ.
    * *Hàm băm mật mã (Cryptographic Hash):* Là hàm toán học một chiều không dùng khóa (Unkeyed One-way Function), ánh xạ dữ liệu đầu vào có độ dài tùy ý thành chuỗi bit đầu ra có độ dài cố định (256 bit đối với SHA-256). Về mặt toán học, hàm băm không phải là hàm có phép giải mã; bài toán tìm lại dữ liệu ban đầu từ mã băm (tìm tiền ảnh - preimage) được thiết kế để bất khả thi về mặt tính toán (computationally infeasible). Mục tiêu của hàm băm là kiểm tra tính toàn vẹn (Integrity) thông qua các tính chất kháng tiền ảnh và kháng va chạm.

### Câu hỏi 8: Nguyên lý Kerckhoffs được áp dụng như thế nào trong bài toán Thủy vân số? Nếu kẻ tấn công biết thuật toán DWT-DCT-QIM thì hệ thống có bị phá vỡ không?
* **Trả lời trọng tâm:**
  * Theo Nguyên lý Kerckhoffs: Độ an toàn của hệ thống không phụ thuộc vào việc giấu kín thuật toán, mà dựa trên việc giữ bí mật của khóa (Key). Tuy nhiên, cần phân định rạch ròi giữa khả năng kháng giả mạo (Forgery Resistance) và khả năng kháng gỡ bỏ / phá hủy đồng bộ (Removal & Desynchronization Resistance):
    1. *Kháng giả mạo (Forgery Resistance):* Việc giữ bí mật khóa và hạt giống CSPRNG (đối với vị trí nhúng fingerprint) cùng khóa HMAC $K$ (đối với thẻ xác thực semi-fragile) làm cho việc giả mạo có chủ đích trở nên khó khăn hơn nhiều và là một thành phần cốt lõi trong mô hình an ninh (security model). Với HMAC, việc không có khóa ngăn kẻ tấn công tính đúng có chủ đích thẻ xác thực; với payload định danh, việc không biết khóa phân bố khiến việc nhúng đè có chủ đích gặp trở ngại lớn (tuy nhiên không suy diễn thành mệnh đề phủ định tuyệt đối).
    2. *Kháng gỡ bỏ và phá vỡ đồng bộ (Removal & Desynchronization Resistance):* Việc giữ bí mật khóa không đồng nghĩa với việc thủy vân miễn nhiễm trước các biến đổi tín hiệu mù. Kẻ tấn công dù không biết khóa vẫn có thể áp dụng các phép nén JPEG, thay đổi kích thước hoặc cắt cúp để phá hủy khả năng giải mã hay làm mất đồng bộ hình học (chính thực nghiệm của nhóm đã chứng minh tỷ lệ giải mã về 0% trước JPEG-70 và Resize-0.75).

### Câu hỏi 9: Tại sao thế hệ V1 thất bại trước JPEG-70 và Resize-0.75, và nhóm đã khắc phục bằng cách nào?
* **Trả lời trọng tâm:**
  * *Với nén JPEG-70:* Chuẩn nén JPEG chia ảnh thành các khối $8 \times 8$ và lượng tử hóa thô các hệ số DCT bằng ma trận lượng tử lossy. Khi hệ số chất lượng giảm xuống 70, các hệ số DCT dải trung tần bị làm tròn rất mạnh, làm xô lệch giá trị hệ số vượt ra khỏi khoảng dung sai của lưới Parity-QIM, tạo ra quá nhiều lỗi bit vượt quá năng lực tự sửa sai của mã Reed-Solomon (tối đa 8 byte lỗi).
  * *Với Resize-0.75:* Hệ cơ sở DCT vẫn giữ nguyên tính trực giao toán học; tuy nhiên phép co giãn kích thước làm thay đổi lưới lấy mẫu không gian (sampling grid), nội suy lại các giá trị điểm ảnh và làm xô lệch ranh giới căn chỉnh (block alignment) của các khối $8 \times 8$. Sự xô lệch này làm biến đổi giá trị các hệ số tần số và phá vỡ hoàn toàn sự đồng bộ của lưới lượng tử hóa QIM.
  * *Cách nhóm đã khắc phục (V2 và V3):* `[Implemented]` Bốn thay đổi thiết kế, đối chiếu trực tiếp được giữa `contracts/algorithm/fingerprint-candidates.v1.json`, `.v2.json` và `.v3.json`:

    | Cơ chế | V1 | V2 | V3 | Giải quyết vấn đề nào |
    |---|---|---|---|---|
    | Dải nhúng | `HL` (chi tiết) | `LL` (xấp xỉ) | `LL` | JPEG lượng tử hóa dải tần cao mạnh nhất; chuyển sang dải xấp xỉ để tránh đúng chỗ bị phá |
    | Bước lượng tử `qim_delta` | quét 6.0–12.0 | ghép 24/32/48/64 | cố định **32.0** | Giảm lỗi bit thô, nhưng **một mình nó không đủ**: V2 quét tới 64.0 vẫn chỉ đạt tối đa 3/12 |
    | Đồng bộ hình học | `orb-ransac` | pilot FFT + ORB (3+1 giả thuyết) | pilot + **8 giả thuyết hình học**, dung sai tỉ lệ 0.001 | Resize làm lệch lưới lấy mẫu; tìm kiếm giả thuyết khôi phục lại lưới trước khi giải mã |
    | **Trải phổ** | không có | không có | **spread_delta 4.0, 64 chip/bit** | **Đây là cơ chế tạo ra bước nhảy.** Mỗi bit trải trên 64 hệ số nên hỏng cục bộ do nén được trung bình hóa |

  * *Bằng chứng cho thấy trải phổ mới là nguyên nhân, không phải bước lượng tử:* `[Experimentally observed]` V2 đã quét `qim_delta` qua 24 / 32 / 48 / 64 trên 1408 hàng (`status: complete`, 0 lỗi thực thi) mà tỷ lệ giải mã tốt nhất **không bao giờ vượt 3/12** ở bất kỳ mức nào, trong khi PSNR giảm đơn điệu và tại 64.0 tụt xuống 36.53 dB — **dưới cổng 38 dB**. V3 giữ nguyên `qim_delta = 32.0` đúng như một mức V2 đã thử (V2 đo 42.33 dB tại mức đó) nhưng đạt 9–10/12. Vì bước lượng tử được giữ bằng nhau, bước nhảy **không thể** quy cho cường độ sóng mang; khác biệt cấu trúc là trải phổ và tìm kiếm hình học mở rộng.
  * *Cái giá phải trả, đo được:* PSNR tối thiểu giảm từ 69.31 dB (V1) xuống 42.47 dB (V3), vẫn trên ngưỡng cổng 38 dB. Lưu ý phần giảm này thuộc bước chuyển **V1 → V2** (do đổi dải nhúng và nâng bước lượng tử), không phải V2 → V3.
  * *Kết quả:* JPEG-70 từ 0/12 lên 9/12 và Resize-0.75 từ 0/12 lên 8/12 trên cùng corpus. Quan trọng hơn, JPEG-70 **không còn gây mất mát nào so với kênh không tấn công** (Mục 7.2.2) — cơ chế nén đã hết là yếu tố giới hạn; nút thắt còn lại là độ phủ phiếu tile trên một fixture.
  * *Đã thử và loại trừ ba hướng tinh chỉnh tham số:* `[Experimentally observed]` Nhóm đã kiểm chứng và **bác bỏ** cả ba lever tham số của thiết kế hiện tại: (a) `qim_delta` — V2 quét 24→64 trên 1408 hàng, trần vẫn 3/12, và 64.0 phá cổng PSNR; (b) `tiles_per_page` — đọc mã nguồn cho thấy `derive_tiles_v3` trả về pool rồi embed chỉ dùng `tiles[:payload_repetitions]`, nên tham số này không tới được phép tính; (c) tham số trải phổ — thí nghiệm V4 ngày 2026-09-11 (192 hàng) cho thấy `spread_chips_per_bit` 128 **kém hơn** baseline (36–38/48 so với 39/48) và hạ `saturated_fraction_min` xuống 0.50 chỉ hoà (đổi 1 hàng crop lấy 1 hàng JPEG).
  * *Phát hiện quan trọng từ kết quả âm tính đó:* khi đổi tham số, **số hàng hỏng gần như không đổi nhưng trang bị hỏng thì đổi hẳn**. Baseline hỏng cả 4 tấn công trên `pdf-multi-mixed/p0` và giải mã sạch `pdf-one-vector/p0`; ở `saturated_fraction_min = 0.50` thì đảo ngược chính xác. Đây là dấu hiệu của bài toán **vị trí đặt sóng mang**, không phải **cường độ sóng mang**. Mọi tham số đã thử đều điều chỉnh *ghi mạnh bao nhiêu* hoặc *ghi bao nhiêu lần*, không tham số nào chọn *ghi ở đâu* theo nội dung trang, trong khi thứ tự tile hiện chỉ dựa trên HMAC-shuffle và khả năng sống sót qua cắt cúp — hoàn toàn mù nội dung.
  * *Hướng xử lý tiếp theo, có căn cứ:* **chọn sóng mang theo nội dung một cách tất định** — chấm điểm tile ứng viên theo độ kết cấu hoặc phương sai trước khi chọn `payload_repetitions` tile, vẫn tái lập được từ khóa. Đây là thay đổi thuật toán, không phải tham số. Xa hơn: bước lượng tử thích nghi theo mô hình thị giác người (HVS) và các kiến trúc học sâu (HiDDeN, StegaStamp) tự học lớp biến dạng nén JPEG vi phân.

### Câu hỏi 10: Vai trò của mã xác thực HMAC trong thuật toán Semi-fragile Tamper Localization là gì? Tại sao không so sánh trực tiếp các hệ số DCT mà phải băm qua HMAC?
* **Trả lời trọng tâm:**
  * Nếu chỉ nhúng trực tiếp các hệ số đặc trưng DCT hoặc băm bằng hàm không khóa (như SHA-256), kẻ tấn công sau khi chỉnh sửa nội dung khối có thể tự trích xuất đặc trưng mới, tự tính mã băm và nhúng đè lên các khối đối tác (Tấn công giả mạo thẻ - Tag Forgery Attack).
  * Bằng việc sử dụng HMAC-SHA256 với khóa bí mật $K$, việc không biết khóa ngăn chặn kẻ tấn công tính toán có chủ đích thẻ HMAC chính xác cho nội dung tùy ý sửa đổi.
  * *Lưu ý học thuật về thẻ rút gọn (Truncated HMAC 32-bit):* Do dung lượng nhúng của từng khối ảnh có hạn, thuật toán cắt ngắn thẻ HMAC xuống 4 byte (32 bit). Mặc dù RFC 2104 khuyến nghị thẻ MAC không dưới 80 bit và NIST lưu ý mức dưới 64 bit không khuyến khích cho ứng dụng an ninh cao, prototype nghiên cứu chấp nhận thẻ 32-bit để dung hòa với dung lượng nhúng của khối ảnh $128 \times 128$. Không có khóa $K$, kẻ tấn công không thể tính thẻ đúng một cách có chủ đích, nhưng thẻ 32-bit vẫn có xác suất đoán ngẫu nhiên $1/2^{32} \approx 2.33 \times 10^{-10}$ cho mỗi khối. Đây là một giới hạn về biên độ an toàn (security margin) cần được nêu rõ khi trình bày học thuật.

---

# PHẦN 9: HÀNG RÀO TUYÊN BỐ AN TOÀN CHO SLIDE & BÁO CÁO (CLAIM SAFETY GUIDE)

Để bảo đảm tính trung thực học thuật, tuyệt đối tránh lỗi cường điệu (overclaim) hoặc gây hiểu lầm cho Hội đồng chấm thi, thành viên soạn Slide và Báo cáo bắt buộc phải tuân thủ bảng ranh giới tuyên bố sau:

| Chủ đề / Lĩnh vực | Nội dung ĐƯỢC PHÉP tuyên bố (Allowed Claims) | Nội dung CẤM TUYÊN BỐ / Dễ gây hiểu lầm (Prohibited Claims) | Căn cứ Kỹ thuật & Bằng chứng Xác minh |
|---|---|---|---|
| **1. Trạng thái Production** | Phiên bản Production Release 0.1 đang chạy bảo vệ tính toàn vẹn tệp chính xác bằng Chữ ký số Ed25519 và SHA-256 trên Azure. | CẤM nói: "Production đã tích hợp bộ quét thủy vân tự động" hoặc "Hệ thống tự động trích xuất watermark trên server khi upload file". | `apps/web/src/features/evidence/copy.ts` hiển thị nhãn "Chưa tìm thấy bản cấp phát khớp"; API backend trả mã enum `NO_WATERMARK` với chú thích giới hạn. |
| **2. Độ Bền vững Thủy vân** | ĐƯỢC phép nói, kèm đúng tên thế hệ: thế hệ **V1** đạt 0/12 trước JPEG-70 và Resize-0.75; thế hệ nghiên cứu **V3** đo trên cùng corpus đạt **9/12 (JPEG-70)**, **9/12 (Crop-0.25)**, **8/12 (Resize-0.75)**, 0 gán sai trên 352 hàng. ĐƯỢC nói: "dưới JPEG-70 và Crop-0.25, V3 không mất thêm hàng nào so với kênh không tấn công". | CẤM nói: "Thủy vân bền vững trước mọi phép tấn công", "Chống chịu hoàn hảo mọi biến đổi hình ảnh", "V3 đã giải quyết xong JPEG-70", hoặc trình bày V3 như năng lực đã phát hành. CẤM nêu con số V3 mà bỏ phạm vi `research_measurement_only`. CẤM nêu con số 0% mà không nói rõ đó là V1. | V1: `fingerprint-profile-v1.md`. V3: `reports/fingerprint-pregate-v3/summary.json`, `status: complete`, 352/352 hàng, `profile_promoted: False`, `qualified_candidate_ids: []` vì chưa đạt cổng 0.95. Xem Mục 7.2. |
| **3. Định vị Can thiệp** | Thuật toán Semi-fragile chứng minh quy trình nghiên cứu phát hiện và định vị can thiệp với IoU thực nghiệm đạt ~0.09; bị chi phối bởi cơ chế fail-safe bảo vệ trước nén mạnh. | CẤM dùng các từ: "Định vị chính xác", "Khoanh vùng hoàn hảo", "Định vị rất tốt vùng sửa đổi". | 48 hàng benchmark thực nghiệm với Aggregate IoU = 0.089981; 38/48 hàng kích hoạt fail-safe (`integrity-profile-v1.md`). |
| **4. Tỷ lệ Gán sai (False Attribution)** | Trong 682 trường hợp benchmark đã xét trên 48 ứng viên, không quan sát thấy trường hợp false attribution nào (0 / 682). | CẤM nói: "Hệ thống tuyệt đối không bao giờ gán nhầm" hoặc "Không bao giờ vu khống người vô tội". | Số liệu thực nghiệm thống kê trên tập mẫu giới hạn, không phải chứng minh toán học cho mọi trường hợp vô hạn. |
| **5. Giá trị Pháp lý Chữ ký số** | Chữ ký số Ed25519 cung cấp đặc tính chống chối bỏ kỹ thuật (cryptographic non-repudiation); giá trị chứng cứ pháp lý tùy thuộc chính sách quản lý khóa và luật sở tại. | CẤM nói: "Chữ ký số có giá trị pháp lý tuyệt đối trong mọi trường hợp" hoặc xem `AGENTS.md` là "căn cứ pháp lý". | Khái niệm mật mã học phân biệt giữa tính chống chối bỏ kỹ thuật và giá trị pháp lý theo Luật Giao dịch điện tử. |
| **6. Độ Trung thực Cảm nhận (Fidelity)** | Các chỉ số khách quan đạt $\text{PSNR} = 41.69\text{ dB}$ và $\text{SSIM} = 0.9825$ trên biểu diễn ảnh trang render 144 DPI, thể hiện độ méo tín hiệu thấp. | CẤM nói: "Chứng minh mắt thường tuyệt đối không thể nhận thấy" hoặc "Chất lượng hình ảnh hoàn toàn không đổi". | PSNR/SSIM là mô hình đo lường khách quan; chưa thực hiện nghiên cứu đánh giá thị giác chủ quan trên người (MOS / User Study). |
| **7. Toàn vẹn Văn bản vs Hình ảnh** | Hệ thống bảo vệ văn bản PDF thông qua biểu diễn ảnh raster của từng trang tài liệu (Page-Image Watermarking) kết hợp ký số Manifest. | CẤM nói: "Thủy vân nhúng trực tiếp vào các ký tự text hoặc font của file PDF thô". | Pipeline thực tế: PDF $\rightarrow$ Render raster 144/300 DPI $\rightarrow$ Nhúng thủy vân trên kênh Luminance $\rightarrow$ Đóng gói lại PDF. |

---

# PHẦN 10: KHUYẾN NGHỊ TRỰC QUAN HÓA & PHÂN BỔ SLIDE (SLIDE & VISUAL MAPPING GUIDE)

Đề xuất khung 20 slide tiêu chuẩn bám sát 4 yêu cầu của Giảng viên và kiến trúc SplitBind:

```
[Khung Báo cáo BTL Nhóm 9 - 18 Slides]
├── MÀN 1: ĐẶT VẤN ĐỀ & BỐI CẢNH (Slides 1 - 3)
├── MÀN 2: LÝ THUYẾT DIGITAL WATERMARKING - YÊU CẦU 1 (Slides 4 - 6)
├── MÀN 3: ỨNG DỤNG THỦY VÂN TRONG TRUY VẾT & TOÀN VẸN - YÊU CẦU 2 (Slides 7 - 10)
├── MÀN 4: ỨNG DỤNG KÝ SỐ & GIẢI QUYẾT MÂU THUẪN - YÊU CẦU 3 (Slides 11 - 13)
├── MÀN 5: MA TRẬN SO SÁNH CÁC KỸ THUẬT TOÀN VẸN - YÊU CẦU 4 (Slides 14 - 15)
└── MÀN 6: THỰC THI HỆ THỐNG SPLITBIND, THỰC NGHIỆM & KẾT LUẬN (Slides 16 - 20)
```

### Chi tiết Phân bổ Từng Slide và Khuyến nghị Trực quan:

1. **Slide 1: Trang tiêu đề:** Tên đề tài, Nhóm 9, Giảng viên hướng dẫn TS. Hồ Đăng Thế. (Hình thức: Tinh gọn, chuyên nghiệp).
2. **Slide 2: Đặt vấn đề & Thách thức bảo vệ toàn vẹn tài liệu:** Nguy cơ rò rỉ tài liệu nội bộ qua chụp màn hình, in-scan; sự bất lực của chữ ký số truyền thống khi tệp bị biến đổi byte thô. (Hình thức: Sơ đồ dòng rò rỉ tài liệu).
3. **Slide 3: Mục tiêu & Bốn yêu cầu cốt lõi:** Trình bày rõ 4 yêu cầu giảng viên giao và giải quyết nghịch lý "Văn bản vs Hình ảnh" (Page-Image Watermarking). (Hình thức: 4 khối nội dung trực quan).
4. **Slide 4: Cơ sở Lý thuyết Thủy vân số (Digital Watermarking):** Khái niệm, mục tiêu an ninh, phân loại theo miền nhúng (Không gian vs Tần số: DCT, DWT, DFT). (Hình thức: Sơ đồ phân nhánh kỹ thuật).
5. **Slide 5: Tam giác Đánh đổi Cốt lõi (Trade-off Triangle):** Robustness $\leftrightarrow$ Imperceptibility $\leftrightarrow$ Capacity. Giải thích ràng buộc đánh đổi kỹ thuật (Engineering / Design Trade-off) giữa độ bền vững, độ tàng hình và dung lượng tải trọng. (Hình thức: Đồ họa hình tam giác đánh đổi với 3 đỉnh).
6. **Slide 6: Kỹ thuật Điều chế Chỉ số Lượng tử (QIM):** Nguyên lý Parity-QIM, bước lượng tử hóa $\Delta$, cơ chế giải mã mù (Blind Extraction). (Hình thức: Trục số lượng tử hóa so le chẵn/lẻ).
7. **Slide 7: Bài toán A - Truy vết Nguồn phát hành (Traitor Tracing):** Định nghĩa bài toán, cấu trúc payload chuẩn hóa 23 byte (`"SB"` + version + UUID 16B + CRC-32), mã sửa lỗi Reed-Solomon 39 byte. (Hình thức: Sơ đồ phân rã khối byte payload).
8. **Slide 8: Pipeline Nhúng & Trích xuất DWT-DCT-QIM:** Luồng xử lý Haar DWT cấp 1, chia khối DCT $8 \times 8$, CSPRNG key, bộ căn chỉnh hình học ORB-RANSAC dựa trên mẫu đồng bộ (SyncTemplate). (Hình thức: Sơ đồ khối pipeline dạng ngang Flowchart LR).
9. **Slide 9: Bài toán B - Phát hiện & Định vị Sửa đổi (Tamper Localization):** Nguyên lý Semi-fragile, lưới khối $128 \times 128$, trích xuất đặc trưng DCT tần số thấp, thẻ xác thực HMAC-SHA256 4 byte, phân tán khối đối tác (Partner Ring). (Hình thức: Sơ đồ lưới ảnh và liên kết khối đối tác).
10. **Slide 10: Kết quả Thực nghiệm Định vị Can thiệp & Ranh giới Kỹ thuật:** Trình bày 4 dạng can thiệp (`replace_text`, `cover_region`, `copy_move`, `insert_object`), số liệu IoU = 0.089981, giải thích cơ chế fail-safe bảo vệ trước nén mạnh. (Hình thức: Bảng số liệu kết hợp hình ảnh trực quan 4 ca can thiệp).
11. **Slide 11: Ứng dụng Ký số trong Bảo vệ Thông tin Truy vết:** Cấu trúc Hồ sơ toàn vẹn (Manifest RFC 8785 JCS), thuật toán ký Ed25519, liên kết `issuance_id` giữa thủy vân và chữ ký số. (Hình thức: Sơ đồ cấu trúc dữ liệu Manifest và quy trình ký).
12. **Slide 12: Giải quyết Mâu thuẫn giữa Thủy vân số và Chữ ký số:** Phân tích câu hỏi của Giảng viên: "Nhúng trước, Ký sau"; phân tầng phòng thủ Defense-in-Depth giữa Kênh số nguyên bản và Kênh rò rỉ analog/lossy. (Hình thức: Sơ đồ hai nhánh luồng xác minh - Dual Verification Paths).
13. **Slide 13: Ba cấp độ Kiến trúc & Minh bạch Trạng thái Vận hành:** Phân định rõ Cấp độ A (Payload), Cấp độ B (Kiến trúc liên kết) và Cấp độ C (Production Release 0.1). Giải thích nhãn UI "Chưa tìm thấy bản cấp phát khớp". (Hình thức: Bảng phân cấp 3 tầng rõ ràng).
14. **Slide 14: Ma trận So sánh Đa chiều Toàn diện (Yêu cầu 4):** Trình bày bảng so sánh 6 kỹ thuật (Hash, HMAC, Digital Signature, Robust WM, Semi-fragile WM, Steganography) qua 7 tiêu chí an ninh. (Hình thức: Bảng ma trận nổi bật các điểm mạnh/yếu).
15. **Slide 15: Phân tích Tương phản Chuyên sâu:** So sánh Watermarking vs Steganography (mục tiêu giấu tin); Watermarking vs Digital Signature (kênh số vs kênh analog); CRC-32 vs HMAC (lỗi ngẫu nhiên vs toàn vẹn mật mã). (Hình thức: 3 khối so sánh song song).
16. **Slide 16: Hiện thực Hệ thống SplitBind & Môi trường Production:** Kiến trúc đám mây: Caddy, React Vite, Django API, Neon Postgres, Cloudflare R2 trên Azure VM (`https://splitbind.qivarn.id.vn`). Ảnh chụp giao diện cấp phát và xác thực. (Hình thức: Sơ đồ kiến trúc triển khai thực tế).
17. **Slide 17: Bảng Tổng hợp Số liệu Thực nghiệm Đã khóa (Frozen Metrics):** Bảng số liệu chuẩn thế hệ V1: PSNR 41.69 dB, SSIM 0.9825, 32.736 hàng V1, False attribution 0.00% (0/682), IoU ~ 0.09. Ghi rõ trên slide rằng đây là số của **thế hệ V1**. (Hình thức: Thẻ thông số nổi bật - Key Metric Cards).
18. **Slide 18 (MỚI): Tiến hóa Thuật toán V1 → V3 và Kết quả Cải thiện Độ bền:** Slide có sức nặng kỹ thuật cao nhất của báo cáo. Trình bày ba nội dung:
    * *Bảng đối chiếu trên cùng corpus:* JPEG-70 `0/12 → 9/12`, Resize-0.75 `0/12 → 8/12`, Crop-0.25 `1/3 → 9/12`, lỗi thực thi `31/682 → 0/352`. Nhấn mạnh cùng corpus `e5837cd4…`, cùng cổng, cùng mẫu số nên so sánh có kiểm soát.
    * *Bốn thay đổi thiết kế và vấn đề mỗi thay đổi giải quyết:* dải nhúng `HL → LL`, `qim_delta` `6–12 → 32`, đồng bộ `orb-ransac → pilot + 8 giả thuyết hình học`, và trải phổ `64 chip/bit` (chi tiết ở Câu hỏi 9).
    * *Phát hiện then chốt:* dưới JPEG-70 và Crop-0.25, V3 trượt **đúng ba trang mà phép đo không tấn công cũng trượt — không thêm hàng nào**. Nén đã hết là yếu tố giới hạn; nút thắt còn lại là độ phủ phiếu tile, và ba hàng đó có `bit_error_rate = 0.0`.
    * *Bắt buộc nêu kèm:* `research_measurement_only`, `profile_promoted: False`, chưa đạt cổng 0.95, production vẫn chạy V2.
    (Hình thức: Bảng đối chiếu hai cột V1/V3 kết hợp biểu đồ cột nhóm; thêm một dòng nhỏ ghi phạm vi bằng chứng.)
19. **Slide 19 (MỚI): Chẩn đoán Nguyên nhân Gốc & Đóng góp Đề xuất của Nhóm:** Slide trả lời trực tiếp phần "**đề xuất**" của đề bài (chi tiết ở PHẦN 13). Ba nhịp:
    * *Chẩn đoán:* bộ giải mã chỉ sinh giả thuyết hình học cho ba trường hợp — giữ nguyên, co giãn đều, và cắt cúp tại **đúng một tỉ lệ cứng** `0.8660`. Ngoài ba trường hợp đó, tầng payload không bao giờ được chạy tới.
    * *Bằng chứng:* bảng tương quan hoàn hảo — mọi phép biến đổi sinh được giả thuyết đạt 7–11/12, mọi phép không sinh được đạt 0–2/12, không ngoại lệ. Kèm nghịch lý crop 10% (2/12) tệ hơn crop 25% (7/12) vì 25% chính là tỉ lệ được cứng hoá.
    * *Kiểm chứng:* bóc viền letterbox đưa screenshot 1920×1080 từ **0/12 lên 9/12**, đúng bằng tỉ lệ resize-0.50, mà **không đổi một tham số nào của thủy vân**.
    (Hình thức: sơ đồ ba nhánh giả thuyết hình học; bảng tương quan; ảnh trước/sau bóc viền kèm hai con số 0/12 → 9/12.)
20. **Slide 20: Tổng kết, Đóng góp & Hướng nghiên cứu tiếp theo:** Tóm tắt kết quả; thừa nhận giới hạn (V3 chưa đạt cổng 0.95; IoU định vị ~ 0.09). Phần hướng phát triển nên trình bày như một **kết luận có căn cứ thực nghiệm**, không phải danh sách ước muốn:
    * Nhóm đã kiểm chứng và loại trừ cả ba lever tham số (`qim_delta`, `tiles_per_page`, tham số trải phổ) bằng ba loại bằng chứng khác nhau: sweep 1408 hàng của V2, đọc mã nguồn, và thí nghiệm V4 192 hàng.
    * Kết quả âm tính chỉ ra nút thắt thật: đổi tham số làm **đổi trang bị hỏng** chứ không giảm số hàng hỏng — đây là bài toán vị trí đặt sóng mang, không phải cường độ.
    * Hướng tiếp theo: chọn sóng mang theo nội dung một cách tất định; sau đó mới tới bước lượng tử thích nghi HVS và Deep Watermarking (HiDDeN, StegaStamp).
    (Hình thức: ba khối — đã thử gì, học được gì, làm gì tiếp.)

---

# PHẦN 11: TÀI LIỆU THAM KHẢO HỌC THUẬT CHUẨN IEEE (ACADEMIC REFERENCES)

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

---

# PHẦN 13: ĐỀ XUẤT KIẾN TRÚC V4 — CHẨN ĐOÁN NGUYÊN NHÂN GỐC VÀ HƯỚNG SỬA

`[Experimentally observed]` `[Implemented]` `[Limitation]`

Đề bài yêu cầu "tìm hiểu và **đề xuất**" một hệ thống. Phần này là đóng góp đề xuất của nhóm: một chẩn đoán nguyên nhân gốc dựa trên số đo, một phép kiểm chứng đã thực hiện, và kiến trúc V4 rút ra từ đó.

## 13.1. Chẩn đoán: nút thắt nằm ở tập giả thuyết hình học, không ở thủy vân

Đọc `geometry_v3.search_geometry_v3`, bộ giải mã chỉ sinh ứng viên chuẩn tắc từ đúng ba nguồn:

1. `identity` — chỉ khi raster bị tấn công có đúng kích thước chuẩn tắc.
2. `pure_resize` — chỉ khi **hai trục co giãn cùng một tỉ lệ**, sai số `geometry_ratio_tolerance = 0.001`.
3. `center_crop` — chỉ cho các tỉ lệ nằm trong `profile.crop_retained_scales`, vốn bị đóng băng ở **đúng một giá trị** `0.8660254037844386`.

Ngoài ba trường hợp đó, bộ giải mã **không sinh được giả thuyết hình học nào**, nên tầng payload không bao giờ được chạy tới — bất kể sóng mang mạnh đến đâu.

## 13.2. Bằng chứng: tương quan hoàn hảo giữa "có giả thuyết" và "truy vết được"

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

## 13.3. Kiểm chứng: bóc viền letterbox khôi phục truy vết screenshot

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

## 13.4. Kiến trúc V4 đề xuất

Xếp theo tỉ lệ lợi ích trên chi phí đo được:

**Tầng 1 — Chuẩn hoá khung ảnh trước khi giải mã (đã kiểm chứng).**
Bóc viền đồng màu; mở rộng sang phát hiện biên trang và khử nghiêng. Bộ giải mã V3 ngầm giả định đầu vào đã được đóng khung giống hệt bản phát hành, trong khi **kênh rò rỉ thật không bao giờ như vậy**. Đây là tầng cho nhiều độ bền nhất trên mỗi dòng mã.

**Tầng 2 — Ước lượng tỉ lệ cắt thay vì liệt kê.**
Thay `crop_retained_scales` cố định bằng tìm kiếm tỉ lệ, hoặc ước lượng tỉ lệ từ tương quan log-polar của pilot (hạ tầng này **đã có sẵn** trong `synchronization_v2.py`). Xoá điểm tối ưu quá mức tại 0.25 và làm crop 0.10 / 0.50 trở nên xử lý được.

**Tầng 3 — Cho phép hai trục co giãn độc lập.**
Ràng buộc `ratios_agree` loại bỏ mọi phép biến đổi đổi tỉ lệ khung. Nới nó ra cho phép xử lý ảnh bị kéo méo và bù phối cảnh.

**Tầng 4 — Chọn sóng mang theo nội dung (chưa kiểm chứng).**
Chấm điểm tile ứng viên theo kết cấu trước khi chọn, vẫn tất định từ khoá. Giải quyết việc *trang nào* hỏng **bên trong** một phép biến đổi mà bộ giải mã đã hoàn tác được — hiệu ứng thứ cấp thật, nhưng không phải nguyên nhân của các thất bại diện rộng.

## 13.5. Cái gì kiến trúc này không sửa được

`[Limitation]`

- **Giới hạn phân giải là thật.** Dưới tỉ lệ khoảng 0.45, payload chết kể cả khi hình học hoàn hảo. Không tầng nào ở trên chạm tới điều đó; muốn sửa phải tăng dung lượng hoặc giảm payload, và nhóm đã đo được rằng nâng `qim_delta` **không** phải lối ra (V2 quét 24→64, trần vẫn 3/12).
- **JPEG-50 là thất bại sóng mang thật** (lớp 3): hình học đúng vì ảnh không đổi kích thước, nhưng nén phá huỷ tín hiệu. Đây là giới hạn mà không tầng kiến trúc nào ở trên chạm tới được, và ba lever tham số đã bị bác bỏ bằng đo đạc, nên hướng duy nhất còn lại là tăng dung lượng kênh hoặc giảm payload.
- **Toàn bộ số trong phần này đến từ harness nghiên cứu, không phải pre-gate**, và khác pre-gate ở cách dẫn xuất RNG tấn công cùng việc cấp mẫu đồng bộ ORB cho bộ giải mã. Không được trộn với Mục 7.2, và không được trình bày như năng lực đã phát hành. Production vẫn chạy V2 với xác thực toàn vẹn tệp chính xác.

## 13.6. Vì sao chẩn đoán này có được

Đáng ghi nhận về mặt phương pháp: chẩn đoán trên chỉ tìm ra được **vì dự án đã ghi lại bằng chứng đúng cách**. Mã trạng thái phân biệt `insufficient_sync_evidence` với `payload_not_detected` là thứ tách được hai nguyên nhân; hợp đồng tấn công có sẵn họ `screenshot` để đo; corpus khoá theo hash làm phép so sánh có kiểm soát. Một dự án ghi chép cẩu thả sẽ không để lại gì để kiểm toán.

---

# PHẦN 12: PHỤ LỤC: MA TRẬN TRUY VẾT KHẲNG ĐỊNH VÀ BẰNG CHỨNG (CLAIM / EVIDENCE TRACEABILITY MATRIX)

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
