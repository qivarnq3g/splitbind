import { Link } from "react-router-dom";

import { WaveletCompanion } from "./WaveletCompanion";

type Props = {
  signedIn: boolean;
  workbench: string;
};

export function LandingClosing({ signedIn, workbench }: Props) {
  return (
    <section
      className="landing-section landing-close"
      data-landing-section="07"
      aria-labelledby="get-started"
    >
      <div className="landing-close-grid">
        <div className="landing-section-body">
          <p className="landing-eyebrow">07</p>
          <h2 id="get-started">
            {signedIn ? "Quay lại không gian làm việc" : "Đăng nhập để bắt đầu"}
          </h2>
          <p>
            SplitBind là bài tập lớn môn an toàn thông tin của nhóm 9. Bản đang
            chạy phục vụ mục đích trình bày và kiểm thử, không phải một dịch vụ
            thương mại.
          </p>
          <p>
            {signedIn
              ? "Bạn đang đăng nhập. Khu vực cấp phát và xác minh luôn mở sẵn."
              : "Khu vực cấp phát và xác minh cần tài khoản. Phần giới thiệu này thì không."}
          </p>
          <div className="landing-actions">
            <Link
              className="button button-primary"
              to={signedIn ? workbench : "/login"}
            >
              {signedIn ? "Vào không gian làm việc" : "Đăng nhập"}
            </Link>
          </div>
        </div>
        <div data-parallax="-6">
          <WaveletCompanion />
        </div>
      </div>
    </section>
  );
}
