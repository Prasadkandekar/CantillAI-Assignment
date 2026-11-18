import React from "react";
import { api } from "../api.js";
import { useAuth } from "../auth/useAuth.js";
import { useToast } from "../components/Toast.jsx";

const Ctx = React.createContext(null);

const byRecent = (a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : b.id - a.id);

// Shared list of saved conversations for the sidebar and ChatPage.
export function ChatHistoryProvider({ children }) {
  const { user } = useAuth();
  const toast = useToast();
  const email = user?.email || user?.name || "";
  const [conversations, setConversations] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api.get("/chat/conversations");
      setConversations([...rows].sort(byRecent));
      setLoaded(true);
    } catch (e) {
      toast.error(e.message || "Could not load chat history");
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  React.useEffect(() => {
    setConversations([]);
    setLoaded(false);
    if (!user) return undefined;
    refresh();
    return undefined;
  }, [email]); // eslint-disable-line react-hooks/exhaustive-deps

  const upsert = React.useCallback((conv) => {
    setConversations((list) => [...list.filter((c) => c.id !== conv.id), conv].sort(byRecent));
  }, []);

  const rename = React.useCallback(
    async (id, title) => {
      let previous;
      setConversations((list) =>
        list.map((c) => {
          if (c.id !== id) return c;
          previous = c;
          return { ...c, title };
        })
      );
      try {
        const saved = await api.patch(`/chat/conversations/${id}`, { title });
        setConversations((list) => list.map((c) => (c.id === id ? { ...c, title: saved.title } : c)));
      } catch (e) {
        if (previous) setConversations((list) => list.map((c) => (c.id === id ? previous : c)));
        toast.error(e.message || "Could not rename chat");
      }
    },
    [toast]
  );

  const remove = React.useCallback(
    async (id) => {
      let previous;
      setConversations((list) => {
        previous = list;
        return list.filter((c) => c.id !== id);
      });
      try {
        await api.del(`/chat/conversations/${id}`);
        toast.success("Chat deleted");
        return true;
      } catch (e) {
        setConversations([...previous].sort(byRecent));
        toast.error(e.message || "Could not delete chat");
        return false;
      }
    },
    [toast]
  );

  const value = React.useMemo(
    () => ({ conversations, loading, loaded, refresh, upsert, rename, remove }),
    [conversations, loading, loaded, refresh, upsert, rename, remove]
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useChatHistory() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useChatHistory must be used inside ChatHistoryProvider");
  return ctx;
}
