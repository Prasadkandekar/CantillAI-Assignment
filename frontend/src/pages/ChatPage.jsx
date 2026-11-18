import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import Badge from "../components/Badge.jsx";
import { useChatHistory } from "../chat/ChatHistoryContext.jsx";
import Button from "../components/Button.jsx";
import Icon from "../components/Icon.jsx";
import Select from "../components/Select.jsx";
import { SkeletonCard } from "../components/Skeleton.jsx";
import SpikeMark from "../components/SpikeMark.jsx";
import { useToast } from "../components/Toast.jsx";
import { RouteChip, useAsync } from "../components/ui.jsx";

const GREETING = {
  role: "assistant",
  text: "Hi! Tell me what you need, e.g. \"100 pairs of nitrile gloves for Chakan by Friday\".",
};

const SUGGESTIONS = [
  "100 pairs of nitrile gloves for Chakan by Friday",
  "50 litres of cutting oil for Pune next Monday",
  "Urgent: 10 safety helmets for Chakan tomorrow",
];

const URGENCY_OPTIONS = [
  { value: "Normal", label: "Normal" },
  { value: "Emergency", label: "Emergency" },
];

function Avatar() {
  return (
    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center text-primary">
      <SpikeMark size={22} />
    </span>
  );
}

function TypingIndicator() {
  return (
    <div className="flex animate-fade-in items-center gap-sm" role="status" aria-label="Assistant is typing">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center text-primary">
        <SpikeMark size={22} spinning />
      </span>
      <div className="flex items-center gap-1">
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-2 w-2 animate-type-dot rounded-pill bg-muted-soft" style={{ animationDelay: `${i * 160}ms` }} />
        ))}
      </div>
    </div>
  );
}

function ConfirmationCard({ card, busy, onConfirm, onEdit }) {
  const [editing, setEditing] = React.useState(false);
  const [fields, setFields] = React.useState({});
  React.useEffect(() => {
    setFields({ quantity: card.quantity, plant: card.plant, need_by: card.need_by, urgency: card.urgency });
    setEditing(false);
  }, [card]);
  return (
    <div className="animate-fade-up rounded-lg border border-hairline bg-surface-card p-lg">
      <h2 className="mb-md font-serif text-display-sm">Check your request</h2>
      <dl className="grid grid-cols-[7rem_1fr] items-center gap-x-md gap-y-sm text-body-sm">
        <dt className="text-muted">Item</dt>
        <dd>
          <span className="font-mono text-code">{card.item_code}</span> {card.description}
        </dd>
        <dt className="text-muted">Quantity</dt>
        <dd>
          {editing ? (
            <input className="input w-28" value={fields.quantity || ""} onChange={(e) => setFields({ ...fields, quantity: e.target.value })} aria-label="quantity" />
          ) : (
            card.quantity
          )}{" "}
          {card.uom}
        </dd>
        <dt className="text-muted">Plant</dt>
        <dd>
          {editing ? (
            <input className="input w-28" value={fields.plant || ""} onChange={(e) => setFields({ ...fields, plant: e.target.value })} aria-label="plant" />
          ) : (
            card.plant
          )}
        </dd>
        <dt className="text-muted">Need by</dt>
        <dd>
          {editing ? (
            <input type="date" className="input w-44" value={fields.need_by || ""} onChange={(e) => setFields({ ...fields, need_by: e.target.value })} aria-label="need by" />
          ) : (
            card.need_by_display
          )}
        </dd>
        <dt className="text-muted">Urgency</dt>
        <dd>
          {editing ? (
            <Select
              className="w-44"
              aria-label="urgency"
              value={fields.urgency || "Normal"}
              onChange={(v) => setFields({ ...fields, urgency: v })}
              options={URGENCY_OPTIONS}
            />
          ) : (
            card.urgency
          )}
        </dd>
        {card.item_code === "NEW" && (
          <>
            <dt className="text-muted">Estimate</dt>
            <dd>{card.estimate ? `₹${card.estimate} per unit` : "not given"}</dd>
          </>
        )}
      </dl>
      <div className="mt-lg flex gap-xs">
        {editing ? (
          <Button disabled={busy} onClick={() => onEdit(fields)}>
            Save changes
          </Button>
        ) : (
          <Button disabled={busy} onClick={onConfirm}>
            Confirm
          </Button>
        )}
        <Button variant="secondary" disabled={busy} onClick={() => setEditing(!editing)}>
          {editing ? "Cancel edit" : "Edit"}
        </Button>
      </div>
    </div>
  );
}

