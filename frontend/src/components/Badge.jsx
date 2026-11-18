import React from "react";
import StatusDot from "./StatusDot.jsx";

const TONES = {
  neutral: "badge-neutral",
  coral: "badge-coral",
  success: "badge-success",
  warning: "badge-warning",
  error: "badge-error",
  teal: "badge-teal",
  amber: "badge-amber",
  dark: "badge-dark",
};
const DOT = { success: "success", warning: "warning", error: "error", teal: "teal", amber: "amber" };

export default function Badge({ tone = "neutral", dot = false, className = "", children }) {
  return (
    <span className={`${TONES[tone] || TONES.neutral} ${className}`}>
      {dot && <StatusDot tone={DOT[tone] || "neutral"} />}
      {children}
    </span>
  );
}
