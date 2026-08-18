/** 10 — A list. One reader's shelf, public or their own. */

import { useEffect, useState } from "react";
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useNavigation, useRoute, type RouteProp } from "@react-navigation/native";
import { X } from "lucide-react-native";
import type { ListDetailPage } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import {
  Body,
  Button,
  Chip,
  Empty,
  Heading,
  Kicker,
  Notice,
  SectionHead,
  Spinner,
  inputStyle,
} from "../components/ui";
import { api } from "../lib/auth";
import { colors, fonts, ink, space } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation, RootStackParamList } from "../navigation/types";

export function ListDetailScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { params } = useRoute<RouteProp<RootStackParamList, "ListDetail">>();

  const { data, error, loading, reload } = useResource<ListDetailPage>(
    () => api.get<ListDetailPage>(`/api/v1/lists/${params.listId}?limit=100`),
    [params.listId],
  );

  const list = data?.list ?? null;
  const [actionError, setActionError] = useState<string | null>(null);

  // The manage fields, seeded from the fetched list.
  const [name, setName] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (list) {
      setName(list.name);
      setIsPublic(list.is_public);
    }
    // Re-seed only when a different list arrives, not on every reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list?.id]);

  const dirty =
    list !== null && (name.trim() !== list.name || isPublic !== list.is_public);

  async function save() {
    if (!list) return;
    setBusy(true);
    setActionError(null);
    const result = await api.patch(`/api/v1/me/lists/${list.id}`, {
      name: name.trim(),
      is_public: isPublic,
    });
    setBusy(false);
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    reload();
  }

  function confirmDelete() {
    if (!list) return;
    Alert.alert("Delete this list?", "The shows themselves stay on the bill.", [
      { text: "Keep it", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: () => {
          void (async () => {
            const result = await api.delete(`/api/v1/me/lists/${list.id}`);
            if (!result.ok) {
              setActionError(result.error);
              return;
            }
            navigation.goBack();
          })();
        },
      },
    ]);
  }

  async function removeEntry(eventId: string) {
    if (!list) return;
    setActionError(null);
    const result = await api.delete(`/api/v1/me/lists/${list.id}/events/${eventId}`);
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    reload();
  }

  if (loading && !data) {
    return (
      <View style={styles.screen}>
        <Spinner />
      </View>
    );
  }

  if (error || !data || !list) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Notice tone="error">{error ?? "That list could not be found."}</Notice>
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Kicker accent>
        A list  ·  {list.count_label ?? `${data.total} shows`}
        {data.can_manage ? (list.is_public ? "  ·  public" : "  ·  private") : ""}
      </Kicker>
      <Heading size="h1" display style={{ fontSize: 30, lineHeight: 32, marginTop: space.s2 }}>
        {list.name}
      </Heading>
      {list.description ? <Body style={{ marginTop: space.s2 }}>{list.description}</Body> : null}

      {list.owner ? (
        <Pressable
          onPress={() => navigation.navigate("Profile", { handle: list.owner!.handle })}
          accessibilityRole="button"
          accessibilityLabel={`Kept by ${list.owner.display_name}`}
          hitSlop={4}
        >
          <Text style={styles.byline}>
            Kept by {list.owner.display_name}
            <Text style={styles.bylineHandle}>  @{list.owner.handle}</Text>
          </Text>
        </Pressable>
      ) : null}

      {actionError ? <Notice tone="error">{actionError}</Notice> : null}

      <SectionHead title="On the list" />
      {data.entries.length === 0 ? <Empty>Nothing kept here yet.</Empty> : null}
      {data.entries.map((entry) => (
        <View key={entry.event.id} style={styles.entryRow}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <ListingRow
              // The owner's note prints where the listing's own line would.
              event={{ ...entry.event, short_line: entry.note ?? entry.event.short_line }}
              onPress={() => navigation.navigate("Show", { eventId: entry.event.id })}
            />
          </View>
          {data.can_manage ? (
            <Button
              label=""
              variant="ghost"
              style={styles.removeButton}
              icon={<X size={13} color={ink.soft} />}
              onPress={() => void removeEntry(entry.event.id)}
            />
          ) : null}
        </View>
      ))}

      {data.can_manage ? (
        <>
          <SectionHead title="Manage this list" />
          <View style={{ marginTop: space.s3 }}>
            <TextInput
              style={inputStyle}
              value={name}
              onChangeText={setName}
              maxLength={80}
              placeholder="List name"
              placeholderTextColor={ink.faint}
              accessibilityLabel="List name"
            />
            <View style={styles.visibilityRow}>
              <Text style={styles.visibilityLabel}>Who can see it</Text>
              <View style={{ flexDirection: "row" }}>
                <Chip label="Public" selected={isPublic} onPress={() => setIsPublic(true)} />
                <Chip label="Private" selected={!isPublic} onPress={() => setIsPublic(false)} />
              </View>
            </View>
            {dirty ? (
              <Button
                label={busy ? "Saving…" : "Save changes"}
                variant="primary"
                disabled={busy || !name.trim()}
                onPress={() => void save()}
              />
            ) : null}
            <Button
              label="Delete this list"
              variant="ghost"
              style={{ marginTop: space.s2 }}
              onPress={confirmDelete}
            />
          </View>
        </>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s4, paddingBottom: space.s8 },
  byline: {
    fontFamily: fonts.bodyItalic,
    fontSize: 12,
    color: ink.soft,
    marginTop: space.s3,
  },
  bylineHandle: { fontFamily: fonts.body, fontSize: 11, color: ink.faint },
  entryRow: { flexDirection: "row", alignItems: "center", gap: space.s1 },
  removeButton: { width: 34, minHeight: 34, paddingHorizontal: 0 },
  visibilityRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: space.s3,
    marginVertical: space.s3,
  },
  visibilityLabel: { fontFamily: fonts.body, fontSize: 12, color: ink.soft },
});
