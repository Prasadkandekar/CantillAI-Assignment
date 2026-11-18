import React from "react";
import { api } from "../api.js";
import { Alert, Field, NextAction, RouteChip, StatusChip, useAsync, useErrorToast } from "../components/ui.jsx";
import AnimatedNumber from "../components/AnimatedNumber.jsx";
import Button from "../components/Button.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import { SkeletonRows } from "../components/Skeleton.jsx";
import StatusDot from "../components/StatusDot.jsx";
import Tabs from "../components/Tabs.jsx";
import { useToast } from "../components/Toast.jsx";

function NewDraft({ onCreated }) {
  const [file, setFile] = React.useState(null);
  const [message, setMessage] = React.useState("");
  const [eff, setEff] = React.useState("");
  const { busy, error, run } = useAsync();
  const toast = useToast();
  useErrorToast(error);
  const created = (d) => {
    toast.success(`Draft v${d.version_label} created.`);
    onCreated(d);
  };
  const upload = () =>
    run(async () => {
      const form = new FormData();
      form.append("file", file);
      if (eff) form.append("effective_from", eff);
      created(await api.upload("/policy/drafts/upload", form));
    });
  const fromChat = () =>
    run(async () => created(await api.post("/policy/drafts/from-chat", { message, effective_from: eff || null })));
  return (
    <div className="card">
      <h2 className="h2 mb-md">New amendment draft</h2>
      <div className="grid items-start gap-x-md md:grid-cols-2">
        <div>
          <span className="label">Amendment document (PDF, DOCX, TXT)</span>
          <label className="flex h-10 cursor-pointer items-center gap-2 rounded-md border border-hairline bg-canvas px-[14px] text-body-sm transition-colors duration-150 hover:border-primary hover:bg-surface-soft focus-within:border-primary focus-within:ring-[3px] focus-within:ring-primary/15">
            <Icon name="upload" size={16} className="shrink-0 text-primary" />
            <span className={`truncate ${file ? "font-mono text-code text-ink" : "text-muted-soft"}`}>{file ? file.name : "Choose a file"}</span>
            <input type="file" className="sr-only" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files[0] || null)} />
          </label>
          <span className="mb-3 mt-1 block text-caption font-normal text-muted">The reader extracts the changed rules into a draft.</span>
        </div>
        <Field label="Effective from (if not in the document)" hint="Leave empty to use the date in the document.">
          <input type="date" className="input" value={eff} onChange={(e) => setEff(e.target.value)} />
        </Field>
      </div>
      <Button disabled={!file} loading={busy} onClick={upload}>
        {busy ? "Reading…" : "Upload and draft"}
      </Button>
      <div className="mt-lg flex flex-wrap items-end gap-xs">
        <Field label="…or describe the change" className="mb-0 min-w-[16rem] flex-1">
          <input
            className="input"
            value={message}
            placeholder="e.g. Raise the spot limit to ₹3 lakh from 1 December 2026"
            onChange={(e) => setMessage(e.target.value)}
          />
        </Field>
        <Button variant="secondary" disabled={!message.trim() || busy} onClick={fromChat}>
          Draft from message
        </Button>
      </div>
    </div>
  );
}

