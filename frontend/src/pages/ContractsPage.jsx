import React from "react";
import { api } from "../api.js";
import { Alert, Field, NextAction, inr, useAsync, useErrorToast } from "../components/ui.jsx";
import Badge from "../components/Badge.jsx";
import Button from "../components/Button.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import { SkeletonRows } from "../components/Skeleton.jsx";
import { useToast } from "../components/Toast.jsx";

const EMPTY = { contract_id: "", supplier_id: "", supplier_name: "", start_date: "", end_date: "", value_cap: "", lines: [] };
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const FIELDS = [
  ["contract_id", "Contract ID", true],
  ["supplier_id", "Supplier ID", true],
  ["supplier_name", "Supplier name", false],
  ["start_date", "Start date (YYYY-MM-DD)", true],
  ["end_date", "End date (YYYY-MM-DD)", true],
  ["value_cap", "Value ceiling (INR)", false],
];

function fieldError(c, meta, k, required) {
  const v = String(c[k] ?? "").trim();
  if (!v && (required || meta?.missing?.includes(k))) return "Required";
  if ((k === "start_date" || k === "end_date") && v && !DATE_RE.test(v)) return "Use YYYY-MM-DD";
  if (k === "value_cap" && v && Number.isNaN(Number(v))) return "Enter a number";
  return "";
}

