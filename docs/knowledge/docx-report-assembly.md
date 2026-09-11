# Lắp ráp báo cáo DOCX bằng pandoc và vá OOXML

Hướng dẫn đọc: mục 1-2 là những lỗi làm Word **không mở được file** (sửa trước tiên);
mục 3-5 và 7-8 là lỗi **hiển thị sai** dù file hợp lệ; mục 6 là bẫy khi tự kiểm chứng
bằng regex; mục 9 nói vì sao một bản render không tự động là bằng chứng.

Bối cảnh: báo cáo được dựng bằng `pandoc --reference-doc`, sau đó ghép trang bìa lấy
nguyên từ một file `.docx` mẫu khác. Mọi kết luận dưới đây đều quan sát được từ đầu ra
thực tế, không suy đoán.

## 1. Namespace của mảnh ghép phải được hợp nhất vào thẻ `w:document`

`<w:document>` do pandoc sinh ra chỉ khai báo 9 namespace. Trang bìa lấy từ file Word
thật dùng tới 37, kèm `mc:Ignorable`. Dán nguyên mảnh có tiền tố `w14:`, `wp14:`, `mc:`
vào tài liệu không khai báo chúng khiến Word báo *không thể mở file* và đề nghị khôi phục.

Cách xử lý: lấy hợp của các `xmlns:*` từ thẻ `<w:document>` của file mẫu, thêm những
tiền tố còn thiếu vào thẻ gốc, rồi gộp luôn danh sách `mc:Ignorable` của hai bên.

## 2. Trong `[Content_Types].xml`, mọi `Default` phải đứng trước mọi `Override`

Lược đồ quy định thứ tự này. Thêm `<Default Extension="png" .../>` vào **cuối** file,
tức sau các `<Override>`, cũng làm Word từ chối mở. Chèn ngay trước `<Override>` đầu tiên.

## 3. Không có `w:pgSz` thì khổ giấy là do máy in mặc định quyết định

`reference.docx` mặc định của pandoc **không chứa `w:pgSz`**. Vá `w:pgMar` mà quên `w:pgSz`
nghĩa là bộ lề đúng đang được áp lên một khổ giấy không xác định. Phải ghi rõ A4:

```xml
<w:pgSz w:w="11906" w:h="16838"/>
```

Hệ quả thực tế: mẫu bìa của trường dùng khổ **Letter** (`12240 x 15840`). Khi chỉ chép
`pgMar` (trái 1701, phải 1134) sang mà không chép `pgSz`, bảng rộng 9350 twips vốn vừa
khít cột chữ Letter (9405 twips) bị **tràn 279 twips** trên cột chữ A4 (9071 twips).
Luôn chép `pgSz` cùng với `pgMar` khi ghép nội dung giữa hai file.

## 4. Phông chữ nằm ở theme, không chỉ ở `styles.xml`

Các style tham chiếu `w:asciiTheme="minorHAnsi"` / `majorHAnsi` sẽ phân giải qua
`word/theme/theme1.xml`. Chỉ sửa `styles.xml` mà bỏ qua theme thì Word vẫn hiển thị phông
của theme (bản pandoc hiện tại là `Aptos Display` / `Aptos`). Cần làm cả hai việc:

1. Ghi đè `<a:latin typeface="..."/>` trong `theme1.xml`.
2. Thay mọi thuộc tính `w:asciiTheme` / `w:hAnsiTheme` / `w:eastAsiaTheme` / `w:csTheme`
   bằng `w:ascii` / `w:hAnsi` / ... với tên phông tường minh.

## 5. Viền bảng không hiện: kiểm tra hình học trước khi thêm XML viền

Thứ tự chẩn đoán đúng khi một cạnh bảng không hiển thị, từ rẻ đến đắt:

1. **Bề rộng bảng so với cột chữ.** `tblW` kiểu `auto` cộng `tblLayout` không khai báo
   khiến Word tự co giãn, và bảng rộng hơn cột chữ sẽ bị đẩy lệch.
2. **`numPr` trỏ tới `numId` không tồn tại.** Mảnh ghép mang theo `<w:numPr>` nhưng
   `word/numbering.xml` của file mẫu không được chép sang, nên đoạn văn nhận thụt lề mặc định.
