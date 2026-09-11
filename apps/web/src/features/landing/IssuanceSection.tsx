export function IssuanceSection() {
  return (
    <section
      className="landing-section"
      data-landing-section="03"
      aria-labelledby="cap-phat-co-chu-ky"
    >
      <div className="landing-section-body">
        <p className="landing-eyebrow">03</p>
        <h2 id="cap-phat-co-chu-ky">Mỗi người một bản riêng, có chữ ký</h2>
        <p>
          Khi phát hành một tài liệu, hệ thống không gửi cùng một tệp cho tất cả
          mọi người. Mỗi người nhận có một bản được dựng riêng, và mỗi bản để lại
          một hồ sơ đủ để đối chiếu về sau.
        </p>
        <ol className="landing-beats">
          <li>
            In lên mỗi trang một mã cấp phát nhìn thấy được, nên không có hai
            người nhận nào cầm cùng một tệp.
          </li>
          <li>
            Băm toàn bộ tệp vừa dựng bằng SHA-256, rồi ghi giá trị băm ấy vào
            manifest (bản kê khai mô tả tệp và người nhận).
          </li>
          <li>
            Đặt chữ ký số Ed25519 lên manifest, để về sau còn chứng minh được
            rằng hồ sơ cấp phát chưa bị thay đổi.
          </li>
        </ol>
        <p>
          Ba bước này chạy ngay lúc bản cấp phát được tạo, và kết quả của chúng
          chính là thứ mà bước xác minh đem ra đối chiếu. Bản đang chạy dùng mã
          cấp phát nhìn thấy được; thủy vân ẩn vẫn còn là hướng nghiên cứu, chưa
          đưa vào bản phát hành.
        </p>
      </div>
    </section>
  );
}