function ContractForm({ initial, meta, onSaved, onCancel }) {
  const [c, setC] = React.useState(initial);
  const [replace, setReplace] = React.useState(false);
  const [touched, setTouched] = React.useState(false);
  const { busy, error, run } = useAsync();
  useErrorToast(error);
  React.useEffect(() => setC(initial), [initial]);
  const set = (k) => (e) => setC({ ...c, [k]: e.target.value });
  const setLine = (i, k, v) => setC({ ...c, lines: c.lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)) });
  const save = () => {
    setTouched(true);
    return run(async () => {
      const saved = await api.post("/contracts", { ...c, source: meta?.source || "PDF", pdf_filename: meta?.pdf_filename || null, replace });
      onSaved(saved);
    });
  };
  const src = (k) => meta?.field_sources?.[k];
  return (
    <div className="card animate-fade-up">
      <h2 className="h2 mb-md">{meta?.pdf_filename ? `Review extracted contract (${meta.pdf_filename})` : "Add contract manually"}</h2>
      {meta?.missing?.length > 0 && <Alert kind="warning">Missing, please fill in: {meta.missing.join(", ")}</Alert>}
      {meta?.warnings?.length > 0 && <Alert kind="warning">{meta.warnings.join("\n")}</Alert>}
      {meta?.exists && (
        <Alert kind="info">
          {c.contract_id} is already saved.{" "}
          {meta.differences.length ? `Differences: ${meta.differences.join("; ")}` : "The document matches the saved contract."}
        </Alert>
      )}
      <div className="grid gap-x-md sm:grid-cols-2 md:grid-cols-3">
        {FIELDS.map(([k, l, req]) => {
          const err = touched || meta?.missing?.includes(k) ? fieldError(c, meta, k, req) : "";
          return (
            <Field key={k} label={l} hint={src(k) ? `from ${src(k)}` : ""} error={err}>
              <input className={`input ${err ? "input-error" : ""} ${k.endsWith("_id") ? "font-mono" : ""}`} value={c[k] || ""} onChange={set(k)} />
            </Field>
          );
        })}
      </div>
      <div className="table-wrap mb-md">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="th">Item code</th>
              <th className="th">Description</th>
              <th className="th">UoM</th>
              <th className="th">Rate</th>
              <th className="th" />
            </tr>
          </thead>
          <tbody>
            {c.lines.map((l, i) => (
              <tr key={i} className="hover:bg-surface-soft">
                {["item_code", "description", "uom", "rate"].map((k) => (
                  <td key={k} className="td">
                    <input
                      className={`input ${k === "item_code" ? "font-mono" : ""}`}
                      aria-label={k}
                      value={l[k] || ""}
                      onChange={(e) => setLine(i, k, e.target.value)}
                    />
                  </td>
                ))}
                <td className="td">
                  <button className="text-caption text-error hover:underline" onClick={() => setC({ ...c, lines: c.lines.filter((_, j) => j !== i) })}>
                    remove
                  </button>
                </td>
              </tr>
            ))}
            {c.lines.length === 0 && (
              <tr>
                <td className="td text-muted" colSpan={5}>
                  No lines yet. Add one below.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-xs">
        <Button loading={busy} onClick={save}>
          Save contract
        </Button>
        <Button variant="secondary" icon="plus" onClick={() => setC({ ...c, lines: [...c.lines, { item_code: "", description: "", uom: "", rate: "" }] })}>
          Add line
        </Button>
        {meta?.exists && (
          <label className="flex items-center gap-2 text-body-sm">
            <input type="checkbox" className="h-4 w-4 accent-primary" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> replace the saved contract (the signed PDF wins)
          </label>
        )}
        <Button variant="secondary" className="ml-auto" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export default function ContractsPage() {
  const [contracts, setContracts] = React.useState(null);
  const [form, setForm] = React.useState(null);
  const { busy, error, run } = useAsync();
  const toast = useToast();
  useErrorToast(error);
  const load = React.useCallback(() => run(async () => setContracts(await api.get("/contracts"))), [run]);
  React.useEffect(() => {
    load();
  }, [load]);
  const extract = (file) =>
    run(async () => {
      const fd = new FormData();
      fd.append("file", file);
      const out = await api.upload("/contracts/extract-pdf", fd);
      setForm({ initial: { ...EMPTY, ...out.fields, lines: out.lines }, meta: { ...out, source: "PDF" } });
      toast.info("Fields extracted. Check them against the PDF.");
    });
  return (
    <div className="page-enter">
      <PageHeader title="Contracts" subtitle="Rate contracts the policy checks before it falls back to spot buying." />
      <NextAction>{form ? "Check the fields against the PDF, then Save contract." : "Add a contract from its PDF (fields are extracted for you to confirm)."}</NextAction>
      <div className="card mb-lg flex flex-wrap items-center gap-md">
        <label className={`btn-primary cursor-pointer ${busy ? "pointer-events-none opacity-60" : ""}`}>
          <Icon name="upload" size={16} />
          {busy ? "Working…" : "Add from PDF"}
          <input
            type="file"
            accept=".pdf"
            className="hidden"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files[0];
              e.target.value = "";
              if (f) extract(f);
            }}
          />
        </label>
        <Button variant="secondary" icon="plus" onClick={() => setForm({ initial: { ...EMPTY, lines: [{ item_code: "", rate: "" }] }, meta: { source: "PDF" } })}>
          Add manually
        </Button>
        <span className="text-caption font-normal text-muted">PDF only. Extracted values stay editable.</span>
      </div>
      {form && (
        <div className="mb-lg">
          <ContractForm
            initial={form.initial}
            meta={form.meta}
            onCancel={() => setForm(null)}
            onSaved={(c) => {
              setForm(null);
              toast.success(`Saved ${c.contract_id}. New batch runs will use it.`);
              load();
            }}
          />
        </div>
      )}
      {contracts === null ? (
        <div className="card">
          <SkeletonRows rows={5} cols={6} />
        </div>
      ) : contracts.length === 0 ? (
        <div className="card">
          <EmptyState glyph="file" title="No contracts yet" body="Upload a signed PDF or add one by hand. Batch runs use saved contracts for contract POs." />
        </div>
      ) : (
        <div className="table-wrap max-h-[70vh]">
          <table className="min-w-full">
            <thead>
              <tr>
                {["Contract", "Supplier", "Term", "Ceiling", "Consumed (register)", "Remaining", "Approved orders", "Source", "Lines"].map((h) => (
                  <th key={h} className="th whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="stagger">
              {contracts.map((c, i) => (
                <tr key={c.contract_id} style={{ "--i": Math.min(i, 12) }} className="transition-colors duration-100 hover:bg-surface-soft">
                  <td className="td font-mono text-code text-ink">{c.contract_id}</td>
                  <td className="td">
                    <span className="font-mono text-code">{c.supplier_id}</span> {c.supplier_name}
                    {c.supplier_status !== "Active" && (
                      <Badge tone="error" className="ml-2">
                        {c.supplier_status}
                      </Badge>
                    )}
                  </td>
                  <td className="td whitespace-nowrap font-mono text-caption font-normal">
                    {c.start_date} → {c.end_date}
                  </td>
                  <td className="td whitespace-nowrap">{inr(c.value_cap)}</td>
                  <td className="td whitespace-nowrap">{inr(c.consumed_value)}</td>
                  <td className="td whitespace-nowrap font-medium text-ink">{inr(c.remaining)}</td>
                  <td className="td whitespace-nowrap">{inr(c.approved_orders_value)}</td>
                  <td className="td text-caption font-normal">
                    <Badge tone={c.source === "PDF" ? "teal" : "neutral"}>{c.source}</Badge>
                    {c.warnings?.length > 0 && <span className="mt-1 block text-warning">{c.warnings.join("; ")}</span>}
                  </td>
                  <td className="td font-mono text-caption font-normal">
                    {c.lines.map((l) => (
                      <div key={l.item_code}>
                        {l.item_code} @ {l.rate}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
