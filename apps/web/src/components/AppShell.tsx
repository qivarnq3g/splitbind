import { useQuery } from "@tanstack/react-query";
import { FileKey2, LogOut, ScanSearch, ShieldCheck } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { canCreateIssuance, canCreateVerification, useLogout, useSession } from "../features/auth/session";
import { getDemoCapabilities } from "../features/demo/capabilities";
import { MotionRoute } from "./MotionRoute";

export function AppShell() {
  const session = useSession();
  const logout = useLogout();
  const user = session.data?.user;
  const demoCapabilities = useQuery({
    queryKey: ["demo-capabilities"],
    queryFn: ({ signal }) => getDemoCapabilities(signal),
    enabled: Boolean(user),
    staleTime: 30_000,
    retry: false,
  });

  return (
    <div className="app-shell">
      <header className="app-header" aria-label="Thanh ứng dụng SplitBind">
        <NavLink className="app-brand" to={canCreateIssuance(user?.role) ? "/issue" : "/verify"} aria-label="SplitBind — trang làm việc">
          <span className="brand-symbol" aria-hidden="true"><ShieldCheck size={19} strokeWidth={2} /></span>
          <span>SplitBind</span>
        </NavLink>
        {user ? (
          <nav className="primary-nav" aria-label="Điều hướng chính">
            {canCreateIssuance(user.role) ? <NavLink to="/issue"><FileKey2 size={17} aria-hidden="true" />Cấp phát</NavLink> : null}
            {canCreateVerification(user.role) ? <NavLink to="/verify"><ScanSearch size={17} aria-hidden="true" />Xác minh</NavLink> : null}
            {!canCreateIssuance(user.role) && !canCreateVerification(user.role) ? <span>Chỉ đọc</span> : null}
          </nav>
        ) : null}
        {user ? (
          <div className="account-area">
            <span className="account-name">{user.username}</span>
            <button className="account-action" type="button" onClick={() => logout.mutate()} disabled={logout.isPending}>
              <LogOut size={17} aria-hidden="true" />
              <span>{logout.isPending ? "Đang thoát" : "Đăng xuất"}</span>
            </button>
          </div>
        ) : <NavLink className="rail-account" to="/login">Đăng nhập</NavLink>}
      </header>
      <div className="app-content">
        {demoCapabilities.data?.enabled ? (
          <aside className="demo-banner" aria-label="Giới hạn chế độ demo">
            <p><strong>Bản demo.</strong> Kết quả chỉ mang tính kỹ thuật, không xác định người làm rò rỉ hoặc chỉnh sửa.</p>
          </aside>
        ) : null}
        <MotionRoute><Outlet /></MotionRoute>
        <footer className="foot-line"><p>SplitBind · Nhóm 9 · ATTT</p></footer>
      </div>
    </div>
  );
}
