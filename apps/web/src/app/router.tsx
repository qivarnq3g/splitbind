import { Navigate, Outlet, RouteObject, createBrowserRouter, useLocation } from "react-router-dom";

import { AppShell } from "../components/AppShell";
import { canCreateIssuance, useSession } from "../features/auth/session";
import { HistoryPage } from "../pages/HistoryPage";
import { IssueDocumentPage } from "../pages/IssueDocumentPage";
import { IssuanceDetailPage } from "../pages/IssuanceDetailPage";
import { JobDetailPage } from "../pages/JobDetailPage";
import { LandingPage } from "../pages/LandingPage";
import { LoginPage } from "../pages/LoginPage";
import { VerificationDetailPage } from "../pages/VerificationDetailPage";
import { VerifyDocumentPage } from "../pages/VerifyDocumentPage";

function HomeRoute() {
  const session = useSession();
  if (session.data?.authenticated) {
    return <Navigate to={canCreateIssuance(session.data?.user?.role) ? "/issue" : "/verify"} replace />;
  }
  return <LandingPage />;
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

export const appRoutes: RouteObject[] = [
  { path: "/", element: <HomeRoute /> },
  { path: "/gioi-thieu", element: <LandingPage /> },
  {
    element: <AppShell />,
    children: [
      { path: "/login", element: <LoginPage /> },
      {
        element: <SessionBoundary />,
        children: [
          { path: "/issue", element: <IssueDocumentPage /> },
          { path: "/verify", element: <VerifyDocumentPage /> },
          { path: "/history", element: <HistoryPage /> },
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
