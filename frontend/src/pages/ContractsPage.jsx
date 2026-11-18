import React from "react";
import { api } from "../api.js";
import { Alert, Field, NextAction, inr, useAsync } from "../components/ui.jsx";

const EMPTY = { contract_id: "", supplier_id: "", supplier_name: "", start_date: "", end_date: "", value_cap: "", lines: [] };

function ContractForm({ initial, meta, onSaved, onCancel }) {
  const [c, setC] = React.useState(initial);
  const [replace, setReplace] = React.useState(false);
  const { busy, error, run } = useAsync();
  React.useEffect(() => setC(initial), [initial]);
  const set = (k) => (e) => setC({ ...c, [k]: e.target.value });
  const setLine = (i, k, v) => setC({ ...c, lines: c.lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)) });
  const save = () =>
    run(async () => {
      const saved = await api.post("/contracts", { ...c, source: meta?.source || "PDF", pdf_filename: meta?.pdf_filename || null, replace });
      onSaved(saved);
    });
  const src = (k) => meta?.field_sources?.[k];
  return (
    <div className="card">
      <h2 className="h2 mb-2">{meta?.pdf_filename ? `Review extracted contract (${meta.pdf_filename})` : "Add contract manually"}</h2>
      {meta?.missing?.length > 0 && <Alert kind="warning">Missing, please fill in: {meta.missing.join(", ")}</Alert>}
      {meta?.warnings?.length > 0 && <Alert kind="warning">{meta.warnings.join("\n")}</Alert>}
      {meta?.exists && (
        <Alert kind="info">
          {c.contract_id} is already saved.{" "}
          {meta.differences.length ? `Differences: ${meta.differences.join("; ")}` : "The document matches the saved contract."}
        </Alert>
      )}
      <div className="grid grid-cols-2 gap-x-4 md:grid-cols-3">
        {[
          ["contract_id", "Contract ID"],
          ["supplier_id", "Supplier ID"],
          ["supplier_name", "Supplier name"],
          ["start_date", "Start date (YYYY-MM-DD)"],
          ["end_date", "End date (YYYY-MM-DD)"],
          ["value_cap", "Value ceiling (INR)"],
        ].map(([k, l]) => (
          <Field key={k} label={l} hint={src(k) ? `from ${src(k)}` : ""}>
            <input className="input w-full" value={c[k] || ""} onChange={set(k)} />
          </Field>
        ))}
      </div>
      <table className="mb-2 min-w-full text-sm">
        <thead>
          <tr>
            <th className="th">Item code</th>
            <th className="th">Description</th>
            <th className="th">UoM</th>
            <th className="th">Rate</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {c.lines.map((l, i) => (
            <tr key={i}>
              {["item_code", "description", "uom", "rate"].map((k) => (
                <td key={k} className="td">
                  <input className="input w-full" value={l[k] || ""} onChange={(e) => setLine(i, k, e.target.value)} />
                </td>
              ))}
              <td className="td">
                <button className="text-xs text-rose-600" onClick={() => setC({ ...c, lines: c.lines.filter((_, j) => j !== i) })}>
                  remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center gap-2">
        <button className="btn-primary" disabled={busy} onClick={save}>
          Save contract
        </button>
        <button className="btn-secondary" onClick={() => setC({ ...c, lines: [...c.lines, { item_code: "", description: "", uom: "", rate: "" }] })}>
          Add line
        </button>
        {meta?.exists && (
          <label className="text-sm">
            <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> replace the saved contract (the signed PDF wins)
          </label>
        )}
        <button className="btn-secondary ml-auto" onClick={onCancel}>
          Cancel
        </button>
      </div>
      <Alert>{error}</Alert>
    </div>
  );
}

export default function ContractsPage() {
  const [contracts, setContracts] = React.useState([]);
  const [form, setForm] = React.useState(null);
  const [notice, setNotice] = React.useState("");
  const { busy, error, run } = useAsync();
  const load = React.useCallback(() => run(async () => setContracts(await api.get("/contracts"))), [run]);
  React.useEffect(() => {
    load();
  }, [load]);
  const extract = (file) =>
    run(async () => {
      const fd = new FormData();
      fd.append("file", file);
      const out = await api.upload("/contracts/extract-pdf", fd);
      setNotice("");
      setForm({ initial: { ...EMPTY, ...out.fields, lines: out.lines }, meta: { ...out, source: "PDF" } });
    });
  return (
    <div>
      <h1 className="h1 mb-1">Contracts</h1>
      <NextAction>{form ? "Check the fields against the PDF, then Save contract." : "Add a contract from its PDF (fields are extracted for you to confirm)."}</NextAction>
      <div className="card mb-3 flex flex-wrap items-end gap-3">
        <Field label="Add from PDF">
          <input type="file" accept=".pdf" disabled={busy} onChange={(e) => e.target.files[0] && extract(e.target.files[0])} />
        </Field>
        <button className="btn-secondary" onClick={() => setForm({ initial: { ...EMPTY, lines: [{ item_code: "", rate: "" }] }, meta: { source: "PDF" } })}>
          Add manually
        </button>
        {busy && <span className="text-sm text-slate-500">Working…</span>}
      </div>
      <Alert>{error}</Alert>
      <Alert kind="success">{notice}</Alert>
      {form && (
        <div className="mb-3">
          <ContractForm
            initial={form.initial}
            meta={form.meta}
            onCancel={() => setForm(null)}
            onSaved={(c) => {
              setForm(null);
              setNotice(`Saved ${c.contract_id}. New batch runs will use it.`);
              load();
            }}
          />
        </div>
      )}
      <div className="card overflow-auto p-0">
        <table className="min-w-full">
          <thead className="bg-slate-50">
            <tr>
              {["Contract", "Supplier", "Term", "Ceiling", "Consumed (register)", "Remaining", "Approved orders", "Source", "Lines"].map((h) => (
                <th key={h} className="th">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {contracts.map((c) => (
              <tr key={c.contract_id} className="border-t">
                <td className="td font-mono">{c.contract_id}</td>
                <td className="td">
                  {c.supplier_id} {c.supplier_name}
                  {c.supplier_status !== "Active" && <span className="ml-1 rounded bg-rose-100 px-1 text-xs text-rose-700">{c.supplier_status}</span>}
                </td>
                <td className="td whitespace-nowrap text-xs">
                  {c.start_date} → {c.end_date}
                </td>
                <td className="td">{inr(c.value_cap)}</td>
                <td className="td">{inr(c.consumed_value)}</td>
                <td className="td font-medium">{inr(c.remaining)}</td>
                <td className="td">{inr(c.approved_orders_value)}</td>
                <td className="td text-xs">
                  {c.source}
                  {c.warnings?.length > 0 && <span className="block text-amber-700">{c.warnings.join("; ")}</span>}
                </td>
                <td className="td text-xs">
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
    </div>
  );
}
