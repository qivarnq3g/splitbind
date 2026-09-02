import { useQuery } from "@tanstack/react-query";
import { Navigate, NavLink, Outlet, RouteObject, createBrowserRouter, useLocation } from "react-router-dom";

import { canCreateIssuance, canCreateVerification, useLogout, useSession } from "../features/auth/session";
import { getDemoCapabilities } from "../features/demo/capabilities";
import { IssueDocumentPage } from "../pages/IssueDocumentPage";
import { IssuanceDetailPage } from "../pages/IssuanceDetailPage";
import { JobDetailPage } from "../pages/JobDetailPage";
import { LoginPage } from "../pages/LoginPage";
import { VerificationDetailPage } from "../pages/VerificationDetailPage";
import { VerifyDocumentPage } from "../pages/VerifyDocumentPage";

function RoleHome() {
  const session = useSession();
  return <Navigate to={canCreateIssuance(session.data?.user?.role) ? "/issue" : "/verify"} replace />;
}

function SessionBoundary() {
  const session = useSession();
  const location = useLocation();
  if (session.isPending) return <main className="session-loading" aria-busy="true"><p>Đang kiểm tra phiên đăng nhập</p></main>;
  if (session.error || !session.data?.authenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

function AppShell() {
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
      <nav className="side-rail" aria-label="Điều hướng chính">
        <NavLink className="side-brand" to={canCreateIssuance(user?.role) ? "/issue" : "/verify"} aria-label="SplitBind — trang làm việc">SplitBind</NavLink>
        <div className="rail-links">
          {canCreateIssuance(user?.role) ? <NavLink to="/issue">Cấp phát</NavLink> : null}
          {canCreateVerification(user?.role) ? <NavLink to="/verify">Xác minh</NavLink> : null}
          {!canCreateIssuance(user?.role) && !canCreateVerification(user?.role) ? <span>Chỉ đọc</span> : null}
        </div>
        {user ? (
          <button className="rail-account" type="button" onClick={() => logout.mutate()} disabled={logout.isPending}>
            {logout.isPending ? "Đang thoát" : "Đăng xuất"}
          </button>
        ) : <NavLink className="rail-account" to="/login">Đăng nhập</NavLink>}
      </nav>
      <div className="app-content">
        {demoCapabilities.data?.enabled ? (
          <aside className="demo-banner" aria-label="Giới hạn chế độ demo">
            <strong>Chế độ demo cục bộ — vân tay thử nghiệm, chưa phát hành.</strong>
            <p>Kết quả kỹ thuật không chứng minh ai đã làm rò rỉ, chỉnh sửa hoặc phân phối tài liệu.</p>
          </aside>
        ) : null}
        <Outlet />
        <footer className="foot-line">
          <p>SplitBind · Nhóm 9 · Bài tập lớn An toàn thông tin</p>
        </footer>
      </div>
    </div>
  );
}

export const appRoutes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { path: "/login", element: <LoginPage /> },
      {
        element: <SessionBoundary />,
        children: [
          { index: true, element: <RoleHome /> },
          { path: "/issue", element: <IssueDocumentPage /> },
          { path: "/verify", element: <VerifyDocumentPage /> },
          { path: "/jobs/:id", element: <JobDetailPage /> },
          { path: "/issuances/:id", element: <IssuanceDetailPage /> },
          { path: "/verifications/:id", element: <VerificationDetailPage /> },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];

export const router = createBrowserRouter(appRoutes);
