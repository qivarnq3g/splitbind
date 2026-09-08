import { FormEvent, useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ArrowRight, KeyRound, Lock, User } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useLogin, useSession } from "../features/auth/session";

gsap.registerPlugin(useGSAP);

export function LoginPage() {
  const session = useSession();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const containerRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      if (typeof window.matchMedia !== "function") return;
      const media = gsap.matchMedia();

      media.add("(prefers-reduced-motion: no-preference)", () => {
        const tl = gsap.timeline({ defaults: { ease: "power2.out" } });
        tl.fromTo(
          ".login-lattice-svg",
          { autoAlpha: 0, scale: 0.92, rotate: -4 },
          { autoAlpha: 0.45, scale: 1, rotate: 0, duration: 0.6 }
        )
          .fromTo(
            ".intro-badge, .login-intro-title, .login-intro > p:not(.login-intro-title)",
            { autoAlpha: 0, y: 12 },
            { autoAlpha: 1, y: 0, duration: 0.4, stagger: 0.08 },
            "-=0.4"
          )
          .fromTo(
            ".login-panel",
            { autoAlpha: 0, x: 16 },
            { autoAlpha: 1, x: 0, duration: 0.45, clearProps: "all" },
            "-=0.3"
          );
      });

      return () => media.revert();
    },
    { scope: containerRef }
  );

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
    <main ref={containerRef} className="login-page">
      <aside className="login-intro" aria-label="Giới thiệu SplitBind">
        <div className="login-intro-ambient" aria-hidden="true">
          <svg className="login-lattice-svg" viewBox="0 0 400 400" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="200" cy="200" r="160" stroke="currentColor" strokeWidth="1" strokeDasharray="4 4" opacity="0.25" />
            <circle cx="200" cy="200" r="110" stroke="currentColor" strokeWidth="1" opacity="0.35" />
            <circle cx="200" cy="200" r="60" stroke="var(--color-focus)" strokeWidth="1.5" opacity="0.6" />
            <line x1="40" y1="200" x2="360" y2="200" stroke="currentColor" strokeWidth="1" opacity="0.3" />
            <line x1="200" y1="40" x2="200" y2="360" stroke="currentColor" strokeWidth="1" opacity="0.3" />
            <rect x="140" y="140" width="120" height="120" stroke="currentColor" strokeWidth="1" opacity="0.4" />
          </svg>
        </div>
        <div className="login-intro-content">
          <div className="intro-badge" aria-hidden="true">
            <span className="intro-badge-dot" />
            <span>Xác thực an toàn v0.1</span>
          </div>
          <p className="login-intro-title">Bảo vệ tài liệu quan trọng</p>
          <p>Cấp phát và kiểm tra tài liệu trong một nơi.</p>
        </div>
      </aside>
      <section className="login-panel" aria-labelledby="login-heading">
        <div className="login-panel-header">
          <div className="login-badge" aria-hidden="true">
            <Lock size={18} strokeWidth={2.2} />
          </div>
          <h1 id="login-heading">Đăng nhập SplitBind</h1>
          <p className="login-subtitle">Nhập thông tin tài khoản được cấp để truy cập không gian làm việc.</p>
        </div>
        <form className="form-stack" aria-label="Đăng nhập SplitBind" onSubmit={(event) => void submit(event)} aria-busy={login.isPending}>
          <div className="field">
            <label htmlFor="username">Tên đăng nhập</label>
            <div className="input-with-icon">
              <span className="input-icon" aria-hidden="true"><User size={17} /></span>
              <input
                id="username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                placeholder="admin"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="password">Mật khẩu</label>
            <div className="input-with-icon">
              <span className="input-icon" aria-hidden="true"><KeyRound size={17} /></span>
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
          {login.error ? <p className="form-error" role="alert">{login.error.message}</p> : <p className="form-error" aria-hidden="true">&nbsp;</p>}
          <button className="button button-primary login-button" type="submit" disabled={login.isPending} data-state={login.isPending ? "loading" : "default"}>
            <span>{login.isPending ? "Đang đăng nhập" : "Đăng nhập"}</span>
            <ArrowRight size={17} aria-hidden="true" />
          </button>
        </form>
      </section>
    </main>
  );
}
