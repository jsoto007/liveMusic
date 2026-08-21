/** One shelf: its shows, its byline, and — for its owner — its controls. */

import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import type { ListDetailPage } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import { Empty, Notice, Rule, Spinner } from "../components/Primitives";
import { Byline } from "../components/Social";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

export function ListDetailPageView() {
  const { listId = "" } = useParams();
  const navigate = useNavigate();
  const { user, initializing } = useAuth();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);

  const { data, error, loading, reload } = useResource<ListDetailPage>(
    () => api.get<ListDetailPage>(`/api/v1/lists/${listId}?limit=100`),
    [listId, user?.id ?? ""],
    { enabled: !initializing },
  );

  const list = data?.list ?? null;

  const startEditing = () => {
    if (!list) return;
    setName(list.name);
    setDescription(list.description ?? "");
    setSaveError(null);
    setEditing(true);
  };

  const save = async () => {
    if (!list) return;
    const result = await api.patch(`/api/v1/me/lists/${list.id}`, {
      name: name.trim(),
      description: description.trim() || null,
    });
    if (!result.ok) {
      setSaveError(result.error);
      return;
    }
    setEditing(false);
    reload();
  };

  const toggleVisibility = async () => {
    if (!list) return;
    await api.patch(`/api/v1/me/lists/${list.id}`, { is_public: !list.is_public });
    reload();
  };

  const removeList = async () => {
    if (!list) return;
    await api.delete(`/api/v1/me/lists/${list.id}`);
    navigate("/list");
  };

  const removeEntry = async (eventId: string) => {
    if (!list) return;
    await api.delete(`/api/v1/me/lists/${list.id}/events/${eventId}`);
    reload();
  };

  if ((loading || initializing) && !data) {
    return <div className="page page-narrow"><Spinner /></div>;
  }
  if (error || !data || !list) {
    return (
      <div className="page page-narrow">
        <Notice tone="error">{error ?? "That list could not be found."}</Notice>
        <Link className="btn btn-ghost" to="/list">Back to your list</Link>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)}>
        <ChevronLeft size={16} aria-hidden /> Back
      </button>

      <header style={{ paddingTop: "var(--space-4)" }}>
        {editing ? (
          <div>
            <input
              className="input"
              maxLength={80}
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-label="List name"
            />
            <textarea
              className="input"
              rows={2}
              maxLength={300}
              placeholder="A line about this list (optional)"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              style={{ marginTop: "var(--space-2)" }}
            />
            <div className="actions" style={{ marginTop: "var(--space-2)" }}>
              <button type="button" className="btn btn-secondary" onClick={() => void save()}>
                Save
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setEditing(false)}>
                Never mind
              </button>
            </div>
            {saveError ? <Notice tone="error">{saveError}</Notice> : null}
          </div>
        ) : (
          <>
            <p className="kicker kicker-accent">
              {list.is_public ? "Public list" : "Private list"} ·{" "}
              {list.count_label ?? `${data.total} shows`}
            </p>
            <h1 className="detail-title">{list.name}</h1>
            {list.description ? (
              <p className="detail-support">{list.description}</p>
            ) : null}
            {list.owner ? (
              <div style={{ marginTop: "var(--space-3)" }}>
                <Byline user={list.owner} />
              </div>
            ) : null}
          </>
        )}
        {data.can_manage && !editing ? (
          <div className="actions">
            <button type="button" className="btn btn-ghost" onClick={startEditing}>
              Rename
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => void toggleVisibility()}>
              Make {list.is_public ? "private" : "public"}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-quiet"
              onClick={() => void removeList()}
            >
              Delete list
            </button>
          </div>
        ) : null}
      </header>

      <Rule />

      {data.entries.length === 0 ? (
        <Empty>
          Nothing here yet{data.can_manage ? " — add shows from any listing page" : ""}.
        </Empty>
      ) : null}

      {data.entries.map((entry) => (
        <div key={entry.event.id}>
          <ListingRow event={entry.event} showNote={false} />
          {(entry.note || data.can_manage) ? (
            <div
              className="comment-actions"
              style={{ marginTop: "calc(var(--space-2) * -1)", paddingBottom: "var(--space-2)" }}
            >
              {entry.note ? (
                <span className="listing-note italic">{entry.note}</span>
              ) : null}
              {data.can_manage ? (
                <button
                  type="button"
                  className="btn btn-ghost btn-quiet"
                  onClick={() => void removeEntry(entry.event.id)}
                >
                  Remove
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