3. **`tblPrEx`** ở cấp hàng có thể ghi đè `tblBorders` của bảng.
4. **`tblStyle` trỏ tới style không tồn tại** cộng `tblLook` bật định dạng có điều kiện
   (`w:firstColumn="1"`) khiến Word xoá cạnh theo style mặc định.

Khi đã vá tới lớp `tcBorders` (mức ưu tiên cao nhất trong OOXML) mà vẫn sai, hãy **dựng
lại bảng** thay vì vá tiếp: giữ nguyên các `<w:p>` trong ô, còn `tblPr`, `tblGrid`, `tcPr`
thì sinh mới với bề rộng cố định vừa đúng cột chữ.

Trật tự phần tử là bắt buộc theo lược đồ, sai trật tự thì Word bỏ qua phần tử:

| Vùng | Trật tự |
|---|---|
| `tblPr` | `tblStyle`, `tblW`, `jc`, `tblInd`, `tblBorders`, `tblLayout`, `tblCellMar`, `tblLook` |
| `tcPr` | `tcW`, `gridSpan`, `vMerge`, `tcBorders`, `shd`, `tcMar`, `vAlign` |
| `pPr` | `pStyle`, `numPr`, `spacing`, `ind`, `jc`, ... và `rPr` **luôn ở cuối** |

Sai trật tự ở đây **không báo lỗi**: file vẫn hợp lệ, Word vẫn mở được, thuộc tính chỉ đơn
giản bị bỏ qua. Đã hai lần trong dự án này một phép chèn `<w:jc>` đặt trước `<w:pStyle>`
khiến bản vá im lặng không có tác dụng, trong khi phép đếm "đã sửa bao nhiêu đoạn" vẫn báo
thành công. Viết một hàm chèn dùng chung: tìm `<w:pStyle .../>` ở đầu `pPr`, chèn thuộc
tính **ngay sau** nó, và kiểm chứng bằng cách đếm số `pPr` còn sai trật tự, không phải bằng
số lần thay thế.

## 6. Regex tự kiểm chứng dễ báo sai

Hai bẫy đã thực sự gây báo động giả trong dự án này:

- `<w:pStyle w:val="X"/>` **không** khớp đầu ra pandoc, vì pandoc ghi `<w:pStyle w:val="X" />`
  có dấu cách trước dấu đóng. Dùng `\s*/>`.
- `<w:t[^>]*>` khớp luôn `<w:tbl>` và `<w:tc>`. Muốn lấy đúng phần tử văn bản phải dùng
  `<w:t(?:\s[^>]*)?>`.
- `[^/]*` bên trong `<w:thẻ[^/]*/>` chết ngay khi thuộc tính chứa URI, ví dụ
  `w:uri="http://schemas.microsoft.com/office/word"`. Dùng `[^>]*` hoặc bắt cả khối.
- **Trật tự thuộc tính không ổn định.** pandoc ghi lại `<w:style w:customStyle="1"
  w:styleId="Compact" w:type="paragraph">` với thứ tự khác file gốc, nên regex kiểu
  `<w:style [^>]*w:styleId="Compact">` không khớp. Định vị style bằng `str.find` trên
  `w:styleId="..."` rồi lùi về `<w:style ` gần nhất, đừng giả định trật tự.

Kiểm tra tính hợp lệ của toàn bộ gói bằng cách parse mọi part `.xml` và `.rels` bằng
`xml.dom.minidom.parseString`, thay vì chỉ nhìn một vài regex.

## 7. Thiếu `compatibilityMode` thì Word mở ở chế độ tương thích Word 2007

`settings.xml` của `reference.docx` mặc định pandoc **không có khối `w:compat` nào**. Khi
`compatibilityMode` vắng mặt, Word giả định giá trị 12, tức chế độ Word 2007, và hiện chữ
*Compatibility Mode* trên thanh tiêu đề. Chế độ này dùng luật dàn trang và dàn bảng cũ.

Thêm vào `settings.xml`, đặt **trước `w:rsids`** cho đúng trật tự lược đồ:

```xml
<w:compat>
  <w:compatSetting w:name="compatibilityMode"
                   w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
</w:compat>
```

## 8. Style `Compact` của pandoc không khai báo căn lề

