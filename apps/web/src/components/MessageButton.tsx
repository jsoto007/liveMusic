/**
 * "Message" — opens with a first line, then lands in the thread.
 *
 * One anchor per button: a @handle, a band (reaches its current owner), or
 * a gig application (connects poster and applicant). The server decides who
 * is actually behind the anchor; the client never resolves identities.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mail } from "lucide-react";
import type { Conversation } from "@live-msc/shared";

import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { Notice } from "./Primitives";

export function MessageButton({
  anchor,
  recipientName,
  label = "Message",
}: {
  anchor: { to?: string; artist_id?: string; application_id?: string };
  recipientName: string;
  label?: string;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    const body = draft.trim();
    if (!body) return;
    setBusy(true);
    setError(null);
    const result = await api.post<{ conversation: Conversation }>(
      "/api/v1/conversations",
      { ...anchor, body },
    );
    setBusy(false);
    if (!result.ok) {
      setError(
        result.code === "BLOCKED" ? "You can’t message this account." : result.error,
      );
      return;
    }
    setOpen(false);
    navigate(`/messages/${result.data.conversation.id}`);
  };

  return (
    <>
      <button
        type="button"
        className="btn btn-secondary"
        onClick={() => {
          if (!user) {
            navigate("/sign-in");
            return;
          }
          setDraft("");
          setError(null);
          setOpen(true);
        }}
      >
        <Mail size={15} aria-hidden /> {label}
      </button>
      {open ? (
        <div className="dialog-backdrop" onClick={() => setOpen(false)}>
          <div
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-label={`Message ${recipientName}`}
            onClick={(event) => event.stopPropagation()}
          >
            <p className="dialog-title">Message {recipientName}</p>
            <div className="dialog-body">
              <textarea
                className="input"
                rows={4}
                maxLength={2000}
                placeholder="Dates, rooms, rates — say what you need."
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                autoFocus
              />
              {error ? <Notice tone="error">{error}</Notice> : null}
            </div>
            <div className="dialog-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
                Never mind
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy || !draft.trim()}
                onClick={() => void send()}
              >
                Send
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
