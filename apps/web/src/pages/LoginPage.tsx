import { FormEvent, useState } from "react";
import { ArrowRight, KeyRound, User } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useLogin, useSession } from "../features/auth/session";

export function LoginPage() {
  const session = useSession();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (session.data?.authenticated) return <Navigate to="/" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session.isSuccess || login.isPending) return;
    try {
      await login.mutateAsync({ username, password });
      const destination =
        (location.state as { from?: string } | null)?.from ?? "/";
      navigate(destination, { replace: true });
    } catch {
      // React Query exposes the safe error in the form; keep the rejected promise handled.
    }
  }

  return (
    <main className="login-page">
      <aside className="login-intro" aria-label="Giới thiệu SplitBind">
        <p className="login-intro-title">
          Tài liệu có nguồn.
          <br />
          Niềm tin có cơ sở.
        </p>
        <p>Cấp phát và kiểm tra tài liệu trong một nơi.</p>
        <div className="login-principle">
          <span>01</span>
          <p>Tạo bản cấp phát riêng cho từng người nhận.</p>
        </div>
        <div className="login-principle">
          <span>02</span>
          <p>Đối chiếu tệp, đọc kết luận, kiểm tra bằng chứng.</p>
        </div>
        <p className="login-note">
          Chữ ký số · Toàn vẹn tệp · Hồ sơ kiểm chứng
        </p>
      </aside>
      <section className="login-panel" aria-labelledby="login-heading">
        <div className="login-panel-header">
          <h1 id="login-heading">Đăng nhập SplitBind</h1>
          <p className="login-subtitle">
            Nhập thông tin tài khoản được cấp để truy cập không gian làm việc.
          </p>
        </div>
        <form
          className="form-stack"
          aria-label="Đăng nhập SplitBind"
          onSubmit={(event) => void submit(event)}
          aria-busy={session.isPending || login.isPending}
        >
          <div className="field">
            <label htmlFor="username">Tên đăng nhập</label>
            <div className="input-with-icon">
              <span className="input-icon" aria-hidden="true">
                <User size={17} />
              </span>
              <input
                id="username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                placeholder="Tên tài khoản được cấp"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="password">Mật khẩu</label>
            <div className="input-with-icon">
              <span className="input-icon" aria-hidden="true">
                <KeyRound size={17} />
              </span>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
          </div>
          {session.isPending ? (
            <p className="form-error" role="status">Đang chuẩn bị đăng nhập…</p>
          ) : session.error ? (
            <div>
              <p className="form-error" role="alert">Không thể chuẩn bị phiên đăng nhập. Vui lòng thử lại.</p>
              <button className="button button-secondary" type="button" disabled={session.isFetching} onClick={() => void session.refetch()}>
                Thử lại kết nối
              </button>
            </div>
          ) : login.error ? (
            <p className="form-error" role="alert">
              {login.error.message}
            </p>
          ) : (
            <p className="form-error" aria-hidden="true">
              &nbsp;
            </p>
          )}
          <button
            className="button button-primary login-button"
            type="submit"
            disabled={!session.isSuccess || login.isPending}
            data-state={login.isPending ? "loading" : "default"}
          >
            <span>{login.isPending ? "Đang đăng nhập" : "Đăng nhập"}</span>
            <ArrowRight size={17} aria-hidden="true" />
          </button>
        </form>
      </section>
    </main>
  );
}
