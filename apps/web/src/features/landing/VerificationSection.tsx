export function VerificationSection() {
  return (
    <section
      className="landing-section"
      data-landing-section="04"
      aria-labelledby="doi-chieu-tep-nghi-van"
    >
      <div className="landing-section-body">
        <p className="landing-eyebrow">04</p>
        <h2 id="doi-chieu-tep-nghi-van">Tệp nghi vấn, đặt cạnh hồ sơ gốc</h2>
        <p>
          Bạn tải lên tệp nghi vấn. Hệ thống băm tệp đó bằng SHA-256, so khớp giá
          trị băm với hồ sơ của các bản đã cấp phát, đồng thời kiểm tra chữ ký số
          Ed25519 trên manifest tương ứng.
        </p>
        <p>
          Kết quả tách bạch hai câu hỏi về tính toàn vẹn: tệp có khớp chính xác
          đến từng byte với một bản đã cấp phát hay không, và hồ sơ của bản đó có
          bị sửa hay không. Những gì hệ thống chưa kết luận được thì nêu riêng,
          không gộp vào một phán quyết chung.
        </p>
      </div>
    </section>
  );
}
