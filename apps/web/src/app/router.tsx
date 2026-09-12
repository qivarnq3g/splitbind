import { useEffect } from "react";
import { Navigate, Outlet, RouteObject, createBrowserRouter, useLocation } from "react-router-dom";

import { AppShell } from "../components/AppShell";
import { titleForPath } from "./documentTitle";
import { canCreateIssuance, useSession } from "../features/auth/session";
import { HistoryPage } from "../pages/HistoryPage";
import { IssueDocumentPage } from "../pages/IssueDocumentPage";
import { IssuanceDetailPage } from "../pages/IssuanceDetailPage";
import { JobDetailPage } from "../pages/JobDetailPage";
import { LandingPage } from "../pages/LandingPage";
import { LoginPage } from "../pages/LoginPage";
import { VerificationDetailPage } from "../pages/VerificationDetailPage";
import { VerifyDocumentPage } from "../pages/VerifyDocumentPage";

function DocumentTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = titleForPath(pathname);
  }, [pathname]);
  return null;
}

function TitledOutlet() {
  return (
    <>
      <DocumentTitle />
      <Outlet />
    </>
  );
}

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
  if (session.isPending)
    return (
      <main
        className="workspace-page session-skeleton"
        role="status"
        aria-label="Đang kiểm tra phiên đăng nhập"
        aria-busy="true"
      >
        <span className="session-skeleton-line session-skeleton-title" />
        <span className="session-skeleton-line" />
        <span className="session-skeleton-line session-skeleton-short" />
      </main>
    );
  if (session.error || !session.data?.authenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

const titledRoutes: RouteObject[] = [
  { path: "/", element: <HomeRoute /> },
  { path: "/about", element: <LandingPage /> },
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

export const appRoutes: RouteObject[] = [
  { element: <TitledOutlet />, children: titledRoutes },
];

export const router = createBrowserRouter(appRoutes);
