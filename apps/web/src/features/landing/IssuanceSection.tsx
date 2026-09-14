export function IssuanceSection() {
  return (
    <section
      className="landing-section"
      data-landing-section="03"
      aria-labelledby="issuance"
    >
      <div className="landing-section-body">
        <p className="landing-eyebrow">03</p>
        <h2 id="issuance">Mỗi người một bản riêng, có chữ ký</h2>
        <p>
          Khi phát hành một tài liệu, hệ thống không gửi cùng một tệp cho mọi
          người. Mỗi người nhận một bản được dựng riêng cho họ, và mỗi bản để lại
          một hồ sơ đủ để đối chiếu về sau.
        </p>
        <ol className="landing-beats">
          <li>
            Nhúng thủy vân vào ảnh của từng trang. Mắt thường không nhìn
            thấy, nhưng nó mang mã của đúng bản cấp phát ấy, nên không có hai
            người nhận nào cầm hai tệp giống hệt nhau.
          </li>
          <li>
            Tính mã băm SHA-256 của tệp vừa dựng. Mã băm là một chuỗi ký tự đại
            diện cho toàn bộ nội dung: đổi một dấu phẩy thôi là chuỗi ấy đổi
            hoàn toàn.
          </li>
          <li>
            Ký số Ed25519 lên manifest, tức hồ sơ mô tả tệp này thuộc về lần
            cấp phát nào. Chữ ký cho phép chứng minh về sau rằng hồ sơ đó chưa bị
            ai sửa.
          </li>
        </ol>
        <p>
          Ba bước diễn ra ngay lúc bản cấp phát được tạo. Thủy vân dùng để nhận
          ra tệp kể cả khi nó đã bị biến đổi. Mã băm và chữ ký dùng để trả lời
          một câu khác hẳn: tệp có còn đúng nguyên như lúc phát hành hay không.
        </p>
      </div>
    </section>
  );
}
