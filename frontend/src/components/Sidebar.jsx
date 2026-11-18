import React from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/useAuth.js";
import { navSections } from "../nav.js";
import ChatHistory from "./ChatHistory.jsx";
import HealthBadge from "./HealthBadge.jsx";
import Icon from "./Icon.jsx";
import SpikeMark from "./SpikeMark.jsx";
import UserMenu from "./UserMenu.jsx";

// Collapsible left sidebar. `mobile` renders the full-width drawer variant (never collapsed).
export default function Sidebar({ collapsed = false, onToggle, mobile = false, onClose }) {
  const { user } = useAuth();
  const slim = collapsed && !mobile;
  const sections = navSections(user?.role);
  return (
    <aside
      className={`flex h-full flex-col border-r border-hairline bg-surface-soft ${mobile ? "w-72" : `transition-[width] duration-200 ease-out ${slim ? "w-[72px]" : "w-[264px]"}`}`}
      aria-label="Primary"
    >
      <div className={`flex h-16 shrink-0 items-center ${slim ? "justify-center" : "justify-between px-md"}`}>
        <NavLink to="/chat" className="flex items-center gap-2 rounded-md text-ink focus-visible:ring-[3px] focus-visible:ring-primary/15" onClick={onClose}>
          <SpikeMark size={26} className="text-primary" />
          {!slim && <span className="font-serif text-title-lg font-medium tracking-[-0.02em]">Corvo</span>}
        </NavLink>
        {mobile ? (
          <button className="btn-icon-ghost" onClick={onClose} aria-label="Close menu">
            <Icon name="close" />
          </button>
        ) : (
          !slim && (
            <button className="btn-icon-ghost" onClick={onToggle} aria-label="Collapse sidebar">
              <Icon name="chevron-left" />
            </button>
          )
        )}
      </div>
      {slim && (
        <div className="flex justify-center pb-2">
          <button className="btn-icon-ghost" onClick={onToggle} aria-label="Expand sidebar">
            <Icon name="chevron-right" />
          </button>
        </div>
      )}

      <nav className="flex-1 space-y-lg overflow-y-auto overflow-x-hidden px-sm py-xs">
        {sections.map((s) => (
          <div key={s.name}>
            {!slim && <div className="mb-1 px-3 text-caption-uppercase uppercase text-muted-soft">{s.name}</div>}
            <ul className="space-y-0.5">
              {s.items.map((i) => (
                <li key={i.to}>
                  <NavLink
                    to={i.to}
                    onClick={onClose}
                    title={slim ? i.label : undefined}
                    className={({ isActive }) => `sidebar-item ${slim ? "justify-center px-0" : ""} ${isActive ? "sidebar-item-active" : ""}`}
                  >
                    <Icon name={i.icon} />
                    {!slim && <span className="truncate">{i.label}</span>}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <ChatHistory slim={slim} onClose={onClose} />
      </nav>

      <div className="shrink-0 space-y-1 border-t border-hairline p-sm">
        <HealthBadge compact={slim} />
        <UserMenu collapsed={slim} />
      </div>
    </aside>
  );
}
