import React from "react";
import { createPortal } from "react-dom";
import { NavLink, useMatch, useNavigate } from "react-router-dom";
import { useChatHistory } from "../chat/ChatHistoryContext.jsx";
import Dropdown, { DropdownItem } from "./Dropdown.jsx";
import Icon from "./Icon.jsx";
import { Skeleton } from "./Skeleton.jsx";
import { Modal } from "./ui.jsx";

const GROUPS = ["Today", "Yesterday", "Previous 7 days", "Older"];

// Groups conversations (already newest first) by local calendar day of updated_at.
export function groupConversations(list, now = new Date()) {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86400000;
  const buckets = Object.fromEntries(GROUPS.map((g) => [g, []]));
  list.forEach((c) => {
    const t = new Date(c.updated_at).getTime();
    const g = t >= startOfToday ? "Today" : t >= startOfToday - day ? "Yesterday" : t >= startOfToday - 7 * day ? "Previous 7 days" : "Older";
    buckets[g].push(c);
  });
  return GROUPS.filter((g) => buckets[g].length).map((g) => ({ name: g, items: buckets[g] }));
}

function RenameInput({ initial, onSave, onCancel }) {
  const [value, setValue] = React.useState(initial);
  const done = React.useRef(false);
  const finish = (save) => {
    if (done.current) return;
    done.current = true;
    const v = value.trim();
    if (save && v && v !== initial) onSave(v);
    else onCancel();
  };
  return (
    <input
      className="input h-8"
      value={value}
      maxLength={120}
      autoFocus
      aria-label="Chat title"
      onChange={(e) => setValue(e.target.value)}
      onFocus={(e) => e.target.select()}
      onBlur={() => finish(true)}
      onKeyDown={(e) => {
        if (e.key === "Enter") finish(true);
        else if (e.key === "Escape") finish(false);
      }}
    />
  );
}

function Item({ conv, active, renaming, onStartRename, onRename, onStopRename, onDelete, onClose }) {
  if (renaming) {
    return (
      <li className="px-1">
        <RenameInput
          initial={conv.title}
          onSave={(title) => {
            onRename(conv.id, title);
            onStopRename();
          }}
          onCancel={onStopRename}
        />
      </li>
    );
  }
  return (
    <li className="group relative">
      <NavLink
        to={`/chat/${conv.id}`}
        onClick={onClose}
        title={conv.title}
        className={`sidebar-item pr-10 ${active ? "sidebar-item-active" : ""}`}
      >
        <span className="truncate">{conv.title}</span>
      </NavLink>
      <div className="absolute right-1 top-1/2 -translate-y-1/2 opacity-100 transition-opacity duration-150 md:opacity-0 md:focus-within:opacity-100 md:group-hover:opacity-100">
        <Dropdown
          align="right"
          minWidth={160}
          trigger={({ props }) => (
            <button {...props} className="btn-icon-ghost h-8 w-8" aria-label="Chat options">
              <Icon name="more" size={16} />
            </button>
          )}
        >
          <DropdownItem icon="edit" onClick={() => onStartRename(conv.id)}>
            Rename
          </DropdownItem>
          <DropdownItem icon="trash" danger onClick={() => onDelete(conv)}>
            Delete
          </DropdownItem>
        </Dropdown>
      </div>
    </li>
  );
}

// "Chat history" block of the sidebar: New chat button and past conversations grouped by day.
export default function ChatHistory({ slim = false, onClose }) {
  const { conversations, loading, loaded, rename, remove } = useChatHistory();
  const navigate = useNavigate();
  const match = useMatch("/chat/:conversationId");
  const activeId = match ? Number(match.params.conversationId) : null;
  const [renamingId, setRenamingId] = React.useState(null);
  const [deleting, setDeleting] = React.useState(null);
  const groups = React.useMemo(() => groupConversations(conversations), [conversations]);

  const newChat = () => {
    navigate("/chat");
    onClose?.();
  };
  const confirmDelete = async () => {
    const conv = deleting;
    setDeleting(null);
    const ok = await remove(conv.id);
    if (ok && conv.id === activeId) navigate("/chat");
  };

  if (slim) {
    return (
      <div className="flex justify-center">
        <button className="btn-icon-ghost" onClick={newChat} title="New chat" aria-label="New chat">
          <Icon name="plus" />
        </button>
      </div>
    );
  }
  return (
    <div>
      <div className="mb-1 px-3 text-caption-uppercase uppercase text-muted-soft">Chat history</div>
      <button className="btn-secondary mb-sm w-full" onClick={newChat}>
        <Icon name="plus" size={16} />
        New chat
      </button>
      {loading && !loaded ? (
        <div className="space-y-1 px-1" role="status" aria-label="Loading chat history">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <p className="px-3 text-body-sm text-muted">No chats yet. Start one above.</p>
      ) : (
        <div className="space-y-md">
          {groups.map((g) => (
            <div key={g.name}>
              <div className="mb-1 px-3 text-caption text-muted-soft">{g.name}</div>
              <ul className="space-y-0.5">
                {g.items.map((c) => (
                  <Item
                    key={c.id}
                    conv={c}
                    active={c.id === activeId}
                    renaming={renamingId === c.id}
                    onStartRename={setRenamingId}
                    onRename={rename}
                    onStopRename={() => setRenamingId(null)}
                    onDelete={setDeleting}
                    onClose={onClose}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      {deleting &&
        createPortal(
        <Modal title="Delete this chat?" onClose={() => setDeleting(null)}>
          <p className="mb-lg text-body-sm text-body">
            &ldquo;{deleting.title}&rdquo; will be removed from your chat history. This cannot be undone.
          </p>
          <div className="flex justify-end gap-xs">
            <button className="btn-secondary" onClick={() => setDeleting(null)}>
              Cancel
            </button>
            <button className="btn-danger" onClick={confirmDelete}>
              Delete
            </button>
          </div>
        </Modal>,
        document.body
        )}
    </div>
  );
}
