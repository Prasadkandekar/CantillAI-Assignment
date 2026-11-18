import React from "react";
import { api } from "../api.js";
import { Alert, Field, NextAction, RouteChip, StatusChip, useAsync } from "../components/ui.jsx";

function NewDraft({ onCreated }) {
  const [file, setFile] = React.useState(null);
  const [message, setMessage] = React.useState("");
  const [eff, setEff] = React.useState("");
  const { busy, error, run } = useAsync();
  const upload = () =>
    run(async () => {
      const form = new FormData();
      form.append("file", file);
      if (eff) form.append("effective_from", eff);
      onCreated(await api.upload("/policy/drafts/upload", form));
    });
  const fromChat = () =>
    run(async () => onCreated(await api.post("/policy/drafts/from-chat", { message, effective_from: eff || null })));
  return (
    <div className="card">
      <h2 className="h2 mb-2">New amendment draft</h2>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Amendment document (PDF, DOCX, TXT)">
          <input type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files[0] || null)} />
        </Field>
        <Field label="Effective from (if not in the document)">
          <input type="date" className="input" value={eff} onChange={(e) => setEff(e.target.value)} />
        </Field>
        <button className="btn-primary" disabled={!file || busy} onClick={upload}>
          {busy ? "Reading…" : "Upload and draft"}
        </button>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <Field label="…or describe the change">
          <input
            className="input w-[32rem] max-w-full"
            value={message}
            placeholder="e.g. Raise the spot limit to ₹3 lakh from 1 December 2026"
            onChange={(e) => setMessage(e.target.value)}
          />
        </Field>
        <button className="btn-secondary" disabled={!message.trim() || busy} onClick={fromChat}>
          Draft from message
        </button>
      </div>
      <Alert>{error}</Alert>
    </div>
  );
}

