import React from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api, getUser, setUser } from "./api.js";
import ChatPage from "./pages/ChatPage.jsx";
import BatchPage from "./pages/BatchPage.jsx";
import WorkspacePage from "./pages/WorkspacePage.jsx";
import PolicyPage from "./pages/PolicyPage.jsx";
import ContractsPage from "./pages/ContractsPage.jsx";
import PreferredSuppliersPage from "./pages/PreferredSuppliersPage.jsx";

const NAV = [
  ["/chat", "Raise a request"],
  ["/batch", "Batch upload"],
  ["/workspace", "Buyer workspace"],
  ["/policy", "Policy"],
  ["/contracts", "Contracts"],
  ["/preferred", "Preferred suppliers"],
];

function UserSelector() {
  const [user, setLocal] = React.useState(getUser());
  const update = (patch) => {
    const next = { ...user, ...patch };
    setLocal(next);
    setUser(next);
  };
  return (
    <div className="flex items-center gap-2 text-sm">
      <input
        className="input w-32"
        value={user.name}
        onChange={(e) => update({ name: e.target.value })}
        aria-label="user name"
      />
      <select className="input" value={user.role} onChange={(e) => update({ role: e.target.value })} aria-label="role">
        <option value="requester">requester</option>
        <option value="buyer">buyer</option>
        <option value="procurement">procurement</option>
      </select>
      <input
        className="input w-28"
        value={user.department}
        placeholder="department"
        onChange={(e) => update({ department: e.target.value })}
        aria-label="department"
      />
    </div>
  );
}

function HealthBadge() {
  const [health, setHealth] = React.useState(null);
  React.useEffect(() => {
    api.get("/health").then(setHealth).catch(() => setHealth({ status: "error" }));
  }, []);
  if (!health) return null;
  if (health.status !== "ok") return <span className="rounded bg-rose-100 px-2 py-0.5 text-xs text-rose-800">API down</span>;
  const on = health.llm === "enabled";
  return (
    <span className="flex items-center gap-2 text-xs">
      <span className="rounded bg-slate-100 px-2 py-0.5">policy v{health.active_policy}</span>
      <span
        className={`rounded px-2 py-0.5 ${on ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-600"}`}
        title={on ? `model ${health.llm_model}` : "rule-based fallback in use"}
      >
        AI: {on ? "on" : "off"}
      </span>
    </span>
  );
}

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-2">
          <div className="flex items-center gap-4">
            <span className="font-semibold text-indigo-700">Corvo PR→PO</span>
            <nav className="flex flex-wrap gap-1">
              {NAV.map(([to, label]) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `rounded px-2 py-1 text-sm ${isActive ? "bg-indigo-50 font-medium text-indigo-700" : "text-slate-600 hover:bg-slate-100"}`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <HealthBadge />
            <UserSelector />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-4">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/batch" element={<BatchPage />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/policy" element={<PolicyPage />} />
          <Route path="/contracts" element={<ContractsPage />} />
          <Route path="/preferred" element={<PreferredSuppliersPage />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </main>
    </div>
  );
}
