/** 16 — Messages. Hire enquiries and correspondence, newest activity first. */

import { useEffect, useState } from "react";
import {
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { queryString, type Conversation, type ConversationPage } from "@live-msc/shared";

import { Avatar } from "../components/UserRow";
import { Button, Empty, Heading, Kicker, Notice, Rule, Spinner } from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { shortWhen } from "../lib/format";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { usePaged } from "../lib/usePaged";
import type { RootNavigation } from "../navigation/types";

const PAGE_SIZE = 50;

export function MessagesScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user, initializing } = useAuth();
  const [refreshing, setRefreshing] = useState(false);

  const page = usePaged<Conversation>(async (offset) => {
    if (!user) {
      return { ok: true, status: 200, data: { items: [], total: 0, hasMore: false } };
    }
    const result = await api.get<ConversationPage>(
      `/api/v1/me/conversations${queryString({ limit: PAGE_SIZE, offset })}`,
    );
    if (!result.ok) return result;
    return {
      ok: true,
      status: result.status,
      data: {
        items: result.data?.conversations ?? [],
        total: result.data?.total ?? 0,
        hasMore: result.data?.has_more ?? false,
      },
    };
  }, [user?.id ?? ""]);

  // The pull-down spinner stays up exactly as long as the reload it started.
  useEffect(() => {
    if (!page.loading) setRefreshing(false);
  }, [page.loading]);

  function open(thread: Conversation) {
    if (thread.unread) {
      // The thread screen stamps the read server-side; the ring clears now.
      page.mutate((items) =>
        items.map((item) => (item.id === thread.id ? { ...item, unread: false } : item)),
      );
    }
    navigation.navigate("Thread", { conversationId: thread.id });
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
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Heading size="h2" display>
          Messages
        </Heading>
        <Notice>Sign in to write to bands and readers.</Notice>
        <Button label="Sign in" variant="primary" onPress={() => navigation.navigate("SignIn")} />
      </ScrollView>
    );
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => {
            setRefreshing(true);
            page.reload();
          }}
          tintColor={colors.accent}
        />
      }
    >
      <Kicker>Hire enquiries and correspondence</Kicker>
      <Rule strong style={{ marginTop: space.s2 }} />

      {page.error ? <Notice tone="error">{page.error}</Notice> : null}
      {page.loading && page.items.length === 0 && !refreshing ? (
        <Spinner label="Fetching the post" />
      ) : null}

      {!page.loading && page.items.length === 0 && !page.error ? (
        <Empty>No correspondence yet — message a band from its page.</Empty>
      ) : null}

      {page.items.map((thread) => (
        <Pressable
          key={thread.id}
          onPress={() => open(thread)}
          accessibilityRole="button"
          accessibilityLabel={`${thread.unread ? "Unread. " : ""}Conversation with ${
            thread.with.display_name
          }${thread.subject ? `, ${thread.subject}` : ""}`}
          style={({ pressed }) => [styles.row, pressed && { backgroundColor: ink.wash }]}
        >
          {/* The unread mark: a small accent ring, drawn not filled. */}
          <View style={[styles.dot, !thread.unread && styles.dotRead]} />
          <Avatar person={thread.with} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.name} numberOfLines={1}>
              {thread.with.display_name}
            </Text>
            {thread.subject ? (
              <Text style={styles.subject} numberOfLines={1}>
                {thread.subject}
              </Text>
            ) : null}
            {thread.last_line ? (
              <Text style={styles.preview} numberOfLines={2}>
                {thread.last_from_me ? "You: " : ""}
                {thread.last_line}
              </Text>
            ) : null}
          </View>
          <Text style={styles.when}>{shortWhen(thread.last_message_at)}</Text>
        </Pressable>
      ))}

      {page.hasMore ? (
        <Button
          label={page.loadingMore ? "Fetching…" : "More"}
          variant="ghost"
          disabled={page.loadingMore}
          onPress={() => void page.loadMore()}
        />
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s4, paddingBottom: space.s8 },
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: colors.accent,
    // Centred against the 40px portrait beside it.
    marginTop: 16,
  },
  dotRead: { borderColor: "transparent" },
  name: { fontFamily: fonts.heading, fontSize: 16, color: colors.text },
  subject: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11.5,
    color: ink.soft,
    marginTop: 2,
  },
  preview: {
    fontFamily: fonts.body,
    fontSize: 12,
    lineHeight: 17,
    color: ink.faint,
    marginTop: 3,
  },
  when: { fontFamily: fonts.body, fontSize: 10, color: ink.faint, marginTop: 3, ...tabular },
});
