/** 06 — Your list. Going, kept for later, and your named shelves. */

import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useIsFocused, useNavigation } from "@react-navigation/native";
import type { EventList, EventListing } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import {
  Button,
  Chip,
  Empty,
  Heading,
  Kicker,
  Notice,
  Screen,
  SectionHead,
  Spinner,
  Tag,
  inputStyle,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";

interface ListResponse {
  going: EventListing[];
  saved: EventListing[];
  summary: string;
}

export function ListScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user, initializing } = useAuth();
  const focused = useIsFocused();

  const { data, error, loading } = useResource<ListResponse>(
    () => api.get<ListResponse>("/api/v1/me/list"),
    [user?.id ?? "", focused],
  );

  // The named shelves. Re-read on focus so a rename or delete made from a
  // list's own page is reflected when the tab comes back.
  const lists = useResource<{ lists: EventList[]; max_lists: number }>(
    () =>
      user
        ? api.get<{ lists: EventList[]; max_lists: number }>("/api/v1/me/lists")
        : Promise.resolve({ ok: true as const, data: { lists: [], max_lists: 0 }, status: 200 }),
    [user?.id ?? "", focused],
  );

  const [newName, setNewName] = useState("");
  const [newPublic, setNewPublic] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function createList() {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    setCreateError(null);
    const result = await api.post<{ list: EventList }>("/api/v1/me/lists", {
      name,
      is_public: newPublic,
    });
    setCreating(false);
    if (!result.ok) {
      setCreateError(result.error);
      return;
    }
    setNewName("");
    setNewPublic(false);
    lists.reload();
  }

  if (initializing) {
    return (
      <View style={styles.screen}>
        <Spinner />
      </View>
    );
  }

  if (!user) {
    return (
      <Screen>
        <Heading size="h2" display>
          Your list
        </Heading>
        <Notice>Sign in to keep shows and mark what you&rsquo;re going to.</Notice>
        <Button label="Sign in" variant="primary" onPress={() => navigation.navigate("SignIn")} />
      </Screen>
    );
  }

  const namedLists = lists.data?.lists ?? [];
  const maxLists = lists.data?.max_lists ?? 0;
  const atCap = maxLists > 0 && namedLists.length >= maxLists;

  return (
    <Screen>
      <Heading size="h2" display>
        Your list
      </Heading>
      <Kicker style={{ marginTop: 6 }}>{data?.summary ?? "—"}</Kicker>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}

      <SectionHead title="Going" />
      {data?.going.length === 0 ? (
        <Empty>Nothing marked yet.</Empty>
      ) : (
        data?.going.map((event) => (
          <ListingRow
            key={event.id}
            event={event}
            showNote={false}
            onPress={() => navigation.navigate("Show", { eventId: event.id })}
          />
        ))
      )}

      <SectionHead title="Kept for later" />
      {data?.saved.length === 0 ? (
        <Empty>Nothing kept yet.</Empty>
      ) : (
        data?.saved.map((event) => (
          <ListingRow
            key={event.id}
            event={event}
            showNote={false}
            onPress={() => navigation.navigate("Show", { eventId: event.id })}
          />
        ))
      )}

      <SectionHead
        title="Your lists"
        count={
          lists.data
            ? maxLists > 0
              ? `${namedLists.length} of ${maxLists}`
              : undefined
            : undefined
        }
      />
      {lists.error ? <Notice tone="error">{lists.error}</Notice> : null}
      {lists.data && namedLists.length === 0 ? (
        <Empty>No named lists yet — start one below.</Empty>
      ) : null}
      {namedLists.map((list) => (
        <Pressable
          key={list.id}
          onPress={() => navigation.navigate("ListDetail", { listId: list.id })}
          accessibilityRole="button"
          accessibilityLabel={`${list.name}, ${list.is_public ? "public" : "private"}`}
          style={({ pressed }) => [styles.listRow, pressed && { backgroundColor: ink.wash }]}
        >
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.listName} numberOfLines={1}>
              {list.name}
            </Text>
            <Text style={styles.listCount}>{list.count_label ?? ""}</Text>
          </View>
          <Tag label={list.is_public ? "Public" : "Private"} accent={list.is_public} />
        </Pressable>
      ))}

      {createError ? <Notice tone="error">{createError}</Notice> : null}
      {atCap ? (
        <Text style={styles.capNote}>
          You&rsquo;re holding the most lists an account can.
        </Text>
      ) : (
        <View style={styles.newList}>
          <View style={{ flexDirection: "row", gap: space.s2 }}>
            <TextInput
              style={[inputStyle, { flex: 1 }]}
              value={newName}
              onChangeText={setNewName}
              placeholder="Name a new list"
              placeholderTextColor={ink.faint}
              maxLength={80}
              accessibilityLabel="New list name"
            />
            <Button
              label={creating ? "Creating…" : "Create"}
              variant="primary"
              disabled={creating || !newName.trim()}
              onPress={() => void createList()}
            />
          </View>
          <View style={styles.newListVisibility}>
            <Chip label="Private" selected={!newPublic} onPress={() => setNewPublic(false)} />
            <Chip label="Public" selected={newPublic} onPress={() => setNewPublic(true)} />
          </View>
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  listRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  listName: { fontFamily: fonts.heading, fontSize: 15.5, color: colors.text },
  listCount: {
    fontFamily: fonts.body,
    fontSize: 10.5,
    color: ink.faint,
    marginTop: 2,
    ...tabular,
  },
  capNote: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    color: ink.faint,
    marginTop: space.s3,
  },
  newList: { marginTop: space.s3 },
  newListVisibility: { flexDirection: "row", marginTop: space.s2 },
});
