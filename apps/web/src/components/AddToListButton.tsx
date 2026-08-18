/** "Add to a list" — a small dialog over the reader's shelves. */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FolderPlus } from "lucide-react";
import type { EventList } from "@live-msc/shared";

import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { Empty, Notice, Spinner } from "./Primitives";

export function AddToListButton({ eventId }: { eventId: string }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [lists, setLists] = useState<EventList[] | null>(null);
  const [added, setAdded] = useState<Record<string, boolean>>({});
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const openDialog = async () => {
    if (!user) {
      navigate("/sign-in");
      return;
    }
    setOpen(true);
    setError(null);
    const result = await api.get<{ lists: EventList[] }>("/api/v1/me/lists");
    if (result.ok) setLists(result.data.lists);
    else setError(result.error);
  };

  const add = async (listId: string) => {
    const result = await api.put(`/api/v1/me/lists/${listId}/events/${eventId}`, {});
    if (result.ok) setAdded((state) => ({ ...state, [listId]: true }));
    else setError(result.error);
  };

  const createAndAdd = async () => {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    setError(null);
    const created = await api.post<{ list: EventList }>("/api/v1/me/lists", { name });
    if (!created.ok) {
      setBusy(false);
      setError(created.error);
      return;
    }
    await add(created.data.list.id);
    setLists((state) => (state ? [created.data.list, ...state] : [created.data.list]));
    setNewName("");
    setBusy(false);
  };

  return (
    <>
      <button type="button" className="btn btn-secondary" onClick={() => void openDialog()}>
        <FolderPlus size={16} aria-hidden /> Add to a list
      </button>
      {open ? (
        <div className="dialog-backdrop" onClick={() => setOpen(false)}>
          <div
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Add to a list"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="dialog-title">Add to a list</p>
            <div className="dialog-body">
              {error ? <Notice tone="error">{error}</Notice> : null}
              {!lists ? <Spinner /> : null}
              {lists && lists.length === 0 ? (
                <Empty>No lists yet — start one below.</Empty>
              ) : null}
              {lists?.map((list) => (
                <div key={list.id} className="person-row">
                  <span>
                    {list.name}
                    <span className="byline-sub">
                      {" "}
                      · {list.is_public ? "public" : "private"}
                      {typeof list.item_count === "number"
                        ? ` · ${list.count_label}`
                        : ""}
                    </span>
                  </span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-quiet"
                    disabled={Boolean(added[list.id])}
                    onClick={() => void add(list.id)}
                  >
                    {added[list.id] ? "Added" : "Add"}
                  </button>
                </div>
              ))}
              <div className="actions" style={{ marginTop: "var(--space-3)" }}>
                <input
                  className="input"
                  placeholder="New list name"
                  maxLength={80}
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy || !newName.trim()}
                  onClick={() => void createAndAdd()}
                >
                  Create &amp; add
                </button>
              </div>
            </div>
            <div className="dialog-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
                Done
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
