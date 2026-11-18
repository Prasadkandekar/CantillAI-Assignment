import React from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth.js";
import { ALL_ROLES, DEMO_PASSWORD, DEMO_USERS } from "../nav.js";
import { Alert } from "../components/ui.jsx";
import Button from "../components/Button.jsx";
import Select from "../components/Select.jsx";
import SpikeMark from "../components/SpikeMark.jsx";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState("requester");
  const [errors, setErrors] = React.useState({});
  const [serverError, setServerError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  if (user) return <Navigate to="/chat" replace />;

  const known = DEMO_USERS.find((u) => u.email === email.trim().toLowerCase());
  const allowed = known ? known.roles : ALL_ROLES;
  const roleOptions = allowed.map((r) => ({ value: r, label: r.charAt(0).toUpperCase() + r.slice(1) }));

  const pickEmail = (value) => {
    setEmail(value);
    const u = DEMO_USERS.find((d) => d.email === value.trim().toLowerCase());
    if (u && !u.roles.includes(role)) setRole(u.roles[u.roles.length - 1]);
  };
  const fillDemo = (u) => {
    setEmail(u.email);
    setPassword(DEMO_PASSWORD);
    setRole(u.roles[u.roles.length - 1]);
    setErrors({});
    setServerError("");
  };

  const submit = async (e) => {
    e.preventDefault();
    const next = {};
    if (!EMAIL_RE.test(email.trim())) next.email = "Enter a valid email address";
    if (!password) next.password = "Password is required";
    setErrors(next);
    setServerError("");
    if (Object.keys(next).length) return;
    setBusy(true);
    try {
      await login(email.trim().toLowerCase(), password, role);
      navigate(location.state?.from || "/chat", { replace: true });
    } catch (err) {
      setServerError(err.message || "Sign in failed");
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-md py-xl">
      <div className="w-full max-w-md animate-fade-up">
        <Link to="/" className="mb-lg flex items-center justify-center gap-2 text-ink">
          <SpikeMark size={28} className="text-primary" />
          <span className="font-serif text-display-sm tracking-[-0.02em]">Corvo</span>
        </Link>
        <div className="card">
          <h1 className="display-sm text-center">Sign in</h1>
          <p className="mb-lg mt-1 text-center text-body-sm text-muted">Use your work email and choose how you're acting.</p>
          <form onSubmit={submit} noValidate className="space-y-md">
            <div>
              <label className="label" htmlFor="login-email">Email</label>
              <input
                id="login-email"
                type="email"
                autoComplete="username"
                className={`input ${errors.email ? "input-error" : ""}`}
                value={email}
                onChange={(e) => pickEmail(e.target.value)}
                aria-invalid={!!errors.email}
              />
              {errors.email && <span className="field-error">{errors.email}</span>}
            </div>
            <div>
              <label className="label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                className={`input ${errors.password ? "input-error" : ""}`}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!errors.password}
              />
              {errors.password && <span className="field-error">{errors.password}</span>}
            </div>
            <Select label="Role" value={role} onChange={setRole} options={roleOptions} />
            <Alert kind="error">{serverError}</Alert>
            <Button type="submit" loading={busy} className="w-full">
              {busy ? "Signing in" : "Sign in"}
            </Button>
          </form>
        </div>

        <div className="mt-lg rounded-lg bg-surface-card p-lg">
          <div className="eyebrow mb-sm">Demo accounts · password {DEMO_PASSWORD}</div>
          <ul className="space-y-2">
            {DEMO_USERS.map((u) => (
              <li key={u.email}>
                <button
                  type="button"
                  onClick={() => fillDemo(u)}
                  className="flex w-full items-center justify-between gap-md rounded-md px-3 py-2 text-left transition-colors duration-150 hover:bg-surface-cream-strong focus-visible:ring-[3px] focus-visible:ring-primary/15"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-code text-ink">{u.email}</span>
                    <span className="block text-caption text-muted">{u.note}</span>
                  </span>
                  <span className="badge-pill bg-canvas capitalize">{u.roles[u.roles.length - 1]}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-sm text-caption text-muted-soft">Demo sign-in only. The API still trusts identity headers.</p>
        </div>
      </div>
    </div>
  );
}
