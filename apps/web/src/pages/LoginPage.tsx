import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useLogin, useSession } from "../features/auth/session";

export function LoginPage() {
  const session = useSession();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (session.data?.authenticated) return <Navigate to="/issue" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await login.mutateAsync({ username, password });
      const destination = (location.state as { from?: string } | null)?.from ?? "/issue";
      navigate(destination, { replace: true });
    } catch {
      // React Query exposes the safe error in the form; keep the rejected promise handled.
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-heading">
        <p className="product-mark" aria-hidden="true">SB</p>
        <h1 id="login-heading">Đăng nhập SplitBind</h1>
        <p>Tiếp tục vào không gian cấp phát tài liệu của tổ chức.</p>
        <form className="form-stack" onSubmit={(event) => void submit(event)} aria-busy={login.isPending}>
          <div className="field">
            <label htmlFor="username">Tên đăng nhập</label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
            <p className="field-help">Tài khoản do quản trị viên của tổ chức cấp.</p>
          </div>
          <div className="field">
            <label htmlFor="password">Mật khẩu</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <p className="field-help">Ứng dụng không ghi mật khẩu vào localStorage hoặc trạng thái dùng chung phía trình duyệt.</p>
          </div>
          {login.error ? <p className="form-error" role="alert">{login.error.message}</p> : <p className="form-error" aria-hidden="true">&nbsp;</p>}
          <button className="button button-primary" type="submit" disabled={login.isPending} data-state={login.isPending ? "loading" : "default"}>
            {login.isPending ? "Đang đăng nhập" : "Đăng nhập"}
          </button>
        </form>
      </section>
    </main>
  );
}
