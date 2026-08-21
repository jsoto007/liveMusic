/**
 * The correspondence: your mailbox, and one thread of it.
 *
 * Letters, not chat bubbles — both sides set in the same type, the sender's
 * lines ruled on the right, no filled balloons anywhere.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft, Send } from "lucide-react";
import type {
  ChatMessage,
  Conversation,
  ConversationPage,
  MessagePage,
} from "@live-msc/shared";

import { Empty, Notice, Rule, Spinner } from "../components/Primitives";
import { Avatar, Byline } from "../components/Social";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

function shortWhen(iso: string): string {
  const then = new Date(iso);
  const days = (Date.now() - then.getTime()) / 86_400_000;
  if (days < 1) {
    return then.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  return then.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function MessagesPage() {
  const { user, initializing } = useAuth();
  const [limit, setLimit] = useState(50);

  const { data, error, loading } = useResource<ConversationPage>(
    () => api.get<ConversationPage>(`/api/v1/me/conversations?limit=${limit}`),
    [user?.id ?? "", limit],
    { enabled: !initializing && Boolean(user) },
  );

  if (initializing) return <div className="page page-narrow"><Spinner /></div>;

  if (!user) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">Messages</h1>
        <Notice>Sign in to write to bands and readers.</Notice>
        <Link className="btn btn-primary" to="/sign-in">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <h1 className="page-title">Messages</h1>
      <p className="page-sub">Hire enquiries and correspondence</p>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}
      {data && data.total === 0 ? (
        <Empty>
          No correspondence yet. Message a band from its page, or a poster
          from a gig&rsquo;s application.
        </Empty>
      ) : null}

      {data?.conversations.map((thread) => (
        <Link
          key={thread.id}
          className="notif-row"
          to={`/messages/${thread.id}`}
          style={{ textDecoration: "none" }}
        >
          {thread.unread ? (
            <span className="unread-ring" aria-label="Unread" />
          ) : (
            <span aria-hidden />
          )}
          <span className="notif-line" style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", minWidth: 0 }}>
            <Avatar user={thread.with} />
            <span style={{ minWidth: 0 }}>
              <span className="byline-name">{thread.with.display_name}</span>
              {thread.subject ? (
                <span className="byline-sub"> · {thread.subject}</span>
              ) : null}
              {thread.last_line ? (
                <span className="notif-excerpt">
                  {thread.last_from_me ? "You: " : ""}
                  {thread.last_line}
                </span>
              ) : null}
            </span>
          </span>
          <span className="notif-when">{shortWhen(thread.last_message_at)}</span>
        </Link>
      ))}

      {data?.has_more ? (
        <button
          type="button"
          className="btn btn-ghost btn-block"
          onClick={() => setLimit((value) => value + 50)}
        >
          Older threads
        </button>
      ) : null}
    </div>
  );
}

export function ThreadPage() {
  const { conversationId = "" } = useParams();
  const navigate = useNavigate();
  const { user, initializing } = useAuth();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const thread = useResource<{ conversation: Conversation }>(
    () => api.get<{ conversation: Conversation }>(`/api/v1/conversations/${conversationId}`),
    [conversationId, user?.id ?? ""],
    { enabled: !initializing && Boolean(user) },
  );
  const page = useResource<MessagePage>(
    () =>
      api.get<MessagePage>(
        `/api/v1/conversations/${conversationId}/messages?limit=100`,
      ),
    [conversationId, user?.id ?? ""],
    { enabled: !initializing && Boolean(user) },
  );

  // Opening the thread reads it — stamp once the messages have arrived.
  useEffect(() => {
    if (page.data && user) {
      void api.post(`/api/v1/conversations/${conversationId}/read`, {});
    }
  }, [page.data, conversationId, user]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [page.data]);

  const send = useCallback(async () => {
    const body = draft.trim();
    if (!body) return;
    setSending(true);
    setSendError(null);
    const result = await api.post(
      `/api/v1/conversations/${conversationId}/messages`,
      { body },
    );
    setSending(false);
    if (!result.ok) {
      setSendError(
        result.code === "BLOCKED" ? "You can’t message this account." : result.error,
      );
      return;
    }
    setDraft("");
    page.reload();
  }, [draft, conversationId, page]);

  if (initializing || (!thread.data && thread.loading)) {
    return <div className="page page-narrow"><Spinner /></div>;
  }
  if (!user) {
    return (
      <div className="page page-narrow">
        <Notice>Sign in to read your messages.</Notice>
        <Link className="btn btn-primary" to="/sign-in">Sign in</Link>
      </div>
    );
  }
  if (thread.error || !thread.data) {
    return (
      <div className="page page-narrow">
        <Notice tone="error">
          {thread.error ?? "That conversation could not be found."}
        </Notice>
        <Link className="btn btn-ghost" to="/messages">Back to messages</Link>
      </div>
    );
  }

  const conversation = thread.data.conversation;
  // Served newest-first; printed oldest-first, the way letters file.
  const messages = [...(page.data?.messages ?? [])].reverse();

  return (
    <div className="page page-narrow">
      <button type="button" className="btn btn-ghost" onClick={() => navigate("/messages")}>
        <ChevronLeft size={16} aria-hidden /> All messages
      </button>

      <div style={{ marginTop: "var(--space-4)" }}>
        <Byline user={conversation.with} sub={conversation.subject ?? undefined} size="lg" />
      </div>

      <Rule />

      {page.loading && !page.data ? <Spinner /> : null}
      {messages.length === 0 && page.data ? (
        <Empty>Nothing here yet — write the first line.</Empty>
      ) : null}

      <div>
        {messages.map((message: ChatMessage) => {
          const mine = message.sender.id === user.id;
          return (
            <div
              key={message.id}
              className={mine ? "letter letter-mine" : "letter"}
            >
              <p className="letter-body">{message.body}</p>
              <p className="letter-when">
                {!mine ? `${message.sender.display_name} · ` : ""}
                {shortWhen(message.created_at)}
              </p>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {sendError ? <Notice tone="error">{sendError}</Notice> : null}

      <div className="actions" style={{ alignItems: "flex-end" }}>
        <textarea
          className="input"
          rows={2}
          maxLength={2000}
          placeholder={`Write to ${conversation.with.display_name}`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              void send();
            }
          }}
          style={{ flex: 1 }}
          aria-label="Message"
        />
        <button
          type="button"
          className="btn btn-secondary"
          disabled={sending || !draft.trim()}
          onClick={() => void send()}
        >
          <Send size={15} aria-hidden /> Send
        </button>
      </div>
    </div>
  );
}
