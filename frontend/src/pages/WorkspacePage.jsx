import React from "react";
import { useSearchParams } from "react-router-dom";
import { api, qs } from "../api.js";
import { Alert, Field, Modal, NextAction, RouteChip, StatusChip, inr, useAsync } from "../components/ui.jsx";

const ROUTES = ["", "CONTRACT_PO", "EMERGENCY_PO", "SPOT_PO", "RFQ", "RFP", "CAPEX_SOURCING", "NEW_ITEM_SOURCING", "NOT_PROCESSED"];
const STATUSES = ["", "PROPOSED", "APPROVED"];

function Condition({ node, depth = 0 }) {
  if (!node) return null;
  for (const kind of ["all", "any"]) {
    if (node[kind]) {
      return (
        <div className={depth ? "ml-3 border-l border-slate-200 pl-2" : ""}>
          <span className="text-xs text-slate-500">{kind === "all" ? "all of" : "any of"}</span>
          {node[kind].map((c, i) => (
            <Condition key={i} node={c} depth={depth + 1} />
          ))}
        </div>
      );
    }
  }
  const val = node.value !== node.resolved && typeof node.value === "string" && node.value.startsWith("$")
    ? `${node.value} = ${JSON.stringify(node.resolved)}`
    : JSON.stringify(node.resolved);
  return (
    <div className="flex gap-2 text-xs">
      <span className={node.passed ? "text-emerald-600" : "text-rose-600"}>{node.passed ? "✓" : "✗"}</span>
      <span className="font-mono">
        {node.fact} {node.op} {val}
      </span>
      <span className="text-slate-500">(actual: {JSON.stringify(node.actual)})</span>
    </div>
  );
}

