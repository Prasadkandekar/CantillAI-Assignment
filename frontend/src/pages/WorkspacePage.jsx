import React from "react";
import { useSearchParams } from "react-router-dom";
import { api, qs } from "../api.js";
import { Alert, Field, Modal, NextAction, RouteChip, StatusChip, inr, useAsync, useErrorToast } from "../components/ui.jsx";
import AnimatedNumber from "../components/AnimatedNumber.jsx";
import Badge from "../components/Badge.jsx";
import Button from "../components/Button.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Select from "../components/Select.jsx";
import { SkeletonCard, SkeletonRows } from "../components/Skeleton.jsx";
import Tabs from "../components/Tabs.jsx";
import { useToast } from "../components/Toast.jsx";

const ROUTES = ["", "CONTRACT_PO", "EMERGENCY_PO", "SPOT_PO", "RFQ", "RFP", "CAPEX_SOURCING", "NEW_ITEM_SOURCING", "NOT_PROCESSED"];
const STATUSES = ["", "PROPOSED", "APPROVED"];

function Condition({ node, depth = 0 }) {
  if (!node) return null;
  for (const kind of ["all", "any"]) {
    if (node[kind]) {
      return (
        <div className={depth ? "ml-3 border-l border-hairline pl-2" : ""}>
          <span className="text-caption font-normal text-muted">{kind === "all" ? "all of" : "any of"}</span>
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
    <div className="flex gap-2 text-caption font-normal">
      <span className={node.passed ? "text-success" : "text-error"}>{node.passed ? "✓" : "✗"}</span>
      <span className="font-mono">
        {node.fact} {node.op} {val}
      </span>
      <span className="text-muted">(actual: {JSON.stringify(node.actual)})</span>
    </div>
  );
}

function WhyPanel({ d }) {
  const why = d.why || {};
  return (
    <div className="stagger space-y-md">
      <div className="card" style={{ "--i": 0 }}>
        <h3 className="h2 mb-2">Why this decision</h3>
        {why.fired ? (
          <p className="text-body-sm">
            Policy <span className="font-mono">v{why.policy_version}</span> clause <b className="font-mono">§{why.fired.clause}</b> (rule <span className="font-mono">{why.fired.id}</span>): {why.fired.text}
          </p>
        ) : (
          <p className="text-body-sm">No rule fired.</p>
        )}
        <p className="mt-1 text-caption font-normal text-muted">{d.original.reason}</p>
        {why.warnings?.length > 0 && <Alert kind="warning">{why.warnings.join("\n")}</Alert>}
      </div>
      <div className="card" style={{ "--i": 1 }}>
        <h3 className="h2 mb-2">Facts</h3>
        <div className="table-wrap">
          <table className="min-w-full">
            <tbody>
              {Object.entries(why.facts || {}).map(([k, v]) => (
                <tr key={k} className="hover:bg-surface-soft">
                  <td className="td font-mono text-code">{k}</td>
                  <td className="td font-mono text-code">{JSON.stringify(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card" style={{ "--i": 2 }}>
        <h3 className="h2 mb-2">Rules checked (in policy order)</h3>
        {(why.rules_checked || []).map((r) => (
          <div key={r.id} className="mb-3">
            <div className="text-body-sm">
              <span className={r.matched && r.fulfilled !== false ? "font-medium text-success" : "text-muted"}>
                <span className="font-mono">§{r.clause} ({r.id})</span> {r.matched ? (r.fulfilled === false ? "matched, strategy not fulfilled" : "fired") : "did not match"}
              </span>
              {r.note && <span className="ml-1 text-caption font-normal text-muted">{r.note}</span>}
            </div>
            <Condition node={r.conditions} />
          </div>
        ))}
      </div>
      {(d.contract || why.valuation) && (
        <div className="card space-y-1 text-body-sm" style={{ "--i": 3 }}>
          <h3 className="h2 mb-2">Contract / price relied on</h3>
          {d.contract && (
            <p>
              Contract <span className="font-mono">{d.contract.contract_id}</span> ({d.contract.source}) with <span className="font-mono">{d.contract.supplier_id}</span> {d.contract.supplier_name}, rate{" "}
              {d.contract.rate}, valid {d.contract.start_date} to {d.contract.end_date}, ceiling {inr(d.contract.value_cap)}, left before
              this requirement {inr(d.contract.remaining_before)}
            </p>
          )}
          {why.contracts?.skipped?.map((s) => (
            <p key={s.contract_id} className="text-caption font-normal text-muted">
              Skipped <span className="font-mono">{s.contract_id}</span>: {s.reason}
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
      <div style={{ "--i": 4 }}>
        <RankingTable ranking={d.ranking} />
      </div>
    </div>
  );
}

export function RankingTable({ ranking, title = "Preferred-supplier ranking" }) {
  if (!ranking?.length) return null;
  const factors = Object.keys(ranking[0].factors);
  return (
    <div className="card transition duration-150 hover:-translate-y-0.5 hover:border-hairline-soft hover:shadow-card">
      <h3 className="h2 mb-2">{title}</h3>
      <div className="table-wrap">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="th">#</th>
              <th className="th">Supplier</th>
              {factors.map((f) => (
                <th key={f} className="th whitespace-nowrap">
                  {f}
                </th>
              ))}
              <th className="th">Score</th>
              <th className="th whitespace-nowrap">Ref price</th>
            </tr>
          </thead>
          <tbody>
            {ranking.map((r) => (
              <tr key={r.supplier_id} className="transition-colors duration-100 hover:bg-surface-soft">
                <td className="td">
                  {r.rank === 1 ? <Badge tone="coral" className="!px-2">1</Badge> : r.rank}
                </td>
                <td className="td whitespace-nowrap">
                  <span className="font-mono text-code">{r.supplier_id}</span> {r.name}
                </td>
                {factors.map((f) => (
                  <td key={f} className="td text-caption font-normal" title={`raw ${JSON.stringify(r.factors[f].raw)}, scaled ${r.factors[f].scaled} × weight ${r.factors[f].weight}`}>
                    <span className="font-mono">{Number(r.factors[f].contribution).toFixed(4)}</span>
                    <span className="block font-mono text-muted-soft">
                      {JSON.stringify(r.factors[f].raw)} × {r.factors[f].weight}
                    </span>
                  </td>
                ))}
                <td className="td font-mono font-semibold text-ink">{Number(r.score).toFixed(4)}</td>
                <td className="td whitespace-nowrap">
                  <span className="font-mono">{r.reference_price}</span>
                  <span className="block font-mono text-caption font-normal text-muted-soft">
                    {r.reference?.source === "po" ? `PO ${r.reference.po_number}` : r.reference?.contract_id}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const DECISIONS = [
  { value: "PO", label: "PO" },
  { value: "SOURCING_REQUEST", label: "SOURCING_REQUEST" },
];

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
  useErrorToast(error);
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
  const short = form.comment.trim().length < 3;
  return (
    <Modal title={`Override ${d.group_id}`} onClose={onClose}>
      <div className="mb-3">
        <Select label="Decision" value={form.decision} onChange={(v) => setForm({ ...form, decision: v })} options={DECISIONS} />
      </div>
      <Field label="Route">
        <input className="input font-mono" value={form.route} onChange={set("route")} />
      </Field>
      {form.decision === "PO" ? (
        <div className="grid gap-x-md sm:grid-cols-2">
          <Field label="Supplier ID">
            <input className="input font-mono" value={form.supplier_id} onChange={set("supplier_id")} />
          </Field>
          <Field label="Unit price">
            <input className="input font-mono" value={form.unit_price} onChange={set("unit_price")} />
          </Field>
        </div>
      ) : (
        <Field label="Suggested suppliers (; separated)">
          <input className="input font-mono" value={form.suggested} onChange={set("suggested")} />
        </Field>
      )}
      <Field
        label="Comment (required)"
        hint="Recorded in the audit log."
        error={form.comment && short ? "Enter at least 3 characters" : ""}
      >
        <textarea className={`input h-24 ${form.comment && short ? "input-error" : ""}`} value={form.comment} onChange={set("comment")} />
      </Field>
      <div className="flex justify-end gap-xs">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button loading={busy} disabled={short} onClick={submit}>
          Save override
        </Button>
      </div>
    </Modal>
  );
}

function Detail({ id, onChanged }) {
  const [d, setD] = React.useState(null);
  const [tab, setTab] = React.useState("why");
  const [confirming, setConfirming] = React.useState(false);
  const [overriding, setOverriding] = React.useState(false);
  const { busy, error, run } = useAsync();
  const toast = useToast();
  const load = React.useCallback(() => run(async () => setD(await api.get(`/requirements/${id}`))), [id, run]);
  React.useEffect(() => {
    load();
  }, [load]);
  React.useEffect(() => {
    if (error && d) toast.error(error);
  }, [error, d, toast]);
  if (!d) {
    if (error) return <Alert>{error}</Alert>;
    return <SkeletonCard />;
  }
  const eff = d.effective;
  const approved = eff.status === "APPROVED";
  const group = d.po_group;
  const approve = () =>
    run(async () => {
      const res = await api.post(`/requirements/${id}/approve`);
      setConfirming(false);
      toast.success(`Created ${res.display} (${res.type}) covering ${res.requirements.length} requirement(s).`);
      await load();
      onChanged();
    });
  return (
    <div className="space-y-md animate-fade-up">
      <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-md">
          <div className="min-w-0">
            <h2 className="display-sm">
              <span className="font-mono text-title-lg">{d.group_id}</span> <span className="font-mono text-title-md text-muted">{d.item_code}</span> {d.item?.description}
            </h2>
            <p className="mt-1 text-body-sm text-muted">
              {d.plant} · {d.total_qty} {d.item?.uom} · value {inr(d.value)} · policy <span className="font-mono">v{d.policy_version}</span> · requirement date {d.requirement_date}
              {d.is_emergency && " · EMERGENCY"}
            </p>
          </div>
          <div className="flex gap-xs">
            <Button loading={busy} disabled={approved || !eff.decision} onClick={() => setConfirming(true)}>
              Approve
            </Button>
            <Button variant="secondary" disabled={busy || approved} onClick={() => setOverriding(true)}>
              Override
            </Button>
          </div>
        </div>
        <div className="mt-md flex flex-wrap items-center gap-xs text-body-sm">
          <RouteChip route={eff.route} />
          <StatusChip status={eff.status} />
          {eff.kind === "OVERRIDE" && <Badge tone="amber">buyer override: {eff.comment}</Badge>}
          {eff.supplier_id && (
            <span>
              <span className="font-mono">{eff.supplier_id}</span> {d.supplier_names[eff.supplier_id]} at {eff.unit_price}
            </span>
          )}
          {eff.suggested?.length > 0 && <span>suggested: {eff.suggested.map((s) => `${s} ${d.supplier_names[s] || ""}`).join(", ")}</span>}
          {group.display && <span className="text-muted">on {group.display}</span>}
          {d.order && <Badge tone="success" dot>order {d.order.display}</Badge>}
        </div>
      </div>
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "why", label: "Why" },
          { id: "lines", label: "PR lines", count: d.lines.length },
          { id: "history", label: "Decisions & audit" },
        ]}
      />
      {tab === "why" && <WhyPanel d={d} />}
      {tab === "lines" && (
        <div className="table-wrap max-h-[60vh]">
          <table className="min-w-full">
            <thead>
              <tr>
                {["PR line", "created", "requester", "dept", "description", "qty", "need by", "urgency"].map((h) => (
                  <th key={h} className="th whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="stagger">
              {d.lines.map((l, i) => (
                <tr key={l.key} style={{ "--i": Math.min(i, 12) }} className="transition-colors duration-100 hover:bg-surface-soft">
                  <td className="td whitespace-nowrap font-mono text-code">{l.key}</td>
                  <td className="td whitespace-nowrap">{l.created_at}</td>
                  <td className="td">{l.requester}</td>
                  <td className="td">{l.department}</td>
                  <td className="td">{l.description || l.item_code_raw}</td>
                  <td className="td whitespace-nowrap">
                    {l.quantity} {l.uom}
                  </td>
                  <td className="td whitespace-nowrap">{l.need_by}</td>
                  <td className="td">{l.urgency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab === "history" && (
        <div className="card text-body-sm">
          <div className="stagger divide-y divide-hairline-soft">
            {d.decisions.map((x, i) => (
              <div key={x.id} style={{ "--i": Math.min(i, 10) }} className="flex flex-wrap items-center gap-xs py-2">
                <StatusChip status={x.status} />
                <span>
                  {x.kind} <span className="font-mono">#{x.id}</span>: {x.decision} / {x.route} {x.supplier_id || ""} {x.unit_price || ""} {x.suggested?.join(";")}
                </span>
                <span className="text-muted">by {x.created_by} {x.comment && `“${x.comment}”`}</span>
              </div>
            ))}
          </div>
          <h3 className="h2 pt-lg">Audit log</h3>
          {d.audit.length === 0 && <p className="mt-2 text-muted">No actions yet.</p>}
          <div className="mt-2 divide-y divide-hairline-soft">
            {d.audit.map((a) => (
              <details key={a.id} className="group py-2">
                <summary className="cursor-pointer list-none text-body-sm transition-colors duration-100 hover:text-ink">
                  <Icon name="chevron-right" size={14} className="mr-1 inline transition-transform duration-150 group-open:rotate-90" />
                  <span className="font-mono text-code">{a.at.replace("T", " ").slice(0, 19)}</span> UTC · {a.who} ({a.role}) · {a.action} {a.comment && `· “${a.comment}”`}
                </summary>
                <div className="mt-2 grid gap-2 text-caption sm:grid-cols-2">
                  <pre className="overflow-auto rounded-md bg-surface-soft p-2 font-mono font-normal">before: {JSON.stringify(a.before, null, 1)}</pre>
                  <pre className="overflow-auto rounded-md bg-surface-soft p-2 font-mono font-normal">after: {JSON.stringify(a.after, null, 1)}</pre>
                </div>
              </details>
            ))}
          </div>
        </div>
      )}
      {confirming && (
        <Modal title="Approve" onClose={() => setConfirming(false)}>
          <p className="mb-md text-body-sm">
            {group.display
              ? `Approves ${group.display} with ${group.members.length} requirement(s).`
              : eff.decision === "PO"
                ? `Creates a PO to ${eff.supplier_id} for this requirement.`
                : `Creates a sourcing request (${eff.route}) for this requirement.`}
            {group.excluded_overridden > 0 && ` ${group.excluded_overridden} overridden requirement(s) are excluded.`}
          </p>
          <div className="flex justify-end gap-xs">
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button loading={busy} onClick={approve}>
              Approve
            </Button>
          </div>
        </Modal>
      )}
      {overriding && (
        <OverrideModal
          d={d}
          onClose={() => setOverriding(false)}
          onDone={() => {
            setOverriding(false);
            toast.success("Override saved. It is now the proposed decision; approve it when ready.");
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
  useErrorToast(error);
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

  const runOptions = [
    { value: "", label: "Latest batch run" },
    ...runs.map((r) => ({
      value: String(r.run_id),
      label: `R${r.run_id} ${r.kind} ${r.filename}`,
      hint: r.created_at.slice(0, 16).replace("T", " "),
    })),
  ];
  const routeOptions = ROUTES.map((r) => ({ value: r, label: r || "All routes" }));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: s || "All statuses" }));

  return (
    <div className="page-enter">
      <PageHeader
        title="Buyer workspace"
        subtitle="Review each routed requirement, see why the policy chose it, then approve or override."
        actions={
          data && (
            <span className="badge-pill">
              <AnimatedNumber value={pending} /> awaiting approval
            </span>
          )
        }
      />
      <NextAction>
        {selected ? "Review the why-panel, then Approve (or Override with a comment)." : `${pending} requirement(s) waiting for approval. Pick one to review.`}
      </NextAction>
      <div className="mb-md grid items-end gap-x-md sm:grid-cols-2 lg:grid-cols-4">
        <div className="mb-3">
          <Select
            label="Run"
            value={runId}
            onChange={(v) => {
              const next = new URLSearchParams();
              if (v) next.set("run", v);
              setParams(next);
            }}
            options={runOptions}
          />
        </div>
        <div className="mb-3">
          <Select label="Route" value={route} onChange={setRoute} options={routeOptions} />
        </div>
        <div className="mb-3">
          <Select label="Status" value={status} onChange={setStatus} options={statusOptions} />
        </div>
        {data?.run && (
          <span className="mb-3 pb-2 text-body-sm text-muted">
            <span className="font-mono">R{data.run.run_id}</span> · {data.run.filename} · {reqs.length} requirements shown
          </span>
        )}
      </div>
      {data && !data.run && <Alert kind="info">No runs yet. Upload a batch or raise a request in chat first.</Alert>}
      <div className="grid gap-md lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <div className="table-wrap max-h-[75vh] self-start">
          {data === null ? (
            <div className="p-lg">
              <SkeletonRows rows={6} cols={3} />
            </div>
          ) : reqs.length === 0 ? (
            <EmptyState glyph="inbox" title="Nothing to review" body="No requirements match this run and filters." />
          ) : (
            <table className="min-w-full">
              <thead>
                <tr>
                  <th className="th">Req</th>
                  <th className="th">Item / plant</th>
                  <th className="th">Value</th>
                  <th className="th">Route</th>
                </tr>
              </thead>
              <tbody className="stagger">
                {reqs.map((r, i) => (
                  <tr
                    key={r.id}
                    style={{ "--i": Math.min(i, 12) }}
                    onClick={() => select(r.id)}
                    className={`cursor-pointer transition-colors duration-100 hover:bg-surface-soft ${String(r.id) === selected ? "bg-surface-card" : ""}`}
                  >
                    <td className="td">
                      <span className="font-mono text-code text-ink">{r.group_id}</span>
                      <span className="block text-caption font-normal text-muted">{r.line_count} line(s)</span>
                    </td>
                    <td className="td">
                      <span className="font-mono text-code">{r.item_code}</span> {r.item_description}
                      <span className="block font-mono text-caption font-normal text-muted">
                        {r.plant} · {r.effective.supplier_id || r.effective.suggested.join(";")}
                      </span>
                    </td>
                    <td className="td whitespace-nowrap">{inr(r.value)}</td>
                    <td className="td">
                      <RouteChip route={r.effective.route} />
                      <div className="mt-1">
                        <StatusChip status={r.effective.status} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div>
          {selected ? (
            <Detail key={selected} id={selected} onChanged={load} />
          ) : (
            <div className="card">
              <EmptyState glyph="chevron-left" title="Select a requirement" body="Pick one from the list to see the why-panel, PR lines and audit trail." />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
