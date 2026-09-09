import { useQuery } from "@tanstack/react-query";
import { FileKey2, LogOut, ScanSearch } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import {
  canCreateIssuance,
  canCreateVerification,
  useLogout,
  useSession,
} from "../features/auth/session";
import { getDemoCapabilities } from "../features/demo/capabilities";
import { MotionRoute } from "./MotionRoute";

export function AppShell() {
  const session = useSession();
  const logout = useLogout();
  const user = session.data?.user;
  const capabilities = useQuery({
    queryKey: ["demo-capabilities"],
    queryFn: ({ signal }) => getDemoCapabilities(signal),
    enabled: Boolean(user),
    staleTime: 30_000,
    retry: false,
  });
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Đến nội dung chính
      </a>
      <header className="app-header" aria-label="Thanh ứng dụng SplitBind">
        <NavLink
          className="app-brand"
          to="/"
          aria-label="SplitBind — trang làm việc"
        >
          <span className="brand-symbol" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>SplitBind</span>
        </NavLink>
        <span className="brand-description">Toàn vẹn tài liệu</span>
        {user ? (
          <div className="account-area">
            <span className="account-name">{user.username}</span>
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
          <span className="account-name">Không gian bảo mật</span>
        )}
      </header>
      {logout.error ? (
        <p className="form-error" role="alert">
          {logout.error.message}
        </p>
      ) : null}
      {user ? (
        <nav className="primary-nav" aria-label="Điều hướng chính">
          {canCreateIssuance(user.role) ? (
            <NavLink to="/issue" className="nav-item">
              <FileKey2 size={18} aria-hidden="true" />
              Cấp phát
            </NavLink>
          ) : null}
          {canCreateVerification(user.role) ? (
            <NavLink to="/verify" className="nav-item">
              <ScanSearch size={18} aria-hidden="true" />
              Xác minh
            </NavLink>
          ) : null}
          {!canCreateIssuance(user.role) &&
          !canCreateVerification(user.role) ? (
            <span className="nav-readonly">
              Quyền chỉ đọc · Mở hồ sơ bằng liên kết được cấp
            </span>
          ) : null}
        </nav>
      ) : null}
      <div className="app-content" id="main-content" tabIndex={-1}>
        <MotionRoute>
          <Outlet />
        </MotionRoute>
        {user &&
        capabilities.data?.algorithm_label === "integrity_release_v1" ? (
          <aside className="capability-note" aria-label="Khả năng xác minh">
            <strong>Xác minh chính xác file đã cấp phát.</strong> Nhận diện
            fingerprint sau biến đổi chưa khả dụng.
          </aside>
        ) : capabilities.data?.enabled ? (
          <aside className="capability-note" aria-label="Giới hạn chế độ demo">
            <p>
              <strong>Bản demo.</strong> Kết quả chỉ mang tính kỹ thuật, không
              xác định người làm rò rỉ hoặc chỉnh sửa.
            </p>
          </aside>
        ) : null}
        <footer className="foot-line">
          <span>SplitBind · Nhóm 9 · ATTT</span>
          <span>Cấp phát có chữ ký. Xác minh có bằng chứng.</span>
        </footer>
      </div>
    </div>
  );
}
