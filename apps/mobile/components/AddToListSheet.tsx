/**
 * "Add to a list" — the reader's shelves in a sheet, with a create-new
 * shortcut so the first list is one tap away.
 */

import { useEffect, useState } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Check, Plus } from "lucide-react-native";
import type { EventList } from "@live-msc/shared";

import { api } from "../lib/auth";
import { colors, fonts, ink, radius, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import { Button, Empty, Notice, Spinner, Tag, inputStyle } from "./ui";

export function AddToListSheet({
  visible,
  eventId,
  onClose,
}: {
  visible: boolean;
  eventId: string;
  onClose: () => void;
}) {
  const [addedIds, setAddedIds] = useState<string[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, loading, error: loadError, reload } = useResource<{
    lists: EventList[];
    max_lists: number;
  }>(
    () =>
      visible
        ? api.get<{ lists: EventList[]; max_lists: number }>("/api/v1/me/lists")
        : Promise.resolve({ ok: true as const, data: { lists: [], max_lists: 0 }, status: 200 }),
    [visible],
  );

  // Each opening is a fresh slate — the checks belong to this show only.
  useEffect(() => {
    if (!visible) {
      setAddedIds([]);
      setBusyId(null);
      setNewName("");
      setError(null);
    }
  }, [visible]);

  const lists = data?.lists ?? [];
  // `max_lists` is 0 only for the closed sheet's placeholder response.
  const atCap = data !== null && data.max_lists > 0 && lists.length >= data.max_lists;

  async function addTo(listId: string) {
    setBusyId(listId);
    setError(null);
    const result = await api.put(`/api/v1/me/lists/${listId}/events/${eventId}`, {});
    setBusyId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setAddedIds((current) => (current.includes(listId) ? current : [...current, listId]));
  }

  async function createAndAdd() {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    setError(null);
    const created = await api.post<{ list: EventList }>("/api/v1/me/lists", { name });
    if (!created.ok || !created.data) {
      setCreating(false);
      setError(created.ok ? "The list could not be created." : created.error);
      return;
    }
    setNewName("");
    await addTo(created.data.list.id);
    setCreating(false);
    reload();
  }

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.frame}
      >
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.sheet}>
          <Text style={styles.title}>Add to a list</Text>

          {error ? <Notice tone="error">{error}</Notice> : null}
          {loadError ? <Notice tone="error">{loadError}</Notice> : null}
          {loading ? <Spinner label="Fetching your shelves" /> : null}

          {!loading && lists.length === 0 ? (
            <Empty>No lists yet — name your first below.</Empty>
          ) : null}

          {lists.map((list) => {
            const added = addedIds.includes(list.id);
            return (
              <Pressable
                key={list.id}
                onPress={() => !added && busyId === null && void addTo(list.id)}
                accessibilityRole="button"
                accessibilityState={{ disabled: added }}
                accessibilityLabel={
                  added ? `${list.name}, added` : `Add to ${list.name}`
                }
                style={({ pressed }) => [styles.row, pressed && { backgroundColor: ink.wash }]}
              >
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={styles.rowName} numberOfLines={1}>
                    {list.name}
                  </Text>
                  <Text style={styles.rowCount}>
                    {list.count_label ?? ""}
                    {list.is_public ? "" : "  ·  private"}
                  </Text>
                </View>
                {added ? (
                  <Check size={16} color={colors.accent} strokeWidth={1.6} />
                ) : (
                  <Text style={styles.rowAction}>
                    {busyId === list.id ? "Adding…" : "Add"}
                  </Text>
                )}
              </Pressable>
            );
          })}

          {atCap ? (
            <Text style={styles.capNote}>
              You&rsquo;re holding the most lists an account can.
            </Text>
          ) : (
            <View style={styles.newRow}>
              <TextInput
                style={[inputStyle, { flex: 1 }]}
                value={newName}
                onChangeText={setNewName}
                placeholder="A new list"
                placeholderTextColor={ink.faint}
                maxLength={80}
                accessibilityLabel="New list name"
              />
              <Button
                label={creating ? "Adding…" : "Create"}
                variant="primary"
                disabled={creating || !newName.trim()}
                icon={<Plus size={14} color={colors.accent} />}
                onPress={() => void createAndAdd()}
              />
            </View>
          )}
          {!atCap && newName.trim() ? (
            <View style={{ flexDirection: "row", marginTop: space.s2 }}>
              <Tag label="Starts private" />
            </View>
          ) : null}

          <Button label="Done" variant="ghost" style={{ marginTop: space.s3 }} onPress={onClose} />
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  frame: {
    flex: 1,
    justifyContent: "flex-end",
    backgroundColor: "rgba(32,31,29,0.35)",
  },
  sheet: {
    backgroundColor: colors.bg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ink.divider,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingHorizontal: 20,
    paddingTop: space.s4,
    paddingBottom: space.s8,
  },
  title: { fontFamily: fonts.heading, fontSize: 18, color: colors.text },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  rowName: { fontFamily: fonts.heading, fontSize: 15, color: colors.text },
  rowCount: {
    fontFamily: fonts.body,
    fontSize: 10.5,
    color: ink.faint,
    marginTop: 2,
    ...tabular,
  },
  rowAction: { fontFamily: fonts.heading, fontSize: 13, color: colors.accent },
  capNote: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    color: ink.faint,
    marginTop: space.s3,
  },
  newRow: { flexDirection: "row", gap: space.s2, marginTop: space.s4 },
});
