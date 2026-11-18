import React from "react";
import { api, onUnauthorized, setUser } from "../api.js";

const SESSION_KEY = "corvo_session";
const USER_KEY = "corvo_user";
export const AuthContext = React.createContext(null);

function readSession() {
  try {
    const s = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    return s?.token && s?.user ? s : null;
  } catch {
    return null;
  }
}

// Persist the session and mirror identity into the legacy corvo_user key so api.js headers keep working.
function persist(token, user) {
  localStorage.setItem(SESSION_KEY, JSON.stringify({ token, user }));
  setUser({ name: user.name, role: user.role, department: user.department });
}

export function AuthProvider({ children }) {
  const [session, setSession] = React.useState(() => readSession());
  const [status, setStatus] = React.useState(() => (readSession() ? "loading" : "anon"));

  const clear = React.useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(USER_KEY);
    setSession(null);
    setStatus("anon");
  }, []);

  React.useEffect(() => {
    onUnauthorized(clear);
    return () => onUnauthorized(null);
  }, [clear]);

  // Validate a stored session once on mount.
  React.useEffect(() => {
    if (!readSession()) return undefined;
    let alive = true;
    api
      .me()
      .then(({ user }) => {
        if (!alive) return;
        const token = readSession()?.token;
        persist(token, user);
        setSession({ token, user });
        setStatus("authed");
      })
      .catch((e) => {
        if (alive && e.status === 401) clear();
        else if (alive) setStatus("authed"); // API unreachable: keep the stored session
      });
    return () => {
      alive = false;
    };
  }, [clear]);

  const login = React.useCallback(async (email, password, role) => {
    const { token, user } = await api.login(email, password, role);
    persist(token, user);
    setSession({ token, user });
    setStatus("authed");
    return user;
  }, []);

  const switchRole = React.useCallback(async (role) => {
    const { token, user } = await api.switchRole(role);
    persist(token, user);
    setSession({ token, user });
    return user;
  }, []);

  const value = React.useMemo(
    () => ({ user: session?.user || null, token: session?.token || null, status, login, logout: clear, switchRole }),
    [session, status, login, clear, switchRole]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
