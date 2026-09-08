import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileKey2, LogOut, Menu, ScanSearch, ShieldCheck, X } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { canCreateIssuance, canCreateVerification, useLogout, useSession } from "../features/auth/session";
import { getDemoCapabilities } from "../features/demo/capabilities";
import { MotionRoute } from "./MotionRoute";

export function AppShell() {
  const session = useSession();
  const logout = useLogout();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const user = session.data?.user;
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

  return (
    <div className={`app-shell ${mobileOpen ? "mobile-drawer-open" : ""}`.trim()}>
      <header className="app-header" aria-label="Thanh ứng dụng SplitBind">
        <div className="header-brand-wrap">
          <NavLink className="app-brand" to={canCreateIssuance(user?.role) ? "/issue" : "/verify"} aria-label="SplitBind — trang làm việc">
            <span className="brand-symbol" aria-hidden="true"><ShieldCheck size={20} strokeWidth={2.2} /></span>
            <span className="brand-title">SplitBind</span>
            <span className="brand-tag">v0.1</span>
          </NavLink>
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
            <p className="foot-sub">Mã hóa DWT-DCT-QIM & Ed25519</p>
          </div>
        </footer>
      </div>
    </div>
  );
}
