import { Link } from "react-router-dom";

import { HeroDocumentStack } from "./HeroDocumentStack";

type Props = {
  signedIn: boolean;
  workbench: string;
};

export function LandingHero({ signedIn, workbench }: Props) {
  return (
    <section
      className="landing-section landing-hero"
      data-landing-section="01"
      aria-labelledby="landing-title"
    >
      <div className="landing-hero-grid">
        <div className="landing-section-body">
          <h1 id="landing-title">
            <span data-hero-line>Tài liệu có nguồn.</span>{" "}
            <span data-hero-line>Niềm tin có cơ sở.</span>
          </h1>
          <p className="landing-lede">
            Mỗi người nhận được một bản riêng. Khi một tệp quay lại, hệ thống
            đối chiếu nó với hồ sơ đã cấp phát và trả lời kèm theo bằng chứng kỹ
            thuật.
          </p>
          <div className="landing-actions">
            <Link
              className="button button-primary"
              to={signedIn ? workbench : "/login"}
            >
              {signedIn ? "Vào không gian làm việc" : "Đăng nhập"}
            </Link>
            <a className="button button-secondary" href="#evidence-boundary">
              Xem cách hoạt động
            </a>
          </div>
        </div>
        <div data-parallax="7">
          <HeroDocumentStack />
        </div>
      </div>
    </section>
  );
}
