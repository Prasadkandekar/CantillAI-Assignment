import React from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Alert, Field, NextAction, RouteChip, useAsync, useErrorToast } from "../components/ui.jsx";
import AnimatedNumber from "../components/AnimatedNumber.jsx";
import Button from "../components/Button.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Select from "../components/Select.jsx";
import { SkeletonRows } from "../components/Skeleton.jsx";
import { useToast } from "../components/Toast.jsx";

const COLUMNS = [
  "pr_no", "pr_line", "resolved_item_code", "group_id", "po_id", "decision", "route", "supplier_id",
  "unit_price", "group_value_inr", "suggested_supplier_ids", "policy_version", "reason",
];
const MONO = new Set(["pr_no", "pr_line", "resolved_item_code", "group_id", "po_id", "supplier_id", "suggested_supplier_ids", "policy_version"]);

export default function BatchPage() {
  const [file, setFile] = React.useState(null);
  const [versions, setVersions] = React.useState([]);
  const [pin, setPin] = React.useState("");
  const [asOf, setAsOf] = React.useState("");
  const [result, setResult] = React.useState(null);
  const [routeFilter, setRouteFilter] = React.useState("");
  const [drag, setDrag] = React.useState(false);
  const { busy, error, run } = useAsync();
  const toast = useToast();
  useErrorToast(error);

  React.useEffect(() => {
    api.get("/policy").then((v) => setVersions(v.filter((x) => ["ACTIVE", "SUPERSEDED"].includes(x.status)))).catch(() => {});
  }, []);

  const process = () =>
    run(async () => {
      const form = new FormData();
      form.append("file", file);
      if (pin) form.append("policy_version", pin);
      if (asOf) form.append("as_of", asOf);
      const out = await api.upload("/process-batch", form);
      setResult(out);
      toast.success(`Processed ${out.line_count} lines (run R${out.run_id}).`);
    });

  const download = () =>
    run(async () => {
      await api.download(`/runs/${result.run_id}/export`, `decisions_run${result.run_id}.csv`);
      toast.success("Decisions CSV downloaded.");
    });

  const rows = result ? result.rows.filter((r) => !routeFilter || r.route === routeFilter) : [];
  const active = versions.find((v) => v.status === "ACTIVE");
  const versionOptions = [
    { value: "", label: `By PR date${active ? ` (active v${active.version_label})` : ""}` },
    ...versions.map((v) => ({
      value: v.version_label,
      label: `v${v.version_label} (${v.status.toLowerCase()})`,
      hint: `from ${v.effective_from}`,
    })),
  ];

  return (
    <div className="page-enter">
      <PageHeader
        title="Batch upload"
        subtitle="Upload a purchase-requisition CSV and get a routing decision for every line."
      />
      <NextAction>{result ? "Download the decisions CSV, or open the workspace to approve." : "Choose the PR batch CSV and press Process batch."}</NextAction>
      <div className="card mb-lg grid gap-lg lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div>
          <span className="label">PR batch file</span>
          <div
            role="button"
            tabIndex={0}
            className={`flex h-36 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 text-center text-body-sm transition-colors duration-150 focus-visible:ring-[3px] focus-visible:ring-primary/15 ${
              drag ? "border-primary bg-surface-soft" : "border-hairline bg-canvas hover:border-primary hover:bg-surface-soft"
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
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                document.getElementById("batch-file").click();
              }
            }}
          >
            <Icon name={file ? "file" : "upload"} size={24} className="text-primary" />
            {file ? (
              <span className="font-mono text-code text-ink">{file.name}</span>
            ) : (
              <span className="text-muted">Drop a CSV here or click to choose</span>
            )}
            <input id="batch-file" type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => setFile(e.target.files[0] || null)} />
          </div>
          <span className="mt-1 block text-caption font-normal text-muted">CSV with one PR line per row.</span>
        </div>
        <div className="grid content-start gap-x-md sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Select
              label="Policy version"
              value={pin}
              onChange={setPin}
              options={versionOptions}
              className="mb-1"
            />
            <span className="mb-3 block text-caption font-normal text-muted">Default: the version effective on each PR's date.</span>
          </div>
          <Field label="As of date (optional)">
            <input type="date" className="input" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </Field>
          <div className="flex flex-wrap items-end gap-xs pb-3">
            <Button variant={result ? "secondary" : "primary"} disabled={!file} loading={busy} onClick={process}>
              {busy ? "Processing…" : "Process batch"}
            </Button>
            {result && (
              <Button icon="arrow-right" disabled={busy} onClick={download}>
                Download CSV
              </Button>
            )}
          </div>
        </div>
      </div>
      {busy && !result && (
        <div className="card">
          <SkeletonRows rows={6} cols={5} />
        </div>
      )}
      {!result && !busy && (
        <div className="card">
          <EmptyState glyph="upload" title="No batch processed yet" body="Pick a CSV above. Each line is routed to a PO, RFQ, RFP or sourcing request under the chosen policy version." />
        </div>
      )}
      {result && (
        <div className="animate-fade-up">
          <Alert kind="info">
            Run R{result.run_id}: <AnimatedNumber value={result.line_count} /> lines. Versions used:{" "}
            {Object.entries(result.versions_used).map(([v, n]) => `v${v} for ${n} lines`).join(", ") || "none"}
            {result.pin_version ? ` (pinned to v${result.pin_version})` : ""}.{" "}
            {result.warnings?.length ? `Warnings: ${result.warnings.join("; ")}` : ""}
          </Alert>
          <div className="mb-md flex flex-wrap items-center gap-xs">
            <button
              className={`rounded-pill px-3 py-1 text-caption transition-colors duration-150 ${routeFilter === "" ? "bg-ink text-on-dark" : "bg-surface-card text-ink hover:bg-surface-cream-strong"}`}
              onClick={() => setRouteFilter("")}
            >
              All {result.line_count}
            </button>
            {Object.entries(result.counts_by_route)
              .sort((a, b) => b[1] - a[1])
              .map(([route, n]) => (
                <button
                  key={route}
                  onClick={() => setRouteFilter(route === routeFilter ? "" : route)}
                  className={`rounded-pill transition-shadow duration-150 ${routeFilter === route ? "ring-2 ring-primary" : "hover:ring-1 hover:ring-hairline"}`}
                >
                  <RouteChip route={route} count={n} />
                </button>
              ))}
            <Link className="btn-secondary ml-auto" to={`/workspace?run=${result.run_id}`}>
              Open in workspace
            </Link>
          </div>
          <div className="table-wrap max-h-[70vh]">
            <table className="min-w-full">
              <thead>
                <tr>{COLUMNS.map((c) => <th key={c} className="th whitespace-nowrap">{c}</th>)}</tr>
              </thead>
              <tbody className="stagger">
                {rows.map((r, i) => (
                  <tr key={i} style={{ "--i": Math.min(i, 12) }} className={`transition-colors duration-100 hover:bg-surface-soft ${r.route === "NOT_PROCESSED" ? "bg-error/10" : ""}`}>
                    {COLUMNS.map((c) => (
                      <td key={c} className={`td ${c === "reason" ? "min-w-[28rem] text-caption font-normal text-body" : "whitespace-nowrap"} ${MONO.has(c) ? "font-mono text-code" : ""}`}>
                        {c === "route" ? <RouteChip route={r.route} /> : r[c]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
