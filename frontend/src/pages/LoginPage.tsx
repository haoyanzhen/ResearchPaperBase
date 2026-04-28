import type { FormEvent } from "react";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { Alert } from "../components/Alert";
import { useAuth } from "../contexts/AuthContext";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/projects";
  const { login, register, user } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user) {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "login") {
        await login({ credential: form.username, password: form.password });
      } else {
        await register(form);
      }
      navigate(from, { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : "认证失败";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-card__hero">
          <span className="eyebrow">Research Paper Base</span>
          <h1>智能学术研究助手</h1>
          <p>从论文构建、深度研究到综述写作，把项目节奏收在一个工作台里。</p>
        </div>

        <div className="auth-card__panel">
          <div className="segmented">
            <button
              type="button"
              className={mode === "login" ? "segmented__item segmented__item--active" : "segmented__item"}
              onClick={() => setMode("login")}
            >
              登录
            </button>
            <button
              type="button"
              className={mode === "register" ? "segmented__item segmented__item--active" : "segmented__item"}
              onClick={() => setMode("register")}
            >
              注册
            </button>
          </div>

          <form className="form" onSubmit={handleSubmit}>
            {error && <Alert tone="error" message={error} />}
            <label className="field">
              <span>{mode === "login" ? "用户名 / 邮箱" : "用户名"}</span>
              <input
                name="username"
                value={form.username}
                onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
                placeholder={mode === "login" ? "输入用户名或邮箱" : "创建用户名"}
                required
              />
            </label>
            {mode === "register" && (
              <label className="field">
                <span>邮箱</span>
                <input
                  name="email"
                  type="email"
                  value={form.email}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                  placeholder="your.name@example.com"
                  required
                />
              </label>
            )}
            <label className="field">
              <span>密码</span>
              <input
                name="password"
                type="password"
                value={form.password}
                onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                placeholder="至少 6 位"
                required
              />
            </label>
            <button type="submit" className="button button--block" disabled={submitting}>
              {submitting ? "提交中..." : mode === "login" ? "登录" : "创建账号"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