pandoc gán style `Compact` cho đoạn văn trong **ô bảng** và trong **danh sách gọn**. Định
nghĩa gốc của nó chỉ có `w:spacing`, không có `w:jc`, nên nó kế thừa căn lề từ `docDefaults`.
Nếu `docDefaults` đặt `w:jc="both"` theo quy định canh đều của báo cáo, chữ trong ô bảng hẹp
bị kéo giãn rất xấu.

Quan trọng: vá thẳng style `Compact` sẽ đổi luôn cả danh sách gạch đầu dòng, và nếu đổi cả
giãn dòng thì phần thân bài mất quy định 1.5. Cách đúng là tách hai việc:

- style `Compact`: chỉ đặt `w:jc="left"`, giữ nguyên giãn dòng 1.5.
- giãn dòng đơn cho ô bảng: hậu xử lý `word/document.xml`, duyệt từng `<w:tc>` và ghi
  `w:spacing` cùng `w:jc` vào `pPr` của mọi `<w:p>` bên trong.

Số trang là phép đo nhạy để phát hiện tác dụng phụ ngoài ý muốn: hạ giãn dòng của `Compact`
xuống đơn làm báo cáo rụng từ 60 xuống 49 trang, cho thấy style này phủ nhiều hơn dự kiến.

## 9. LibreOffice không phải trọng tài cho lỗi hiển thị đặc thù Word

Dựng bản render bằng LibreOffice headless là cách rẻ để tự nhìn kết quả, nhưng nó chỉ chứng
minh được điều nó tái hiện được. Hai giới hạn đã quan sát trực tiếp:

- Viền trang kiểu nghệ thuật `twistedLines1` của Word **không được LibreOffice vẽ**, dù Word
  vẽ bình thường.
- Với lỗi mất cạnh trái của bảng, LibreOffice vẽ đúng cạnh trái **trên cả bản đã sửa lẫn bản
  đối chứng giữ nguyên hình học cũ**. Nó không tái hiện được triệu chứng, nên không thể dùng
  để xác nhận bản vá.

Quy tắc rút ra: trước khi coi một bản render là bằng chứng, hãy dựng một **bản đối chứng
mang khuyết tật đã biết** và kiểm tra xem công cụ render có tái hiện khuyết tật đó không.
Công cụ nào không tái hiện được triệu chứng thì không xác nhận được cách chữa.

Công thức render đã kiểm chứng trên Windows:

```bat
"C:\Program Files\LibreOffice\program\soffice.com" --headless --norestore ^
  --convert-to pdf --outdir "<thu muc>" "<file.docx>"
```

Dùng biến thể `soffice.com` (bản console) và gọi qua `cmd`, rồi đọc PDF bằng
`pdftoppm -png -r 100 -f <trang> -l <trang>` và `pdftotext -layout` của poppler.

`pdftotext` mặc định xuất Latin-1, nên tiếng Việt biến thành ký tự rác và phép `grep` tìm
tiêu đề sẽ báo không có kết quả trong khi PDF hoàn toàn đúng. Luôn thêm `-enc UTF-8` khi
kiểm chứng tài liệu tiếng Việt.
`pdfinfo` xác nhận số trang và khổ giấy thực tế.

## 10. Canh đều cộng mã nội tuyến dài làm giãn chữ

Một đoạn văn canh đều (`w:jc="both"`) chứa một token không ngắt được và dài hơn phần còn
lại của dòng, ví dụ một đường dẫn tệp trong `<w:rStyle w:val="VerbatimChar"/>`, buộc token
đó xuống dòng sau và để lại vài chữ trên dòng trước. Word và LibreOffice kéo giãn mấy chữ
đó ra hết chiều rộng cột, nhìn như lỗi phông.

Cách chữa: hậu xử lý `word/document.xml`, tìm mọi `<w:p>` có run mang style mã nội tuyến mà
văn bản mã chứa token dài (ngưỡng 24 ký tự dùng tốt), rồi ghi `<w:jc w:val="left"/>` cho
riêng những đoạn đó. Phần thân bài vẫn giữ canh đều theo quy định trình bày.


## 11. Hai lỗi trình bày nữa mà pandoc để lại

**Tiêu đề kế thừa canh đều.** `docDefaults` đặt `w:jc="both"` cho cả tài liệu, và các style
`Heading*` không khai báo `w:jc` riêng nên kế thừa nó. Một tiêu đề chương dài tràn hai dòng
sẽ bị kéo giãn dòng đầu ra hết chiều rộng cột, trông như lỗi phông. Đặt `<w:jc w:val="left"/>`
trong `pPr` của mọi style `Heading*` ngay sau `<w:spacing/>`.

