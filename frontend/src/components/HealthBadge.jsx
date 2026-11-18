import React from "react";
import { api } from "../api.js";
import StatusDot from "./StatusDot.jsx";

// Same /health call and fields as the old header badge. `compact` = dot only (collapsed sidebar).
export default function HealthBadge({ compact = false }) {
  const [health, setHealth] = React.useState(null);
  React.useEffect(() => {
    api.get("/health").then(setHealth).catch(() => setHealth({ status: "error" }));
  }, []);
  if (!health) return null;
  if (health.status !== "ok") {
    return (
      <span className="flex items-center gap-2 px-3 text-caption text-error" title="API down">
        <StatusDot tone="error" />
        {!compact && "API down"}
      </span>
    );
  }
  const on = health.llm === "enabled";
  const tip = `policy v${health.active_policy} · AI ${on ? `on (model ${health.llm_model})` : "off (rule-based fallback)"}`;
  return (
    <span className="flex items-center gap-2 px-3 text-caption text-muted" title={tip}>
      <StatusDot tone={on ? "teal" : "success"} pulse />
      {!compact && (
        <span className="truncate">
          policy v{health.active_policy} · AI {on ? "on" : "off"}
        </span>
      )}
    </span>
  );
}
