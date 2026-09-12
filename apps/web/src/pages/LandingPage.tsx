import { useRef } from "react";
import { Link } from "react-router-dom";

import { ArchitectureSection } from "../features/landing/ArchitectureSection";
import { BoundarySection } from "../features/landing/BoundarySection";
import { IssuanceSection } from "../features/landing/IssuanceSection";
import { LandingClosing } from "../features/landing/LandingClosing";
import { LandingHero } from "../features/landing/LandingHero";
import { ProblemSection } from "../features/landing/ProblemSection";
import { VerificationSection } from "../features/landing/VerificationSection";
import { useScrollReveal } from "../features/landing/useScrollReveal";
import "../styles/landing.css";

export function LandingPage() {
  const root = useRef<HTMLDivElement>(null);
  useScrollReveal(root);
  return (
    <div className="landing" ref={root}>
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
        <LandingHero />
        <ProblemSection />
        <IssuanceSection />
        <VerificationSection />
        <BoundarySection />
        <ArchitectureSection />
        <LandingClosing />
      </main>
      <footer className="landing-footer">
        <span>SplitBind · Nhóm 9 · An toàn thông tin</span>
        <span>Cấp phát có chữ ký. Xác minh có bằng chứng.</span>
      </footer>
    </div>
  );
}
