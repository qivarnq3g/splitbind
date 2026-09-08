import { useEffect, useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import { useQuery } from "@tanstack/react-query";
import gsap from "gsap";
import { FileKey2, LogOut, Menu, ScanSearch, ShieldCheck, X } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { canCreateIssuance, canCreateVerification, useLogout, useSession } from "../features/auth/session";
import { getDemoCapabilities } from "../features/demo/capabilities";
import { MotionRoute } from "./MotionRoute";

gsap.registerPlugin(useGSAP);

interface WorkflowStageInfo {
  stage: 1 | 2 | 3;
  flowLabel: string;
  stepLabel: string;
  terminalLabel: string;
}

function getWorkflowStageInfo(pathname: string): WorkflowStageInfo | null {
  if (pathname.startsWith("/issue")) {
    return {
      stage: 1,
      flowLabel: "Cấp phát",
      stepLabel: "Tiếp nhận tệp",
      terminalLabel: "Niêm phong",
    };
  }
  if (pathname.startsWith("/verify")) {
    return {
      stage: 1,
      flowLabel: "Xác minh",
      stepLabel: "Kiểm định tệp",
      terminalLabel: "Kết quả",
    };
  }
  if (pathname.startsWith("/jobs/")) {
    return {
      stage: 2,
      flowLabel: "Quy trình xử lý",
      stepLabel: "Xử lý mật mã",
      terminalLabel: "Kết quả",
    };
  }
  if (pathname.startsWith("/issuances/")) {
    return {
      stage: 3,
      flowLabel: "Cấp phát",
      stepLabel: "Ấn triện niêm phong",
      terminalLabel: "Niêm phong",
    };
  }
  if (pathname.startsWith("/verifications/")) {
    return {
      stage: 3,
      flowLabel: "Xác minh",
      stepLabel: "Bằng chứng toàn vẹn",
      terminalLabel: "Kiểm định",
    };
  }
  return null;
}

export function AppShell() {
  const session = useSession();
  const logout = useLogout();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const pipelineIndicatorRef = useRef<HTMLDivElement>(null);
  const user = session.data?.user;
  const stageInfo = getWorkflowStageInfo(location.pathname);
  const demoCapabilities = useQuery({
    queryKey: ["demo-capabilities"],
    queryFn: ({ signal }) => getDemoCapabilities(signal),
    enabled: Boolean(user),
    staleTime: 30_000,
    retry: false,
  });
  const isIntegrityRelease = demoCapabilities.data?.algorithm_label === "integrity_release_v1";

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useGSAP(
    () => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function" || !pipelineIndicatorRef.current || !stageInfo) {
        return;
      }

      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (prefersReduced) {
        gsap.set(".stage-node-dot, .stage-segment-beam", { clearProps: "all" });
        return;
      }

      const tl = gsap.timeline({ defaults: { ease: "power2.out" } });

      tl.fromTo(
        `.stage-node[data-step="${stageInfo.stage}"] .stage-node-dot`,
        { scale: 0.65, opacity: 0.7 },
        { scale: 1, opacity: 1, duration: 0.32, ease: "back.out(2)", clearProps: "transform,opacity" }
      );

      if (stageInfo.stage >= 2) {
        tl.fromTo(
          ".stage-segment.is-filled .stage-segment-beam",
          { scaleX: 0, transformOrigin: "left center" },
          { scaleX: 1, duration: 0.35, ease: "power2.out", clearProps: "transform" },
          "-=0.2"
        );
      }
    },
    { scope: pipelineIndicatorRef, dependencies: [stageInfo?.stage], revertOnUpdate: true }
  );

  return (
    <div className={`app-shell ${mobileOpen ? "mobile-drawer-open" : ""}`.trim()}>
      <header className="app-header" aria-label="Thanh ứng dụng SplitBind">
        <div className="header-brand-wrap">
          <NavLink className="app-brand" to={canCreateIssuance(user?.role) ? "/issue" : "/verify"} aria-label="SplitBind — trang làm việc">
            <span className="brand-symbol" aria-hidden="true"><ShieldCheck size={20} strokeWidth={2.2} /></span>
            <span className="brand-title">SplitBind</span>
            <span className="brand-tag">v0.1</span>
          </NavLink>
          {user && stageInfo ? (
            <div className="header-breadcrumb" aria-label="Đường dẫn quy trình mật mã">
              <span className="breadcrumb-separator" aria-hidden="true">/</span>
              <span className="breadcrumb-flow">{stageInfo.flowLabel}</span>
              <span className="breadcrumb-separator" aria-hidden="true">/</span>
              <span className="breadcrumb-current">{stageInfo.stepLabel}</span>
            </div>
          ) : null}
        </div>

        {user ? (
          <nav className={`primary-nav ${mobileOpen ? "is-open" : ""}`.trim()} aria-label="Điều hướng chính">
            {canCreateIssuance(user.role) ? (
              <NavLink to="/issue" className="nav-item">
                <FileKey2 size={17} aria-hidden="true" />
                <span>Cấp phát</span>
              </NavLink>
            ) : null}
            {canCreateVerification(user.role) ? (
              <NavLink to="/verify" className="nav-item">
                <ScanSearch size={17} aria-hidden="true" />
                <span>Xác minh</span>
              </NavLink>
            ) : null}
            {!canCreateIssuance(user.role) && !canCreateVerification(user.role) ? (
              <span className="nav-readonly">Chỉ đọc</span>
            ) : null}
          </nav>
        ) : null}

        {user && stageInfo ? (
          <div
            ref={pipelineIndicatorRef}
            className="header-pipeline-indicator"
            role="group"
            aria-label="Tiến trình quy trình mật mã"
            data-active-stage={stageInfo.stage}
          >
            <div className="stage-track">
              <div className={`stage-node ${stageInfo.stage >= 1 ? "is-active" : ""}`} data-step="1">
                <span className="stage-node-dot" />
                <span className="stage-node-label">Tiếp nhận</span>
              </div>
              <span className={`stage-segment ${stageInfo.stage >= 2 ? "is-filled" : ""}`}>
                <span className="stage-segment-beam" />
              </span>
              <div className={`stage-node ${stageInfo.stage >= 2 ? "is-active" : ""}`} data-step="2">
                <span className="stage-node-dot" />
                <span className="stage-node-label">Xử lý</span>
              </div>
              <span className={`stage-segment ${stageInfo.stage >= 3 ? "is-filled" : ""}`}>
                <span className="stage-segment-beam" />
              </span>
              <div className={`stage-node ${stageInfo.stage >= 3 ? "is-active" : ""}`} data-step="3">
                <span className="stage-node-dot" />
                <span className="stage-node-label">{stageInfo.terminalLabel}</span>
              </div>
            </div>
          </div>
        ) : null}

        <div className="header-right-slot">
          {user ? (
            <div className="account-area">
              <div className="account-badge">
                <span className="account-dot" aria-hidden="true" />
                <span className="account-name">{user.username}</span>
              </div>
              <button
                className="account-action"
                type="button"
                onClick={() => logout.mutate()}
                disabled={logout.isPending}
                aria-label="Đăng xuất khỏi SplitBind"
              >
                <LogOut size={16} aria-hidden="true" />
                <span>{logout.isPending ? "Đang thoát" : "Đăng xuất"}</span>
              </button>
            </div>
          ) : (
            <NavLink className="rail-account" to="/login">Đăng nhập</NavLink>
          )}

          {user ? (
            <button
              className="mobile-nav-toggle"
              type="button"
              aria-label={mobileOpen ? "Đóng menu điều hướng" : "Mở menu điều hướng"}
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen(!mobileOpen)}
            >
              {mobileOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
            </button>
          ) : null}
        </div>
      </header>

      {mobileOpen ? (
        <div
          className="mobile-drawer-backdrop"
          aria-hidden="true"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}

      <div className="app-content">
        {isIntegrityRelease ? (
          <aside className="demo-banner" aria-label="Khả năng xác minh">
            <p><strong>Xác minh chính xác file đã cấp phát.</strong> Nhận diện fingerprint sau biến đổi chưa khả dụng.</p>
          </aside>
        ) : demoCapabilities.data?.enabled ? (
          <aside className="demo-banner" aria-label="Giới hạn chế độ demo">
            <p><strong>Bản demo.</strong> Kết quả chỉ mang tính kỹ thuật, không xác định người làm rò rỉ hoặc chỉnh sửa.</p>
          </aside>
        ) : null}
        <MotionRoute><Outlet /></MotionRoute>
        <footer className="foot-line">
          <div className="foot-line-content">
            <p>SplitBind · Nhóm 9 · ATTT</p>
            <span className="foot-divider" aria-hidden="true">/</span>
            <p className="foot-sub">Thủy vân số chống giả mạo & Ký số bảo vệ toàn vẹn</p>
          </div>
        </footer>
      </div>
    </div>
  );
}
