# Điều khiển ứng dụng GUI Windows từ agent

Hướng dẫn đọc: mục 1 là cách chạy một ứng dụng cài đặt mà không cần quyền quản trị; mục 2-3
là hai lỗi làm hỏng thao tác bàn phím và ảnh chụp; mục 4-6 là các bẫy khi điều khiển menu và
cửa sổ con của ứng dụng MFC; mục 7 là quy tắc chọn kích thước cửa sổ khi ảnh chụp sẽ đưa vào
báo cáo.

Bối cảnh quan sát: điều khiển CrypTool 1.4.42 (ứng dụng MFC 32 bit) bằng `winapp ui` trên
Windows 11 để chụp ảnh từng bước cho một báo cáo.

## 1. Trình cài đặt NSIS giải nén được bằng 7-Zip, không cần UAC

Một trình cài đặt NSIS (`Nullsoft`) có manifest `highestAvailable` sẽ bật hộp thoại UAC khi
chạy, và agent không bấm được hộp thoại đó vì nó nằm trên secure desktop.

Cách đi vòng: giải nén thẳng gói cài đặt bằng 7-Zip rồi chạy tệp `.exe` trong thư mục giải
nén.

```bash
"C:/Program Files/7-Zip/7z.exe" x -y -o"<thu muc dich>" "<setup.exe>"
```

Nhận diện loại trình cài đặt trước khi thử: đếm chuỗi `Nullsoft`, `Inno Setup`,
`InstallShield` trong tệp nhị phân. Đầu ra của 7-Zip cũng ghi rõ `SubType = NSIS-3`.

Ứng dụng chạy được ở dạng portable hay không thì phải kiểm chứng bằng cách chạy thật; với
CrypTool 1.4.42 thì chạy được, chỉ thiếu các chức năng cần phần mềm ngoài (bản hoạt hình
thuật toán cần Java).

## 2. Bộ gõ tiếng Việt làm hỏng phím gửi bằng send-input

Gõ chuỗi `DES` bằng `winapp ui send-keys ... --via send-input` cho ra `DÉ` trên máy đang bật
bộ gõ Telex: `e` + `s` bị bộ gõ ghép thành `é`. Lỗi này im lặng, không có thông báo nào.

Cách chữa đã kiểm chứng: đưa văn bản qua clipboard rồi dán.

```bash
powershell -NoProfile -Command "Set-Clipboard -Value '...'"
winapp ui send-keys "ctrl+v" -w <hwnd> --via send-input
```

Quy tắc rút ra: **không bao giờ gõ văn bản có nghĩa bằng phím tổng hợp trên máy có bộ gõ
tiếng Việt**; chỉ dùng `send-keys` cho phím điều khiển (`ctrl+n`, `escape`, `enter`).

Hệ quả phụ: `ctrl+a` gửi tới cửa sổ hộp thoại không phải lúc nào cũng chọn hết nội dung ô
nhập đang có tiêu điểm. Nếu cần thay nội dung, dùng `set-value` để xóa trước rồi mới dán, và
kiểm lại bằng ảnh chụp.

## 3. Chụp ảnh: công cụ chụp theo tiến trình ghép mọi cửa sổ vào một ảnh

`winapp ui screenshot -a <pid>` ghép tất cả cửa sổ của tiến trình thành một ảnh nằm ngang,
không dùng được làm hình minh họa.

Dùng PowerShell chụp đúng hình chữ nhật của một cửa sổ:

```powershell
$r = New-Object RECT
[Win]::GetWindowRect([IntPtr]$Hwnd, [ref]$r)
$bmp = New-Object System.Drawing.Bitmap($w, $h)
[System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen($r.Left, $r.Top, 0, 0, $size)
```

Ưu điểm quyết định: `CopyFromScreen` **không cướp tiêu điểm**, nên menu đang mở vẫn còn khi
chụp. Mọi cách chụp có kích hoạt cửa sổ đều làm menu tự đóng.

## 4. Hộp thoại còn sót làm mọi thao tác menu thất bại với thông báo sai

Một hộp thoại lỗi chưa đóng khiến cửa sổ chính không nhận thao tác, và lệnh mở menu trả về
"không tìm thấy mục menu". Thông báo đó dẫn người đọc đi sai hướng: vấn đề không nằm ở menu.

Quy tắc: trước mỗi chuỗi thao tác, quét hộp thoại còn mở và đóng chúng; sau mỗi lần bấm nút,
quét lại. Khi tìm hộp thoại để thao tác, **lọc theo tiêu đề** (`Key Entry`, `Schroedel`, ...)
chứ đừng lấy hộp thoại đầu tiên có lớp `#32770`, vì hộp thoại lỗi cũng cùng lớp đó.

## 5. Selector của UI Automation đổi sau mỗi lần tìm

`winapp ui search` trả về selector dạng `mnu-encryptdecrypt-9ba3` với hậu tố băm thay đổi
giữa các lần gọi. Không lưu selector để dùng lại ở bước sau; tìm lại ngay trước khi bấm.

