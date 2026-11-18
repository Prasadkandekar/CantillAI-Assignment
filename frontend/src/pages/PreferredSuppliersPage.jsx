import React from "react";
import { api, qs } from "../api.js";
import { Field, NextAction, useAsync, useErrorToast } from "../components/ui.jsx";
import Button from "../components/Button.jsx";
import EmptyState from "../components/EmptyState.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Select from "../components/Select.jsx";
import { SkeletonCard } from "../components/Skeleton.jsx";
import { useToast } from "../components/Toast.jsx";
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
  const toast = useToast();
  useErrorToast(error);

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
    run(async () => {
      await api.download(`/preferred-suppliers/export${qs({ as_of: asOf, policy_version: pin })}`, `preferred_suppliers_${asOf}.csv`);
      toast.success("Preferred suppliers CSV downloaded.");
    });

  const itemOptions = [{ value: "", label: "All items" }, ...items.map((i) => ({ value: i.item_code, label: `${i.item_code} ${i.description}` }))];
  const versionOptions = [{ value: "", label: "Effective on the as-of date" }, ...versions.map((v) => ({ value: v.version_label, label: `v${v.version_label}` }))];

  return (
    <div className="page-enter">
      <PageHeader
        title="Preferred suppliers"
        subtitle="Ranked supplier shortlist per item, scored under the policy weights."
        actions={
          <Button icon="arrow-right" disabled={!asOf} loading={busy && !!data} onClick={exportCsv}>
            Export CSV
          </Button>
        }
      />
      <NextAction>Choose the as-of date and press Export CSV (top {data?.export_count ?? "N"} per item).</NextAction>
      <div className="card mb-lg grid items-start gap-x-md md:grid-cols-3">
        <Field label="As of">
          <input type="date" className="input" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </Field>
        <div className="mb-3">
          <Select label="Item" value={itemCode} onChange={setItemCode} options={itemOptions} />
        </div>
        <div className="mb-3">
          <Select label="Policy version" value={pin} onChange={setPin} options={versionOptions} />
        </div>
      </div>
      {!data && busy && <SkeletonCard />}
      {data && (
        <div className="animate-fade-up">
          <p className="mb-md text-body-sm text-muted">
            Policy <span className="font-mono text-code text-ink">v{data.policy_version}</span>; weights{" "}
            {Object.entries(data.weights).map(([k, v]) => `${k} ${v}`).join(", ")}.
          </p>
          {data.items.length === 0 && <EmptyState glyph="star" title="No items to rank" body="There are no items for this date and filter." />}
          <div className="stagger space-y-md">
            {data.items.map((it, i) =>
              it.suppliers.length ? (
                <div key={it.item_code} style={{ "--i": Math.min(i, 10) }}>
                  <RankingTable title={`${it.item_code} ${it.description} (${it.category})`} ranking={it.suppliers} />
                </div>
              ) : (
                <div key={it.item_code} style={{ "--i": Math.min(i, 10) }} className="card text-body-sm text-muted">
                  <span className="font-mono text-code text-ink">{it.item_code}</span> {it.description}: no eligible supplier with recent history or a contract.
                </div>
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
}