**Chú thích bảng phải neo vào dòng tiêu đề bảng, không vào dòng dữ liệu.** Khi chèn chú thích
bằng cách tìm một chuỗi đặc trưng rồi chèn vào trước dòng chứa nó, nếu chuỗi đó nằm ở một
dòng dữ liệu thì chú thích rơi vào **giữa** bảng Markdown. Bảng bị cắt làm hai: phần trên
thành bảng một dòng, phần dưới thành văn bản thường có dấu `|`. Luôn chọn khoá neo từ dòng
tiêu đề, và kiểm bằng cách đếm số bảng thực sự được sinh ra chứ không chỉ đếm số chú thích.


## 12. Trường TOC của Word không được LibreOffice cập nhật khi xuất PDF

pandoc chèn mục lục dưới dạng **trường** `TOC` kèm một chuỗi giữ chỗ. Word cập nhật trường đó
khi người dùng bấm Update Field, nhưng `soffice --headless --convert-to pdf` chỉ chép nguyên
chuỗi giữ chỗ vào PDF. Thêm `<w:updateFields w:val="true"/>` vào `word/settings.xml` (đặt
**trước** `<w:compat>` theo trật tự lược đồ) cũng **không** làm LibreOffice cập nhật.

Nên nếu bản nộp là PDF thì đừng dùng trường TOC. Cách đã kiểm chứng là dựng mục lục tĩnh
bằng hai lượt:

1. Dựng lần một, đọc PDF bằng `pdftotext -enc UTF-8 -f <trang> -l <trang>` từng trang, tìm
   trang đầu tiên chứa nguyên văn từng tiêu đề (dùng con trỏ tiến dần để một tiêu đề lặp lại
   không khớp nhầm trang trước đó).
2. Sinh bảng mục lục tĩnh có số trang, dựng lại, đo lại, và lặp cho tới khi dãy số trang không
   đổi. Trong dự án này dãy hội tụ sau ba lượt.

Hai chi tiết khiến phép đo sai nếu bỏ qua:

- **Phải bỏ qua chính các trang mục lục khi dò.** Trang mục lục chứa đủ mọi tiêu đề, nên phép
  tìm sẽ trả về trang mục lục cho mọi mục. Dấu hiệu nhận trang phần đầu sách rất đơn giản và
  đủ tin cậy: trang nào chứa từ 5 mục trở lên thì đó là trang mục lục hoặc danh mục hình.
- **Cắt ngắn chú thích hình có thể làm hỏng bảng.** Khi rút gọn chú thích cho danh mục hình,
  nếu nhát cắt rơi vào giữa một đoạn mã nội tuyến thì dấu nháy ngược còn lẻ sẽ nuốt luôn các
  dấu `|` phía sau, và nhiều hàng bảng dính thành một ô. Sau khi cắt, kiểm số dấu nháy ngược
  là chẵn, nếu lẻ thì bỏ nốt phần mã dở dang.

## 13. Trật tự các bước hậu xử lý quyết định kết quả

Các phép hậu xử lý `document.xml` ghi đè lẫn nhau, nên thứ tự gọi là một phần của thiết kế.
Lỗi đã gặp: hàm căn giữa chú thích hình nhận diện đoạn văn bắt đầu bằng `Hình <số>.`, và nó
căn giữa luôn các ô trong **danh mục hình** vì nội dung ô cũng bắt đầu như vậy.

Cách sửa đúng không phải là làm phức tạp điều kiện nhận diện, mà là đổi thứ tự: chạy phép căn
giữa chú thích **trước**, rồi mới chạy phép chuẩn hoá ô bảng. Phép sau đặt lại `w:jc="left"`
cho mọi đoạn nằm trong `<w:tc>`, nên tự động sửa các ô bị căn giữa nhầm, trong khi chú thích
ngoài bảng vẫn giữ căn giữa.

Xem thêm [[git-bash-and-windows-process-control]] về ký tự điều khiển vô hình lọt vào
regex qua heredoc, một lỗi từng làm phép thay thế `tblLook` im lặng không khớp, và
[[windows-gui-automation]] về cách chụp ảnh giao diện sao cho chữ còn đọc được sau khi thu
vào cột chữ A4.
