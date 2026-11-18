// Single source of truth for sidebar items and route role gating (UX only; the backend enforces roles).
export const ALL_ROLES = ["requester", "buyer", "procurement"];
const STAFF = ["buyer", "procurement"];

export const NAV_ITEMS = [
  { to: "/chat", label: "Raise a request", icon: "chat", section: "Requests", roles: ALL_ROLES },
  { to: "/batch", label: "Batch upload", icon: "upload", section: "Requests", roles: STAFF },
  { to: "/workspace", label: "Buyer workspace", icon: "inbox", section: "Buyer", roles: STAFF },
  { to: "/contracts", label: "Contracts", icon: "file", section: "Buyer", roles: STAFF },
  { to: "/preferred", label: "Preferred suppliers", icon: "star", section: "Buyer", roles: STAFF },
  { to: "/policy", label: "Policy", icon: "shield", section: "Governance", roles: ["procurement"] },
];

export const rolesFor = (path) => NAV_ITEMS.find((i) => i.to === path)?.roles || ALL_ROLES;

export function navSections(role) {
  const out = [];
  NAV_ITEMS.filter((i) => i.roles.includes(role)).forEach((i) => {
    let s = out.find((x) => x.name === i.section);
    if (!s) out.push((s = { name: i.section, items: [] }));
    s.items.push(i);
  });
  return out;
}

export const DEMO_USERS = [
  { email: "requester@corvo.demo", roles: ["requester"], note: "Raise requests" },
  { email: "buyer@corvo.demo", roles: ["requester", "buyer"], note: "Requests plus buyer tools" },
  { email: "procurement@corvo.demo", roles: ["requester", "buyer", "procurement"], note: "Everything, incl. policy" },
];export const DEMO_PASSWORD = "corvo-demo";
