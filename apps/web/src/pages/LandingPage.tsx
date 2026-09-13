import { useRef } from "react";
import { Link } from "react-router-dom";

import { canCreateIssuance, useSession } from "../features/auth/session";

import { AtmosphereLayer } from "../features/landing/AtmosphereLayer";
import { ArchitectureSection } from "../features/landing/ArchitectureSection";
import { BoundarySection } from "../features/landing/BoundarySection";
import { IssuanceSection } from "../features/landing/IssuanceSection";
import { LandingClosing } from "../features/landing/LandingClosing";
import { LandingHero } from "../features/landing/LandingHero";
import { ProblemSection } from "../features/landing/ProblemSection";
import { VerificationSection } from "../features/landing/VerificationSection";
import { useScrollReveal } from "../features/landing/useScrollReveal";
import { useSmoothScroll } from "../features/landing/useSmoothScroll";
import { useTilt } from "../features/shared/useTilt";
import "../styles/landing.css";

export function LandingPage() {
  const root = useRef<HTMLDivElement>(null);
  const session = useSession();
  const signedIn = session.data?.authenticated === true;
  const workbench = canCreateIssuance(session.data?.user?.role)
    ? "/issue"
    : "/verify";
  useSmoothScroll();
  useScrollReveal(root);
  useTilt(root, ".landing-stack > div");
  return (
    <div className="landing" ref={root}>
      <AtmosphereLayer />
      <a className="skip-link" href="#main-content">
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
        <Link
          className="button button-secondary"
          to={signedIn ? workbench : "/login"}
        >
          {signedIn ? "Vào không gian làm việc" : "Đăng nhập"}
        </Link>
      </header>
      <main className="landing-main" id="main-content" tabIndex={-1}>
        <LandingHero signedIn={signedIn} workbench={workbench} />
        <ProblemSection />
        <IssuanceSection />
        <VerificationSection />
        <BoundarySection />
        <ArchitectureSection />
        <LandingClosing signedIn={signedIn} workbench={workbench} />
      </main>
      <footer className="landing-footer">
        <span>SplitBind · Nhóm 9 · An toàn thông tin</span>
        <span>Cấp phát có chữ ký. Xác minh có bằng chứng.</span>
      </footer>
    </div>
  );
}
