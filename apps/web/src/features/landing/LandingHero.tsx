import { Link } from "react-router-dom";

export function LandingHero() {
  return (
    <section
      className="landing-section landing-hero"
      data-landing-section="01"
      aria-labelledby="landing-title"
    >
      <div className="landing-section-body">
        <h1 id="landing-title">
          <span data-hero-line>Tài liệu có nguồn.</span>{" "}
          <span data-hero-line>Niềm tin có cơ sở.</span>
        </h1>
        <p className="landing-lede">
          Mỗi người nhận được một bản riêng. Khi một tệp quay lại, hệ thống đối
          chiếu nó với hồ sơ đã cấp phát và trả lời kèm bằng chứng kỹ thuật.
        </p>
        <div className="landing-actions">
          <Link className="button button-primary" to="/login">
            Đăng nhập
          </Link>
          <a className="button button-secondary" href="#bien-gioi-bang-chung">
            Xem cách hoạt động
          </a>
        </div>
      </div>
    </section>
  );
}
