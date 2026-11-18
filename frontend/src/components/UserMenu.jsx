import React from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth.js";
import Dropdown, { DropdownDivider, DropdownItem, DropdownLabel } from "./Dropdown.jsx";
import Icon from "./Icon.jsx";
import { useToast } from "./Toast.jsx";

function initials(name) {
  return (name || "?")
    .split(/\s+/)
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export default function UserMenu({ collapsed = false }) {
  const { user, logout, switchRole } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  if (!user) return null;

  const change = async (role) => {
    if (role === user.role) return;
    try {
      await switchRole(role);
      toast.success(`Now acting as ${role}`);
      navigate("/chat");
    } catch (e) {
      toast.error(e.message);
    }
  };

  return (
    <Dropdown
      direction="up"
      minWidth={240}
      trigger={({ open, props }) => (
        <button
          {...props}
          title={`${user.name} · ${user.role}`}
          className={`flex w-full items-center gap-sm rounded-md p-2 text-left transition-colors duration-150 hover:bg-surface-card focus-visible:ring-[3px] focus-visible:ring-primary/15 ${open ? "bg-surface-card" : ""}`}
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-pill bg-primary text-caption text-on-primary">
            {initials(user.name)}
          </span>
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-body-sm font-medium text-ink">{user.name}</span>
                <span className="block truncate text-caption capitalize text-muted">{user.role}</span>
              </span>
              <Icon name="chevron-down" size={16} className="text-muted" />
            </>
          )}
        </button>
      )}
    >
      <DropdownLabel>
        <span className="block truncate text-body-sm text-ink">{user.email}</span>
        <span>
          Signed in as <span className="capitalize">{user.role}</span>
        </span>
      </DropdownLabel>
      {user.allowed_roles?.length > 1 && (
        <>
          <DropdownDivider />
          <DropdownLabel>Switch role</DropdownLabel>
          {user.allowed_roles.map((r) => (
            <DropdownItem key={r} icon={r === user.role ? "check" : "swap"} onClick={() => change(r)}>
              <span className="capitalize">{r}</span>
            </DropdownItem>
          ))}
        </>
      )}
      <DropdownDivider />
      <DropdownItem
        icon="logout"
        danger
        onClick={() => {
          logout();
          navigate("/login", { replace: true });
        }}
      >
        Sign out
      </DropdownItem>
    </Dropdown>
  );
}