function DryRun({ result }) {
  if (!result) return null;
  return (
    <div className="card animate-fade-up">
      <h3 className="h2 mb-1">Impact on the latest batch (<span className="font-mono text-code">{result.filename}</span>)</h3>
      <p className="mb-md font-serif text-title-lg text-ink">{result.headline}</p>
      <div className="mb-md flex flex-wrap gap-md text-body-sm">
        {Object.entries(result.route_deltas).map(([r, n]) => (
          <span key={r} className="flex items-center gap-xs">
            <RouteChip route={r} /> <span className="font-medium text-ink">{n > 0 ? "+" : n < 0 ? "−" : ""}<AnimatedNumber value={Math.abs(n)} /></span>
          </span>
        ))}
      </div>
      {result.changes.length > 0 && (
        <div className="table-wrap max-h-80">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="th">PR line</th>
                <th className="th">Before</th>
                <th className="th">After</th>
              </tr>
            </thead>
            <tbody>
              {result.changes.map((c) => (
                <tr key={`${c.pr_no}/${c.pr_line}`} className="hover:bg-surface-soft">
                  <td className="td whitespace-nowrap font-mono text-code">
                    {c.pr_no}/{c.pr_line}
                  </td>
                  {[c.before, c.after].map((x, i) => (
                    <td key={i} className="td text-caption font-normal">
                      <RouteChip route={x.route} /> <span className="font-mono">{x.supplier_id || x.suggested_supplier_ids} {x.unit_price}</span> · value {x.group_value_inr} · <span className="font-mono">{x.group_id}</span> · v
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
  const toast = useToast();
  useErrorToast(error);
  React.useEffect(() => {
    setEff(draft.effective_from || "");
    setJsonText(JSON.stringify(draft.document, null, 2));
    setDry(null);
  }, [draft]);
  const isDraft = draft.status === "DRAFT";
  const errors = draft.validation.errors;
  const warnings = draft.validation.warnings;

  const saveDate = () =>
    run(async () => {
      onChange(await api.put(`/policy/${draft.id}`, { effective_from: eff }));
      toast.success("Effective date saved.");
    });
  const saveJson = () => {
    let doc;
    try {
      doc = JSON.parse(jsonText);
      setJsonError("");
    } catch (e) {
      setJsonError(`Not valid JSON: ${e.message}`);
      return;
    }
    run(async () => {
      onChange(await api.put(`/policy/${draft.id}`, { document: doc }));
      toast.success("JSON saved and re-validated.");
    });
  };
  const dryRun = () => run(async () => setDry(await api.post(`/policy/${draft.id}/dry-run`)));
  const approve = () =>
    run(async () => {
      onChange(await api.post(`/policy/${draft.id}/approve`, { effective_from: eff || null }));
      toast.success(`Policy v${draft.version_label} approved and activated.`);
    });
  const discard = () =>
    run(async () => {
      onChange(await api.post(`/policy/${draft.id}/discard`));
      toast.info(`Draft v${draft.version_label} discarded.`);
    });

  return (
    <div className="space-y-md animate-fade-up">
      <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-md">
          <h2 className="display-sm flex flex-wrap items-center gap-sm">
            v{draft.version_label} <StatusChip status={draft.status} />
          </h2>
          {isDraft && (
            <div className="flex flex-wrap items-end gap-xs">
              <Field label="Effective from" hint={draft.needs_effective_date ? draft.question : ""} error={!eff && draft.needs_effective_date ? "Required to approve" : ""} className="mb-0">
                <input type="date" className={`input ${!eff && draft.needs_effective_date ? "input-error" : ""}`} value={eff} onChange={(e) => setEff(e.target.value)} />
              </Field>
              <Button variant="secondary" disabled={busy || !eff || eff === draft.effective_from} onClick={saveDate}>
                Set date
              </Button>
              <Button variant="secondary" disabled={busy} onClick={dryRun}>
                Dry run
              </Button>
              <Button disabled={busy || errors.length > 0 || !eff} onClick={approve} title="Needs no errors and an effective date">
                Approve and activate
              </Button>
              <Button variant="danger" disabled={busy} onClick={discard}>
                Discard
              </Button>
            </div>
          )}
        </div>
        {draft.reader && (
          <p className="mt-2 text-caption font-normal text-muted">
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
      </div>
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "summary", label: "What changes" },
          { id: "diff", label: "Structural diff" },
          { id: "json", label: isDraft ? "Edit JSON" : "JSON" },
        ]}
      />
      {tab === "summary" && (
        <div className="card">
          {draft.diff.bullets.length ? (
            <ul className="stagger list-disc space-y-1 pl-5 text-body-sm">
              {draft.diff.bullets.map((b, i) => (
                <li key={i} style={{ "--i": Math.min(i, 10) }}>{b}</li>
              ))}
            </ul>
          ) : (
            <EmptyState glyph="check" title="No differences" body="This version matches its base version." />
          )}
        </div>
      )}
      {tab === "diff" && (
        <pre className="card-dark max-h-[60vh] overflow-auto font-mono text-code">{JSON.stringify(draft.diff.structural, null, 2)}</pre>
      )}
      {tab === "json" && (
        <div className="card">
          <textarea
            className={`input h-[60vh] w-full font-mono text-code ${jsonError ? "input-error" : ""}`}
            value={jsonText}
            readOnly={!isDraft}
            spellCheck={false}
            onChange={(e) => setJsonText(e.target.value)}
          />
          {jsonError && <span className="field-error">{jsonError}</span>}
          {isDraft && (
            <Button variant="secondary" className="mt-md" disabled={busy} onClick={saveJson}>
              Save JSON and re-validate
            </Button>
          )}
        </div>
      )}
      <DryRun result={dry} />
    </div>
  );
}

export default function PolicyPage() {
  const [versions, setVersions] = React.useState(null);
  const [current, setCurrent] = React.useState(null);
  const { error, run } = useAsync();
  useErrorToast(error);
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
  const active = (versions || []).find((v) => v.status === "ACTIVE");
  return (
    <div className="page-enter">
      <PageHeader
        title="Policy versions"
        subtitle="Review amendments as drafts, dry-run them against the latest batch, then activate."
        actions={
          active && (
            <span className="badge-pill">
              <StatusDot tone="success" pulse /> Active <span className="font-mono">v{active.version_label}</span>
            </span>
          )
        }
      />
      <NextAction>{next}</NextAction>
      <div className="grid gap-md lg:grid-cols-[20rem_minmax(0,1fr)]">
        <div className="card self-start p-0">
          {versions === null ? (
            <div className="p-lg">
              <SkeletonRows rows={4} cols={3} />
            </div>
          ) : versions.length === 0 ? (
            <EmptyState glyph="shield" title="No versions" body="Policy versions will appear here." />
          ) : (
            <ul className="stagger divide-y divide-hairline-soft">
              {versions.map((v, i) => (
                <li key={v.id} style={{ "--i": Math.min(i, 10) }}>
                  <button
                    className={`flex w-full items-center gap-sm px-md py-sm text-left transition-colors duration-100 hover:bg-surface-soft focus-visible:ring-[3px] focus-visible:ring-primary/15 ${current?.id === v.id ? "bg-surface-card" : ""}`}
                    onClick={() => open(v.id)}
                  >
                    <span className="font-mono text-code font-medium text-ink">v{v.version_label}</span>
                    <StatusChip status={v.status} />
                    <span className="ml-auto text-caption font-normal text-muted">{v.effective_from ? `from ${v.effective_from}` : "no date"}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="space-y-md">
          <NewDraft onCreated={changed} />
          {current && <DraftView draft={current} onChange={changed} />}
        </div>
      </div>
    </div>
  );
}