function ResultCard({ result }) {
  const row = result.row || {};
  return (
    <div className="animate-fade-up rounded-lg border border-hairline bg-canvas p-lg">
      <div className="mb-xs flex items-center gap-xs">
        <Badge tone="success" dot>
          Created
        </Badge>
        <h2 className="font-serif text-display-sm">{result.pr_no}</h2>
      </div>
      <p className="mb-sm text-body-sm text-body">{result.decision_summary}</p>
      <div className="mb-md flex items-center gap-xs text-body-sm">
        <RouteChip route={row.route} />
        {row.group_id && <span className="text-muted">requirement {row.group_id}</span>}
      </div>
      {result.requirement && (
        <Link className="btn-primary" to={`/workspace?run=${result.requirement.run_id}&req=${result.requirement.id}`}>
          Open in buyer workspace
          <Icon name="arrow-right" size={16} />
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
  const [convId, setConvId] = React.useState(null);
  const [loadingConv, setLoadingConv] = React.useState(false);
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { upsert } = useChatHistory();
  const justCreated = React.useRef(null);
  const viewToken = React.useRef(0); // bumped whenever the visible chat is replaced; stale responses are dropped
  const { busy, error, setError, run } = useAsync();
  const toast = useToast();
  const endRef = React.useRef(null);
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
    return undefined;
  }, [messages, card, result, busy]);

  React.useEffect(() => {
    if (error) toast.error(error);
    return undefined;
  }, [error]); // eslint-disable-line react-hooks/exhaustive-deps

  const resetChat = React.useCallback(() => {
    viewToken.current += 1;
    setSessionId(null);
    setConvId(null);
    setMessages([GREETING]);
    setCard(null);
    setCandidates([]);
    setResult(null);
    setError("");
  }, [setError]);

  // Follow the route: /chat is a new chat, /chat/:id reopens a saved one (unless this page just created it).
  React.useEffect(() => {
    if (!conversationId) {
      justCreated.current = null;
      setLoadingConv(false);
      resetChat();
      return undefined;
    }
    if (String(justCreated.current) === conversationId) return undefined;
    let alive = true;
    setLoadingConv(true);
    resetChat();
    api
      .get(`/chat/conversations/${conversationId}`)
      .then((conv) => {
        if (!alive) return;
        const rows = conv.messages || [];
        const last = rows[rows.length - 1];
        const lastPayload = last?.role === "assistant" ? last.payload || {} : {};
        setConvId(conv.id);
        setSessionId(conv.session_id);
        setMessages([GREETING, ...rows.map((r) => ({ role: r.role, text: r.content }))]);
        setCard(conv.stage === "awaiting_confirmation" ? lastPayload.card || null : null);
        setCandidates(lastPayload.candidates || []);
        setResult(conv.stage === "created" ? lastPayload.result || null : null);
        setLoadingConv(false);
      })
      .catch((e) => {
        if (!alive) return;
        setLoadingConv(false);
        toast.error(e.message || "Could not open chat");
        navigate("/chat", { replace: true });
      });
    return () => {
      alive = false;
    };
  }, [conversationId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handle = (res, token) => {
    if (!res) return;
    if (res.conversation) upsert(res.conversation);
    if (token !== viewToken.current) return;
    if (res.conversation_id && res.conversation_id !== convId) {
      setConvId(res.conversation_id);
      if (String(res.conversation_id) !== conversationId) {
        justCreated.current = res.conversation_id;
        navigate(`/chat/${res.conversation_id}`, { replace: true });
      }
    }
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
    const token = viewToken.current;
    run(async () => handle(await api.post("/chat", { session_id: result ? null : sessionId, message: msg, conversation_id: convId }), token));
  };

  const select = (code) =>
    run(async () => {
      const token = viewToken.current;
      setMessages((m) => [...m, { role: "user", text: code }]);
      handle(await api.post("/chat", { session_id: sessionId, action: "select", choice: code, conversation_id: convId }), token);
    });

  const edit = (fields) => {
    const token = viewToken.current;
    return run(async () => handle(await api.post("/chat", { session_id: sessionId, action: "edit", fields, conversation_id: convId }), token));
  };

  const confirm = () =>
    run(async () => {
      const token = viewToken.current;
      const res = await api.post(`/chat/${sessionId}/confirm`);
      if (res.conversation) upsert(res.conversation);
      if (token !== viewToken.current) return;
      setCard(null);
      setResult(res);
      setMessages((m) => [...m, { role: "assistant", text: res.reply }]);
      toast.success(`Created ${res.pr_no}`);
    });

  const restart = () => {
    justCreated.current = null;
    resetChat();
    navigate("/chat");
  };

  const empty = messages.length === 1 && !card && !result && !busy && !loadingConv;

  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] w-full max-w-[768px] flex-col">
      <div className="mb-md flex justify-end">
        <Button variant="ghost" onClick={restart} icon="plus">
          New request
        </Button>
      </div>

      <div className="flex-1 space-y-lg pb-lg">
        {loadingConv ? (
          <SkeletonCard />
        ) : empty ? (
          <div className="flex animate-fade-up flex-col items-center pt-xxl text-center">
            <SpikeMark size={40} className="mb-lg text-primary" />
            <h1 className="display-md">What do you need to buy?</h1>
            <p className="mt-sm max-w-md text-body-md text-muted">{GREETING.text}</p>
            <div className="mt-xl flex flex-wrap justify-center gap-xs">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="rounded-pill border border-hairline bg-canvas px-md py-xs text-body-sm text-body transition-colors duration-150 hover:bg-surface-card focus-visible:ring-[3px] focus-visible:ring-primary/15"
                  onClick={() => {
                    setText(s);
                    inputRef.current?.focus();
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex animate-fade-up justify-end">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-surface-card px-md py-sm text-body-md text-ink">{m.text}</div>
              </div>
            ) : (
              <div key={i} className="flex animate-fade-up items-start gap-sm">
                <Avatar />
                <div className="min-w-0 flex-1 whitespace-pre-wrap pt-0.5 text-body-md text-ink">{m.text}</div>
              </div>
            )
          )
        )}
        {!loadingConv && candidates.length > 0 && (
          <div className="flex animate-fade-up flex-wrap gap-xs pl-[40px]">
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
        {busy && <TypingIndicator />}
        {!loadingConv && card && <ConfirmationCard card={card} busy={busy} onConfirm={confirm} onEdit={edit} />}
        {!loadingConv && result && <ResultCard result={result} />}
        <div ref={endRef} />
      </div>

      <form onSubmit={send} className="sticky bottom-0 -mx-lg bg-canvas px-lg pb-md pt-sm">
        <div className="flex items-center gap-xs rounded-xl border border-hairline bg-canvas py-xs pl-md pr-xs shadow-card focus-within:border-primary focus-within:ring-[3px] focus-within:ring-primary/15">
          <input
            ref={inputRef}
            className="h-10 min-w-0 flex-1 bg-transparent text-body-md text-ink placeholder:text-muted-soft focus:outline-none"
            value={text}
            maxLength={2000}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type your message"
            aria-label="message"
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={busy || !text.trim()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-pill bg-primary text-on-primary transition-colors duration-150 hover:bg-primary-active focus-visible:ring-[3px] focus-visible:ring-primary/15 disabled:cursor-not-allowed disabled:bg-primary-disabled disabled:text-muted"
          >
            {busy ? <SpikeMark size={16} spinning /> : <Icon name="send" size={18} />}
          </button>
        </div>
        <p className="mt-xs text-center text-caption text-muted-soft">Dates like "by Friday" or "next Monday" are worked out in IST.</p>
      </form>
    </div>
  );
}