function WhyPanel({ d }) {
  const why = d.why || {};
  return (
    <div className="space-y-3">
      <div className="card">
        <h3 className="h2 mb-1">Why this decision</h3>
        {why.fired ? (
          <p className="text-sm">
            Policy v{why.policy_version} clause <b>§{why.fired.clause}</b> (rule {why.fired.id}): {why.fired.text}
          </p>
        ) : (
          <p className="text-sm">No rule fired.</p>
        )}
        <p className="mt-1 text-xs text-slate-600">{d.original.reason}</p>
        {why.warnings?.length > 0 && <Alert kind="warning">{why.warnings.join("\n")}</Alert>}
      </div>
      <div className="card">
        <h3 className="h2 mb-1">Facts</h3>
        <table className="text-sm">
          <tbody>
            {Object.entries(why.facts || {}).map(([k, v]) => (
              <tr key={k} className="border-t">
                <td className="td font-mono text-xs">{k}</td>
                <td className="td">{JSON.stringify(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3 className="h2 mb-1">Rules checked (in policy order)</h3>
        {(why.rules_checked || []).map((r) => (
          <div key={r.id} className="mb-2">
            <div className="text-sm">
              <span className={r.matched && r.fulfilled !== false ? "font-semibold text-emerald-700" : "text-slate-600"}>
                §{r.clause} ({r.id}) {r.matched ? (r.fulfilled === false ? "matched, strategy not fulfilled" : "fired") : "did not match"}
              </span>
              {r.note && <span className="ml-1 text-xs text-slate-500">{r.note}</span>}
            </div>
            <Condition node={r.conditions} />
          </div>
        ))}
      </div>
      {(d.contract || why.valuation) && (
        <div className="card text-sm">
          <h3 className="h2 mb-1">Contract / price relied on</h3>
          {d.contract && (
            <p>
              Contract {d.contract.contract_id} ({d.contract.source}) with {d.contract.supplier_id} {d.contract.supplier_name}, rate{" "}
              {d.contract.rate}, valid {d.contract.start_date} to {d.contract.end_date}, ceiling {inr(d.contract.value_cap)}, left before
              this requirement {inr(d.contract.remaining_before)}
            </p>
          )}
          {why.contracts?.skipped?.map((s) => (
            <p key={s.contract_id} className="text-xs text-slate-600">
              Skipped {s.contract_id}: {s.reason}
            </p>
          ))}
          {why.valuation && (
            <p>
              Valued from {why.valuation.source || "nothing"} at {why.valuation.unit_price} = {inr(why.valuation.value)}
              {why.valuation.last_po &&
                ` (last PO ${why.valuation.last_po.po_number} on ${why.valuation.last_po.po_date} from ${why.valuation.last_po.supplier_id} at ${why.valuation.last_po.unit_price})`}
            </p>
          )}
        </div>
      )}
      <RankingTable ranking={d.ranking} />
    </div>
  );
}

export function RankingTable({ ranking, title = "Preferred-supplier ranking" }) {
  if (!ranking?.length) return null;
  const factors = Object.keys(ranking[0].factors);
  return (
    <div className="card overflow-auto">
      <h3 className="h2 mb-1">{title}</h3>
      <table className="min-w-full text-sm">
        <thead>
          <tr>
            <th className="th">#</th>
            <th className="th">Supplier</th>
            {factors.map((f) => (
              <th key={f} className="th">
                {f}
              </th>
            ))}
            <th className="th">Score</th>
            <th className="th">Ref price</th>
          </tr>
        </thead>
        <tbody>
          {ranking.map((r) => (
            <tr key={r.supplier_id} className="border-t">
              <td className="td">{r.rank}</td>
              <td className="td">
                {r.supplier_id} {r.name}
              </td>
              {factors.map((f) => (
                <td key={f} className="td text-xs" title={`raw ${JSON.stringify(r.factors[f].raw)}, scaled ${r.factors[f].scaled} × weight ${r.factors[f].weight}`}>
                  {Number(r.factors[f].contribution).toFixed(4)}
                  <span className="block text-slate-400">
                    {JSON.stringify(r.factors[f].raw)} × {r.factors[f].weight}
                  </span>
                </td>
              ))}
              <td className="td font-semibold">{Number(r.score).toFixed(4)}</td>
              <td className="td">
                {r.reference_price}
                <span className="block text-xs text-slate-400">
                  {r.reference?.source === "po" ? `PO ${r.reference.po_number}` : r.reference?.contract_id}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OverrideModal({ d, onClose, onDone }) {
  const [form, setForm] = React.useState({
    decision: d.effective.decision || "PO",
    route: d.effective.route,
    supplier_id: d.effective.supplier_id || "",
    unit_price: d.effective.unit_price || "",
    suggested: (d.effective.suggested || []).join(";"),
    comment: "",
  });
  const { busy, error, run } = useAsync();
  const submit = () =>
    run(async () => {
      await api.post(`/requirements/${d.id}/override`, {
        comment: form.comment,
        decision: form.decision,
        route: form.route,
        supplier_id: form.supplier_id || null,
        unit_price: form.unit_price || null,
        suggested_supplier_ids: form.suggested.split(/[;,]/).map((s) => s.trim()).filter(Boolean),
      });
      onDone();
    });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <Modal title={`Override ${d.group_id}`} onClose={onClose}>
      <Field label="Decision">
        <select className="input" value={form.decision} onChange={set("decision")}>
          <option value="PO">PO</option>
          <option value="SOURCING_REQUEST">SOURCING_REQUEST</option>
        </select>
      </Field>
      <Field label="Route">
        <input className="input w-full" value={form.route} onChange={set("route")} />
      </Field>
      {form.decision === "PO" ? (
        <>
          <Field label="Supplier ID">
            <input className="input" value={form.supplier_id} onChange={set("supplier_id")} />
          </Field>
          <Field label="Unit price">
            <input className="input" value={form.unit_price} onChange={set("unit_price")} />
          </Field>
        </>
      ) : (
        <Field label="Suggested suppliers (; separated)">
          <input className="input w-full" value={form.suggested} onChange={set("suggested")} />
        </Field>
      )}
      <Field label="Comment (required)">
        <textarea className="input h-20 w-full" value={form.comment} onChange={set("comment")} />
      </Field>
      <Alert>{error}</Alert>
      <button className="btn-primary" disabled={busy || form.comment.trim().length < 3} onClick={submit}>
        Save override
      </button>
    </Modal>
  );
}

function Detail({ id, onChanged }) {
  const [d, setD] = React.useState(null);
  const [tab, setTab] = React.useState("why");
  const [confirming, setConfirming] = React.useState(false);
  const [overriding, setOverriding] = React.useState(false);
  const [notice, setNotice] = React.useState("");
  const { busy, error, run } = useAsync();
  const load = React.useCallback(() => run(async () => setD(await api.get(`/requirements/${id}`))), [id, run]);
  React.useEffect(() => {
    setNotice("");
    load();
  }, [load]);
  if (!d) return <Alert>{error}</Alert>;
  const eff = d.effective;
  const approved = eff.status === "APPROVED";
  const group = d.po_group;
  const approve = () =>
    run(async () => {
      const res = await api.post(`/requirements/${id}/approve`);
      setConfirming(false);
      setNotice(`Created ${res.display} (${res.type}) covering ${res.requirements.length} requirement(s).`);
      await load();
      onChanged();
    });
  return (
    <div className="space-y-3">
      <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="h1">
              {d.group_id} <span className="font-mono text-base">{d.item_code}</span> {d.item?.description}
            </h2>
            <p className="text-sm text-slate-600">
              {d.plant} · {d.total_qty} {d.item?.uom} · value {inr(d.value)} · policy v{d.policy_version} · requirement date {d.requirement_date}
              {d.is_emergency && " · EMERGENCY"}
            </p>
          </div>
          <div className="flex gap-2">
            <button className="btn-primary" disabled={busy || approved || !eff.decision} onClick={() => setConfirming(true)}>
              Approve
            </button>
            <button className="btn-secondary" disabled={busy || approved} onClick={() => setOverriding(true)}>
              Override
            </button>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <RouteChip route={eff.route} />
          <StatusChip status={eff.status} />
          {eff.kind === "OVERRIDE" && <span className="text-xs text-amber-700">buyer override: {eff.comment}</span>}
          {eff.supplier_id && (
            <span>
              {eff.supplier_id} {d.supplier_names[eff.supplier_id]} at {eff.unit_price}
            </span>
          )}
          {eff.suggested?.length > 0 && <span>suggested: {eff.suggested.map((s) => `${s} ${d.supplier_names[s] || ""}`).join(", ")}</span>}
          {group.display && <span className="text-slate-500">on {group.display}</span>}
          {d.order && <span className="font-medium text-emerald-700">order {d.order.display}</span>}
        </div>
        <Alert kind="success">{notice}</Alert>
        <Alert>{error}</Alert>
      </div>
      <div className="flex gap-1">
        {[["why", "Why"], ["lines", `PR lines (${d.lines.length})`], ["history", "Decisions & audit"]].map(([k, l]) => (
          <button key={k} className={tab === k ? "btn-primary" : "btn-secondary"} onClick={() => setTab(k)}>
            {l}
          </button>
        ))}
      </div>
      {tab === "why" && <WhyPanel d={d} />}
      {tab === "lines" && (
        <div className="card overflow-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["PR line", "created", "requester", "dept", "description", "qty", "need by", "urgency"].map((h) => (
                  <th key={h} className="th">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.lines.map((l) => (
                <tr key={l.key} className="border-t">
                  <td className="td">{l.key}</td>
                  <td className="td">{l.created_at}</td>
                  <td className="td">{l.requester}</td>
                  <td className="td">{l.department}</td>
                  <td className="td">{l.description || l.item_code_raw}</td>
                  <td className="td">
                    {l.quantity} {l.uom}
                  </td>
                  <td className="td">{l.need_by}</td>
                  <td className="td">{l.urgency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab === "history" && (
        <div className="card space-y-2 text-sm">
          {d.decisions.map((x) => (
            <div key={x.id} className="border-b pb-1">
              <StatusChip status={x.status} /> {x.kind} #{x.id}: {x.decision} / {x.route} {x.supplier_id || ""} {x.unit_price || ""}{" "}
              {x.suggested?.join(";")} — by {x.created_by} {x.comment && `“${x.comment}”`}
            </div>
          ))}
          <h3 className="h2 pt-2">Audit log</h3>
          {d.audit.length === 0 && <p className="text-slate-500">No actions yet.</p>}
          {d.audit.map((a) => (
            <details key={a.id} className="border-b pb-1">
              <summary>
                {a.at.replace("T", " ").slice(0, 19)} UTC · {a.who} ({a.role}) · {a.action} {a.comment && `· “${a.comment}”`}
              </summary>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <pre className="overflow-auto bg-slate-50 p-1">before: {JSON.stringify(a.before, null, 1)}</pre>
                <pre className="overflow-auto bg-slate-50 p-1">after: {JSON.stringify(a.after, null, 1)}</pre>
              </div>
            </details>
          ))}
        </div>
      )}
      {confirming && (
        <Modal title="Approve" onClose={() => setConfirming(false)}>
          <p className="mb-2 text-sm">
            {group.display
              ? `Approves ${group.display} with ${group.members.length} requirement(s).`
              : eff.decision === "PO"
                ? `Creates a PO to ${eff.supplier_id} for this requirement.`
                : `Creates a sourcing request (${eff.route}) for this requirement.`}
            {group.excluded_overridden > 0 && ` ${group.excluded_overridden} overridden requirement(s) are excluded.`}
          </p>
          <button className="btn-primary" disabled={busy} onClick={approve}>
            Approve
          </button>
        </Modal>
      )}
      {overriding && (
        <OverrideModal
          d={d}
          onClose={() => setOverriding(false)}
          onDone={() => {
            setOverriding(false);
            setNotice("Override saved. It is now the proposed decision; approve it when ready.");
            load();
            onChanged();
          }}
        />
      )}
    </div>
  );
}

export default function WorkspacePage() {
  const [params, setParams] = useSearchParams();
  const [data, setData] = React.useState(null);
  const [route, setRoute] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [runs, setRuns] = React.useState([]);
  const { error, run } = useAsync();
  const runId = params.get("run") || "";
  const selected = params.get("req");

  const load = React.useCallback(
    () => run(async () => setData(await api.get(`/requirements${qs({ run_id: runId, route, status })}`))),
    [run, runId, route, status]
  );
  React.useEffect(() => {
    load();
  }, [load]);
  React.useEffect(() => {
    api.get("/runs").then(setRuns).catch(() => {});
  }, []);

  const select = (id) => {
    const next = new URLSearchParams(params);
    next.set("req", id);
    setParams(next);
  };
  const reqs = data?.requirements || [];
  const pending = data?.status_counts?.PROPOSED || 0;

  return (
    <div>
      <h1 className="h1 mb-1">Buyer workspace</h1>
      <NextAction>
        {selected ? "Review the why-panel, then Approve (or Override with a comment)." : `${pending} requirement(s) waiting for approval. Pick one to review.`}
      </NextAction>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Field label="Run">
          <select
            className="input"
            value={runId}
            onChange={(e) => {
              const next = new URLSearchParams();
              if (e.target.value) next.set("run", e.target.value);
              setParams(next);
            }}
          >
            <option value="">Latest batch run</option>
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                R{r.run_id} {r.kind} {r.filename} ({r.created_at.slice(0, 16).replace("T", " ")})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Route">
          <select className="input" value={route} onChange={(e) => setRoute(e.target.value)}>
            {ROUTES.map((r) => (
              <option key={r} value={r}>
                {r || "All routes"}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s || "All statuses"}
              </option>
            ))}
          </select>
        </Field>
        {data?.run && (
          <span className="pb-2 text-sm text-slate-500">
            R{data.run.run_id} · {data.run.filename} · {reqs.length} requirements shown
          </span>
        )}
      </div>
      <Alert>{error}</Alert>
      {data && !data.run && <Alert kind="info">No runs yet. Upload a batch or raise a request in chat first.</Alert>}
      <div className="grid gap-3 lg:grid-cols-[minmax(0,26rem)_1fr]">
        <div className="card max-h-[75vh] overflow-auto p-0">
          <table className="min-w-full">
            <thead className="sticky top-0 bg-slate-50">
              <tr>
                <th className="th">Req</th>
                <th className="th">Item / plant</th>
                <th className="th">Value</th>
                <th className="th">Route</th>
              </tr>
            </thead>
            <tbody>
              {reqs.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => select(r.id)}
                  className={`cursor-pointer border-t hover:bg-indigo-50 ${String(r.id) === selected ? "bg-indigo-100" : ""}`}
                >
                  <td className="td">
                    {r.group_id}
                    <span className="block text-xs text-slate-500">{r.line_count} line(s)</span>
                  </td>
                  <td className="td">
                    {r.item_code} {r.item_description}
                    <span className="block text-xs text-slate-500">
                      {r.plant} · {r.effective.supplier_id || r.effective.suggested.join(";")}
                    </span>
                  </td>
                  <td className="td whitespace-nowrap">{inr(r.value)}</td>
                  <td className="td">
                    <RouteChip route={r.effective.route} />
                    <div className="mt-0.5">
                      <StatusChip status={r.effective.status} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>{selected ? <Detail key={selected} id={selected} onChanged={load} /> : <p className="text-sm text-slate-500">Select a requirement.</p>}</div>
      </div>
    </div>
  );
}
