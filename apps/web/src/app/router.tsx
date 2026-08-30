import { Navigate, NavLink, Outlet, RouteObject, createBrowserRouter, useLocation } from "react-router-dom";

import { canCreateIssuance, useLogout, useSession } from "../features/auth/session";
import { IssueDocumentPage } from "../pages/IssueDocumentPage";
import { IssuanceDetailPage } from "../pages/IssuanceDetailPage";
import { JobDetailPage } from "../pages/JobDetailPage";
import { LoginPage } from "../pages/LoginPage";

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

  return (
    <div className="app-shell">
      <nav className="side-rail" aria-label="Điều hướng chính">
        <NavLink className="side-brand" to="/issue" aria-label="SplitBind — trang cấp phát">SplitBind</NavLink>
        <div className="rail-links">
          {canCreateIssuance(user?.role) ? <NavLink to="/issue">Cấp phát</NavLink> : <span>Chỉ đọc</span>}
        </div>
        {user ? (
          <button className="rail-account" type="button" onClick={() => logout.mutate()} disabled={logout.isPending}>
            {logout.isPending ? "Đang thoát" : "Đăng xuất"}
          </button>
        ) : <NavLink className="rail-account" to="/login">Đăng nhập</NavLink>}
      </nav>
      <div className="app-content">
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
          { index: true, element: <Navigate to="/issue" replace /> },
          { path: "/issue", element: <IssueDocumentPage /> },
          { path: "/jobs/:id", element: <JobDetailPage /> },
          { path: "/issuances/:id", element: <IssuanceDetailPage /> },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];

export const router = createBrowserRouter(appRoutes);