Ngược lại, `automationId` số của nút trong hộp thoại (ví dụ `1314` cho nút Encrypt) thì ổn
định giữa các phiên, dùng lại được.

## 6. Ứng dụng MFC dạng MDI: bấm nút phóng to có thể kích hoạt nhầm cửa sổ con

Tìm nút `Maximize` bằng `search` sẽ trả về nhiều kết quả, mỗi cửa sổ con một nút. Bấm nhầm
nút của cửa sổ con khác sẽ **kích hoạt cửa sổ đó**, và ảnh chụp sau đó ghi lại sai nội dung -
một lỗi im lặng, vì lệnh vẫn báo thành công.

Hai cách tránh: chỉ phóng to **một lần** ở đầu phiên, vì cửa sổ con mới sẽ kế thừa trạng thái
phóng to; và sau mỗi thao tác, kiểm tra `MainWindowTitle` để chắc chắn cửa sổ đang hoạt động
đúng là cửa sổ vừa sinh ra.

Đọc tiêu đề cửa sổ chính là phép kiểm rẻ nhất cho "thao tác vừa rồi có tác dụng không", vì
ứng dụng MFC thường ghi cả tham số vào tiêu đề.

## 7. Chọn bề rộng cửa sổ theo bề rộng hình trong báo cáo

Chữ trong ảnh chụp nhỏ đi theo đúng tỉ lệ thu phóng khi đặt ảnh vào trang. Với cột chữ A4
rộng 15,5 cm:

| Bề rộng ảnh | Mật độ trên trang | Cỡ chữ giao diện 11 px hiện ra |
|---|---|---|
| 1280 px | 210 dpi | khoảng 3,8 pt - không đọc được khi in |
| 820 px | 134 dpi | khoảng 6 pt - đọc được |
| 700 px | 115 dpi | khoảng 7 pt - thoải mái |

Vì vậy hãy **thu nhỏ cửa sổ ứng dụng trước khi chụp** thay vì chụp rộng rồi thu ảnh lại. Khi
ảnh đã chụp rồi, cắt bớt vùng trống bằng Pillow là cách cứu vãn: quét từ dưới lên tìm hàng
điểm ảnh đầu tiên không đồng nhất, chỉ lấy mẫu ở các cột bên trong (bỏ 20 px trái và 40 px
phải) vì viền cửa sổ có đổ bóng làm hàng nào cũng khác nhau.

## 8. "Java is not installed" của phần mềm cũ thường là lỗi đọc số phiên bản

CrypTool 1.4.42 từ chối mở phần hoạt hình với thông báo
`Java is not installed. You need at least Java 1.7.` trên máy đã cài JDK 25 và `java -version`
chạy bình thường. Thông báo sai hướng: Java có, chỉ là chương trình không đọc được.

Cách truy nguyên nhanh hơn đoán mò là **đọc chuỗi trong tệp nhị phân**, cả dạng ASCII lẫn
UTF-16LE. Ở đây chuỗi `java -XshowSettings:all` cùng `java.version` và `sun.arch.data.model`
lộ ra toàn bộ cơ chế: chương trình chạy `java -XshowSettings:all` rồi phân tích đầu ra. Nó
cũng cho thấy có hai thông báo khác nhau, một cho "không tìm thấy Java" và một cho "phiên bản
không đạt", nên nội dung thông báo giúp phân biệt hai tình huống.

Nguyên nhân gốc là cách đánh số phiên bản Java đổi từ bản 9: `1.8.0_452` thành `25.0.4.1`.
Phần mềm viết trước 2017 thường khớp mẫu `1.x` nên coi mọi JVM hiện đại là không hợp lệ.

Cách chữa đã kiểm chứng: cài thêm một JRE 8 song song, không gỡ JVM mới.

```bash
winget install --id EclipseAdoptium.Temurin.8.JRE --silent \
  --accept-package-agreements --accept-source-agreements
```

Hai chi tiết đi kèm:

- Bộ cài Temurin 8 tạo khóa `HKLM\SOFTWARE\JavaSoft\Java Runtime Environment`, còn bộ cài
  JDK 25 mặc định thì không. Nếu chương trình dò theo registry thay vì PATH thì đây mới là
  thứ làm nó chạy.
- Tiến trình con thừa hưởng PATH của tiến trình cha. Một shell mở từ trước khi cài Java sẽ
  không thấy `java`, và ứng dụng khởi động từ shell đó cũng vậy. Đặt PATH tường minh khi khởi
  chạy, hoặc mở shell mới.

Bài học chung: khi một phụ thuộc bị báo thiếu, hãy cài nó rồi thử lại thay vì ghi nhận giới
hạn. Nếu bản mới nhất không chạy được, một bản cũ cài song song thường giải quyết xong vấn đề
trong vài phút.

Xem thêm [[docx-report-assembly]] về khâu ghép ảnh vào tài liệu Word.