function DryRun({ result }) {
  if (!result) return null;
  return (
    <div className="card">
      <h3 className="h2 mb-1">Impact on the latest batch ({result.filename})</h3>
      <p className="mb-2 text-lg font-semibold">{result.headline}</p>
      <div className="mb-2 flex flex-wrap gap-2 text-sm">
        {Object.entries(result.route_deltas).map(([r, n]) => (
          <span key={r}>
            <RouteChip route={r} /> {n > 0 ? `+${n}` : n}
          </span>
        ))}
      </div>
      {result.changes.length > 0 && (
        <div className="max-h-80 overflow-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                <th className="th">PR line</th>
                <th className="th">Before</th>
                <th className="th">After</th>
              </tr>
            </thead>
            <tbody>
              {result.changes.map((c) => (
                <tr key={`${c.pr_no}/${c.pr_line}`} className="border-t">
                  <td className="td">
                    {c.pr_no}/{c.pr_line}
                  </td>
                  {[c.before, c.after].map((x, i) => (
                    <td key={i} className="td text-xs">
                      <RouteChip route={x.route} /> {x.supplier_id || x.suggested_supplier_ids} {x.unit_price} · value {x.group_value_inr} · {x.group_id} · v
                      {x.policy_version}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DraftView({ draft, onChange }) {
  const [tab, setTab] = React.useState("summary");
  const [eff, setEff] = React.useState(draft.effective_from || "");
  const [jsonText, setJsonText] = React.useState(JSON.stringify(draft.document, null, 2));
  const [jsonError, setJsonError] = React.useState("");
  const [dry, setDry] = React.useState(null);
  const { busy, error, run } = useAsync();
  React.useEffect(() => {
    setEff(draft.effective_from || "");
    setJsonText(JSON.stringify(draft.document, null, 2));
    setDry(null);
  }, [draft]);
  const isDraft = draft.status === "DRAFT";
  const errors = draft.validation.errors;
  const warnings = draft.validation.warnings;

  const saveDate = () => run(async () => onChange(await api.put(`/policy/${draft.id}`, { effective_from: eff })));
  const saveJson = () => {
    let doc;
    try {
      doc = JSON.parse(jsonText);
      setJsonError("");
    } catch (e) {
      setJsonError(`Not valid JSON: ${e.message}`);
      return;
    }
    run(async () => onChange(await api.put(`/policy/${draft.id}`, { document: doc })));
  };
  const dryRun = () => run(async () => setDry(await api.post(`/policy/${draft.id}/dry-run`)));
  const approve = () => run(async () => onChange(await api.post(`/policy/${draft.id}/approve`, { effective_from: eff || null })));
  const discard = () => run(async () => onChange(await api.post(`/policy/${draft.id}/discard`)));

  return (
    <div className="space-y-3">
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="h1">
            v{draft.version_label} <StatusChip status={draft.status} />
          </h2>
          {isDraft && (
            <div className="flex items-end gap-2">
              <Field label="Effective from" hint={draft.needs_effective_date ? draft.question : ""}>
                <input type="date" className="input" value={eff} onChange={(e) => setEff(e.target.value)} />
              </Field>
              <button className="btn-secondary mb-2" disabled={busy || !eff || eff === draft.effective_from} onClick={saveDate}>
                Set date
              </button>
              <button className="btn-secondary mb-2" disabled={busy} onClick={dryRun}>
                Dry run
              </button>
              <button className="btn-primary mb-2" disabled={busy || errors.length > 0 || !eff} onClick={approve} title="Needs no errors and an effective date">
                Approve and activate
              </button>
              <button className="btn-danger mb-2" disabled={busy} onClick={discard}>
                Discard
              </button>
            </div>
          )}
        </div>
        {draft.reader && (
          <p className="text-xs text-slate-500">
            Read by {draft.reader.mode === "llm" ? "AI (OpenRouter)" : "the rule-based reader"}
            {draft.reader.llm_error ? ` (AI unavailable: ${draft.reader.llm_error})` : ""}
            {draft.source_filename ? ` from ${draft.source_filename}` : ""}.
          </p>
        )}
        {draft.reader?.unrecognised?.length > 0 && (
          <Alert kind="warning">Not understood (edit the JSON if these matter):{"\n"}• {draft.reader.unrecognised.join("\n• ")}</Alert>
        )}
        {errors.length > 0 && <Alert>Validation errors:{"\n"}{errors.map((e) => `${e.path}: ${e.message}`).join("\n")}</Alert>}
        {warnings.length > 0 && <Alert kind="warning">Warnings:{"\n"}{warnings.map((e) => `${e.path}: ${e.message}`).join("\n")}</Alert>}
        <Alert>{error}</Alert>
      </div>
      <div className="flex gap-1">
        {[["summary", "What changes"], ["diff", "Structural diff"], ["json", isDraft ? "Edit JSON" : "JSON"]].map(([k, l]) => (
          <button key={k} className={tab === k ? "btn-primary" : "btn-secondary"} onClick={() => setTab(k)}>
            {l}
          </button>
        ))}
      </div>
      {tab === "summary" && (
        <div className="card">
          {draft.diff.bullets.length ? (
            <ul className="list-disc pl-5 text-sm">
              {draft.diff.bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No differences from the base version.</p>
          )}
        </div>
      )}
      {tab === "diff" && (
        <pre className="card max-h-[60vh] overflow-auto text-xs">{JSON.stringify(draft.diff.structural, null, 2)}</pre>
      )}
      {tab === "json" && (
        <div className="card">
          <textarea
            className="input h-[60vh] w-full font-mono text-xs"
            value={jsonText}
            readOnly={!isDraft}
            onChange={(e) => setJsonText(e.target.value)}
          />
          {jsonError && <Alert>{jsonError}</Alert>}
          {isDraft && (
            <button className="btn-secondary mt-2" disabled={busy} onClick={saveJson}>
              Save JSON and re-validate
            </button>
          )}
        </div>
      )}
      <DryRun result={dry} />
    </div>
  );
}

export default function PolicyPage() {
  const [versions, setVersions] = React.useState([]);
  const [current, setCurrent] = React.useState(null);
  const { error, run } = useAsync();
  const loadList = React.useCallback(() => run(async () => setVersions(await api.get("/policy"))), [run]);
  React.useEffect(() => {
    loadList();
  }, [loadList]);
  const open = (id) => run(async () => setCurrent(await api.get(`/policy/${id}`)));
  const changed = (d) => {
    setCurrent(d);
    loadList();
  };
  const next =
    current?.status === "DRAFT"
      ? current.validation.errors.length
        ? "Fix the validation errors (Edit JSON), then approve."
        : current.effective_from
          ? "Check the summary and dry run, then Approve and activate."
          : "Set the effective date, then approve."
      : "Upload an amendment or describe a change to create a draft.";
  return (
    <div>
      <h1 className="h1 mb-1">Policy versions</h1>
      <NextAction>{next}</NextAction>
      <Alert>{error}</Alert>
      <div className="grid gap-3 lg:grid-cols-[18rem_1fr]">
        <div className="card p-0">
          <table className="min-w-full">
            <tbody>
              {versions.map((v) => (
                <tr key={v.id} className={`cursor-pointer border-t hover:bg-indigo-50 ${current?.id === v.id ? "bg-indigo-100" : ""}`} onClick={() => open(v.id)}>
                  <td className="td font-semibold">v{v.version_label}</td>
                  <td className="td">
                    <StatusChip status={v.status} />
                  </td>
                  <td className="td text-xs">{v.effective_from ? `from ${v.effective_from}` : "no date"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="space-y-3">
          <NewDraft onCreated={changed} />
          {current && <DraftView draft={current} onChange={changed} />}
        </div>
      </div>
    </div>
  );
}
