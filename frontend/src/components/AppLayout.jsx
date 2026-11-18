import React from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ChatHistoryProvider } from "../chat/ChatHistoryContext.jsx";
import MobileBar from "./MobileBar.jsx";
import Sidebar from "./Sidebar.jsx";

const KEY = "corvo_sidebar";

export default function AppLayout() {
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = React.useState(() => localStorage.getItem(KEY) === "1");
  const [drawer, setDrawer] = React.useState(false);
  const drawerRef = React.useRef(null);

  const toggle = () =>
    setCollapsed((c) => {
      localStorage.setItem(KEY, c ? "0" : "1");
      return !c;
    });

  React.useEffect(() => {
    setDrawer(false);
  }, [pathname]);

  React.useEffect(() => {
    if (!drawer) return undefined;
    drawerRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && setDrawer(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawer]);

  return (
    <ChatHistoryProvider>
    <div className="flex h-screen overflow-hidden bg-canvas">
      <div className="hidden md:block">
        <Sidebar collapsed={collapsed} onToggle={toggle} />
      </div>

      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 animate-fade-in bg-ink/40" onClick={() => setDrawer(false)} aria-hidden="true" />
          <div ref={drawerRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Menu" className="absolute inset-y-0 left-0 animate-slide-in-left focus:outline-none">
            <Sidebar mobile onClose={() => setDrawer(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileBar onOpen={() => setDrawer(true)} />
        <main className="flex-1 overflow-y-auto">
          <div key={pathname.split("/")[1]} className="page-enter mx-auto w-full max-w-content px-lg py-xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
    </ChatHistoryProvider>
  );
}
