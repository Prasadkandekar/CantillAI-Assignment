import React from "react";
import Icon from "./Icon.jsx";
import SpikeMark from "./SpikeMark.jsx";

// 56px top bar shown below 768px: hamburger + wordmark.
export default function MobileBar({ onOpen }) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-sm border-b border-hairline bg-canvas px-md md:hidden">
      <button className="btn-icon-ghost" onClick={onOpen} aria-label="Open menu">
        <Icon name="menu" />
      </button>
      <SpikeMark size={22} className="text-primary" />
      <span className="font-serif text-title-lg font-medium tracking-[-0.02em] text-ink">Corvo</span>
    </header>
  );
}
