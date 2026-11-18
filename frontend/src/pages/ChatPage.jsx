import React from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Alert, Field, NextAction, RouteChip, useAsync } from "../components/ui.jsx";

const GREETING = {
  role: "assistant",
  text: "Hi! Tell me what you need, e.g. \"100 pairs of nitrile gloves for Chakan by Friday\".",
};

function ConfirmationCard({ card, busy, onConfirm, onEdit }) {
  const [editing, setEditing] = React.useState(false);
  const [fields, setFields] = React.useState({});
  React.useEffect(() => {
    setFields({ quantity: card.quantity, plant: card.plant, need_by: card.need_by, urgency: card.urgency });
    setEditing(false);
  }, [card]);
  return (
    <div className="card border-indigo-300">
      <h2 className="h2 mb-2">Check your request</h2>
      <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
        <dt className="text-slate-500">Item</dt>
        <dd>
          <span className="font-mono">{card.item_code}</span> {card.description}
        </dd>
        <dt className="text-slate-500">Quantity</dt>
        <dd>
          {editing ? (
            <input className="input w-24" value={fields.quantity || ""} onChange={(e) => setFields({ ...fields, quantity: e.target.value })} />
          ) : (
            card.quantity
          )}{" "}
          {card.uom}
        </dd>
        <dt className="text-slate-500">Plant</dt>
        <dd>
          {editing ? (
            <input className="input w-24" value={fields.plant || ""} onChange={(e) => setFields({ ...fields, plant: e.target.value })} />
          ) : (
            card.plant
          )}
        </dd>
        <dt className="text-slate-500">Need by</dt>
        <dd>
          {editing ? (
            <input type="date" className="input" value={fields.need_by || ""} onChange={(e) => setFields({ ...fields, need_by: e.target.value })} />
          ) : (
            card.need_by_display
          )}
        </dd>
        <dt className="text-slate-500">Urgency</dt>
        <dd>
          {editing ? (
            <select className="input" value={fields.urgency || ""} onChange={(e) => setFields({ ...fields, urgency: e.target.value })}>
              <option>Normal</option>
              <option>Emergency</option>
            </select>
          ) : (
            card.urgency
          )}
        </dd>
        {card.item_code === "NEW" && (
          <>
            <dt className="text-slate-500">Estimate</dt>
            <dd>{card.estimate ? `₹${card.estimate} per unit` : "not given"}</dd>
          </>
        )}
      </dl>
      <div className="mt-3 flex gap-2">
        {editing ? (
          <button className="btn-primary" disabled={busy} onClick={() => onEdit(fields)}>
            Save changes
          </button>
        ) : (
          <button className="btn-primary" disabled={busy} onClick={onConfirm}>
            Confirm
          </button>
        )}
        <button className="btn-secondary" disabled={busy} onClick={() => setEditing(!editing)}>
          {editing ? "Cancel edit" : "Edit"}
        </button>
      </div>
    </div>
  );
}

function ResultCard({ result }) {
  const row = result.row || {};
  return (
    <div className="card border-emerald-300">
      <h2 className="h2 mb-1">Created {result.pr_no}</h2>
      <p className="mb-2 text-sm">{result.decision_summary}</p>
      <div className="mb-2 flex items-center gap-2 text-sm">
        <RouteChip route={row.route} />
        {row.group_id && <span className="text-slate-500">requirement {row.group_id}</span>}
      </div>
      {result.requirement && (
        <Link className="btn-primary" to={`/workspace?run=${result.requirement.run_id}&req=${result.requirement.id}`}>
          Open in buyer workspace
        </Link>
      )}
    </div>
  );
}

export default function ChatPage() {
  const [sessionId, setSessionId] = React.useState(null);
  const [messages, setMessages] = React.useState([GREETING]);
  const [text, setText] = React.useState("");
  const [card, setCard] = React.useState(null);
  const [candidates, setCandidates] = React.useState([]);
  const [result, setResult] = React.useState(null);
  const { busy, error, setError, run } = useAsync();
  const endRef = React.useRef(null);
  React.useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [messages, card, result]);

  const handle = (res) => {
    if (!res) return;
    setSessionId(res.session_id);
    setMessages((m) => [...m, { role: "assistant", text: res.reply }]);
    setCard(res.card || null);
    setCandidates(res.candidates || []);
    if (res.result) setResult(res.result);
  };

  const send = (e) => {
    e?.preventDefault();
    const msg = text.trim();
    if (!msg) return;
    if (result) {
      setResult(null);
      setSessionId(null);
    }
    setMessages((m) => [...m, { role: "user", text: msg }]);
    setText("");
    run(async () => handle(await api.post("/chat", { session_id: result ? null : sessionId, message: msg })));
  };

  const select = (code) =>
    run(async () => {
      setMessages((m) => [...m, { role: "user", text: code }]);
      handle(await api.post("/chat", { session_id: sessionId, action: "select", choice: code }));
    });

  const edit = (fields) => run(async () => handle(await api.post("/chat", { session_id: sessionId, action: "edit", fields })));

  const confirm = () =>
    run(async () => {
      const res = await api.post(`/chat/${sessionId}/confirm`);
      setCard(null);
      setResult(res);
      setMessages((m) => [...m, { role: "assistant", text: res.reply }]);
    });

  const restart = () => {
    setSessionId(null);
    setMessages([GREETING]);
    setCard(null);
    setCandidates([]);
    setResult(null);
    setError("");
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-2 flex items-center justify-between">
        <h1 className="h1">Raise a purchase request</h1>
        <button className="btn-secondary" onClick={restart}>
          New request
        </button>
      </div>
      <NextAction>
        {card ? "Check the card and press Confirm." : result ? "Done. Open it in the workspace or start a new request." : "Describe what you need and press Send."}
      </NextAction>
      <div className="card mb-3 max-h-[55vh] space-y-2 overflow-auto">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
                m.role === "user" ? "bg-indigo-600 text-white" : "bg-slate-100"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
        {candidates.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {candidates.map((c, i) => (
              <button key={c.item_code} className="btn-secondary" disabled={busy} onClick={() => select(c.item_code)}>
                {i + 1}. {c.item_code} {c.description} ({c.uom})
              </button>
            ))}
            <button className="btn-secondary" disabled={busy} onClick={() => select("none")}>
              None of these
            </button>
          </div>
        )}
        <div ref={endRef} />
      </div>
      {card && <ConfirmationCard card={card} busy={busy} onConfirm={confirm} onEdit={edit} />}
      {result && <ResultCard result={result} />}
      <Alert>{error}</Alert>
      <form onSubmit={send} className="mt-3 flex gap-2">
        <Field label="" hint="Dates like 'by Friday' or 'next Monday' are worked out in IST.">
          <input
            className="input w-[36rem] max-w-full"
            value={text}
            maxLength={2000}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type your message"
            aria-label="message"
          />
        </Field>
        <div>
          <button className={card ? "btn-secondary" : "btn-primary"} disabled={busy || !text.trim()} type="submit">
            {busy ? "…" : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}
