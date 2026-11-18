import React from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Alert, Field, NextAction, RouteChip, useAsync } from "../components/ui.jsx";

const COLUMNS = [
  "pr_no", "pr_line", "resolved_item_code", "group_id", "po_id", "decision", "route", "supplier_id",
  "unit_price", "group_value_inr", "suggested_supplier_ids", "policy_version", "reason",
];

export default function BatchPage() {
  const [file, setFile] = React.useState(null);
  const [versions, setVersions] = React.useState([]);
  const [pin, setPin] = React.useState("");
  const [asOf, setAsOf] = React.useState("");
  const [result, setResult] = React.useState(null);
  const [routeFilter, setRouteFilter] = React.useState("");
  const [drag, setDrag] = React.useState(false);
  const { busy, error, run } = useAsync();

  React.useEffect(() => {
    api.get("/policy").then((v) => setVersions(v.filter((x) => ["ACTIVE", "SUPERSEDED"].includes(x.status)))).catch(() => {});
  }, []);

  const process = () =>
    run(async () => {
      const form = new FormData();
      form.append("file", file);
      if (pin) form.append("policy_version", pin);
      if (asOf) form.append("as_of", asOf);
      setResult(await api.upload("/process-batch", form));
    });

  const download = () => run(() => api.download(`/runs/${result.run_id}/export`, `decisions_run${result.run_id}.csv`));

  const rows = result ? result.rows.filter((r) => !routeFilter || r.route === routeFilter) : [];
  const active = versions.find((v) => v.status === "ACTIVE");

  return (
    <div>
      <h1 className="h1 mb-1">Batch upload</h1>
      <NextAction>{result ? "Download the decisions CSV, or open the workspace to approve." : "Choose the PR batch CSV and press Process batch."}</NextAction>
      <div className="card mb-3 flex flex-wrap items-end gap-4">
        <div
          className={`flex h-24 w-80 cursor-pointer items-center justify-center rounded-md border-2 border-dashed text-sm ${
            drag ? "border-indigo-500 bg-indigo-50" : "border-slate-300"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
          }}
          onClick={() => document.getElementById("batch-file").click()}
        >
          {file ? file.name : "Drop a CSV here or click to choose"}
          <input id="batch-file" type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => setFile(e.target.files[0] || null)} />
        </div>
        <Field label="Policy version" hint="Default: the version effective on each PR's date">
          <select className="input" value={pin} onChange={(e) => setPin(e.target.value)}>
            <option value="">By PR date{active ? ` (active v${active.version_label})` : ""}</option>
            {versions.map((v) => (
              <option key={v.id} value={v.version_label}>
                Process under v{v.version_label} ({v.status.toLowerCase()}, from {v.effective_from})
              </option>
            ))}
          </select>
        </Field>
        <Field label="As of date (optional)">
          <input type="date" className="input" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </Field>
        <button className={result ? "btn-secondary" : "btn-primary"} disabled={!file || busy} onClick={process}>
          {busy ? "Processing…" : "Process batch"}
        </button>
        {result && (
          <button className="btn-primary" disabled={busy} onClick={download}>
            Download CSV
          </button>
        )}
      </div>
      <Alert>{error}</Alert>
      {result && (
        <>
          <Alert kind="info">
            Run R{result.run_id}: {result.line_count} lines. Versions used:{" "}
            {Object.entries(result.versions_used).map(([v, n]) => `v${v} for ${n} lines`).join(", ") || "none"}
            {result.pin_version ? ` (pinned to v${result.pin_version})` : ""}.{" "}
            {result.warnings?.length ? `Warnings: ${result.warnings.join("; ")}` : ""}
          </Alert>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <button className={`btn-secondary ${routeFilter === "" ? "ring-2 ring-indigo-400" : ""}`} onClick={() => setRouteFilter("")}>
              All {result.line_count}
            </button>
            {Object.entries(result.counts_by_route)
              .sort((a, b) => b[1] - a[1])
              .map(([route, n]) => (
                <button key={route} onClick={() => setRouteFilter(route === routeFilter ? "" : route)} className={routeFilter === route ? "ring-2 ring-indigo-400 rounded" : ""}>
                  <RouteChip route={route} count={n} />
                </button>
              ))}
            <Link className="btn-secondary ml-auto" to={`/workspace?run=${result.run_id}`}>
              Open in workspace
            </Link>
          </div>
          <div className="card overflow-auto p-0">
            <table className="min-w-full">
              <thead className="sticky top-0 bg-slate-50">
                <tr>{COLUMNS.map((c) => <th key={c} className="th">{c}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className={`border-t ${r.route === "NOT_PROCESSED" ? "bg-rose-50" : ""}`}>
                    {COLUMNS.map((c) => (
                      <td key={c} className={`td ${c === "reason" ? "min-w-[28rem] text-xs" : "whitespace-nowrap"}`}>
                        {c === "route" ? <RouteChip route={r.route} /> : r[c]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
