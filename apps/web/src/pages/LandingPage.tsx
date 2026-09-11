import { Link } from "react-router-dom";

import "../styles/landing.css";

export function LandingPage() {
  return (
    <div className="landing">
      <a className="skip-link" href="#noi-dung-chinh">
        Đến nội dung chính
      </a>
      <header className="landing-header" aria-label="Giới thiệu SplitBind">
        <span className="landing-brand">
          <span className="brand-symbol" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>SplitBind</span>
        </span>
        <Link className="button button-secondary" to="/login">
          Đăng nhập
        </Link>
      </header>
      <main className="landing-main" id="noi-dung-chinh" tabIndex={-1}>
        <h1>Tài liệu có nguồn. Niềm tin có cơ sở.</h1>
      </main>
      <footer className="landing-footer">
        <span>SplitBind · Nhóm 9 · An toàn thông tin</span>
        <span>Cấp phát có chữ ký. Xác minh có bằng chứng.</span>
      </footer>
    </div>
  );
}
