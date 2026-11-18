import React from "react";
import { api, qs } from "../api.js";
import { Alert, Field, NextAction, useAsync } from "../components/ui.jsx";
import { RankingTable } from "./WorkspacePage.jsx";

function todayIst() {
  return new Date(Date.now() + 5.5 * 3600 * 1000).toISOString().slice(0, 10);
}

export default function PreferredSuppliersPage() {
  const [asOf, setAsOf] = React.useState(todayIst());
  const [itemCode, setItemCode] = React.useState("");
  const [pin, setPin] = React.useState("");
  const [items, setItems] = React.useState([]);
  const [versions, setVersions] = React.useState([]);
  const [data, setData] = React.useState(null);
  const { busy, error, run } = useAsync();

  React.useEffect(() => {
    api.get("/items").then(setItems).catch(() => {});
    api.get("/policy").then((v) => setVersions(v.filter((x) => ["ACTIVE", "SUPERSEDED"].includes(x.status)))).catch(() => {});
  }, []);
  const load = React.useCallback(
    () => run(async () => setData(await api.get(`/preferred-suppliers${qs({ as_of: asOf, item_code: itemCode, policy_version: pin })}`))),
    [run, asOf, itemCode, pin]
  );
  React.useEffect(() => {
    if (asOf) load();
  }, [load, asOf]);
  const exportCsv = () =>
    run(() => api.download(`/preferred-suppliers/export${qs({ as_of: asOf, policy_version: pin })}`, `preferred_suppliers_${asOf}.csv`));

  return (
    <div>
      <h1 className="h1 mb-1">Preferred suppliers</h1>
      <NextAction>Choose the as-of date and press Export CSV (top {data?.export_count ?? "N"} per item).</NextAction>
      <div className="card mb-3 flex flex-wrap items-end gap-3">
        <Field label="As of">
          <input type="date" className="input" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </Field>
        <Field label="Item">
          <select className="input" value={itemCode} onChange={(e) => setItemCode(e.target.value)}>
            <option value="">All items</option>
            {items.map((i) => (
              <option key={i.item_code} value={i.item_code}>
                {i.item_code} {i.description}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Policy version">
          <select className="input" value={pin} onChange={(e) => setPin(e.target.value)}>
            <option value="">Effective on the as-of date</option>
            {versions.map((v) => (
              <option key={v.id} value={v.version_label}>
                v{v.version_label}
              </option>
            ))}
          </select>
        </Field>
        <button className="btn-primary" disabled={busy || !asOf} onClick={exportCsv}>
          Export CSV
        </button>
      </div>
      <Alert>{error}</Alert>
      {data && (
        <>
          <p className="mb-2 text-sm text-slate-600">
            Policy v{data.policy_version}; weights {Object.entries(data.weights).map(([k, v]) => `${k} ${v}`).join(", ")}.
          </p>
          <div className="space-y-3">
            {data.items.map((it) =>
              it.suppliers.length ? (
                <RankingTable key={it.item_code} title={`${it.item_code} ${it.description} (${it.category})`} ranking={it.suppliers} />
              ) : (
                <div key={it.item_code} className="card text-sm text-slate-500">
                  {it.item_code} {it.description}: no eligible supplier with recent history or a contract.
                </div>
              )
            )}
          </div>
        </>
      )}
    </div>
  );
}
