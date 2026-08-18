/** 12 — The bell. What happened while you were out. */

import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import {
  queryString,
  type Notification,
  type NotificationPage,
} from "@live-msc/shared";

import { Button, Empty, Heading, Kicker, Notice, Rule, Spinner } from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { shortDate } from "../lib/format";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { usePaged } from "../lib/usePaged";
import type { RootNavigation } from "../navigation/types";

const PAGE_SIZE = 50;

export function NotificationsScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user, initializing } = useAuth();
  const [unread, setUnread] = useState(0);

  const page = usePaged<Notification>(async (offset) => {
    if (!user) {
      return { ok: true, status: 200, data: { items: [], total: 0, hasMore: false } };
    }
    const result = await api.get<NotificationPage>(
      `/api/v1/me/notifications${queryString({ limit: PAGE_SIZE, offset })}`,
    );
    if (!result.ok) return result;
    setUnread(result.data?.unread_count ?? 0);
    return {
      ok: true,
      status: result.status,
      data: {
        items: result.data?.notifications ?? [],
        total: result.data?.total ?? 0,
        hasMore: result.data?.has_more ?? false,
      },
    };
  }, [user?.id ?? ""]);

  function open(notification: Notification) {
    if (!notification.read) {
      // Fire and forget — the row flips locally either way.
      void api.post("/api/v1/me/notifications/read", { ids: [notification.id] });
      page.mutate((items) =>
        items.map((item) => (item.id === notification.id ? { ...item, read: true } : item)),
      );
      setUnread((count) => Math.max(0, count - 1));
    }
    if (notification.event_id) {
      navigation.navigate("Show", { eventId: notification.event_id });
    } else if (notification.gig_id) {
      navigation.navigate("Gig", { gigId: notification.gig_id });
    } else if (notification.actor) {
      navigation.navigate("Profile", { handle: notification.actor.handle });
    }
  }

  async function markAllRead() {
    const result = await api.post("/api/v1/me/notifications/read", { all: true });
    if (!result.ok) return;
    page.mutate((items) => items.map((item) => ({ ...item, read: true })));
    setUnread(0);
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
          The bell
        </Heading>
        <Notice>Sign in to see what happened while you were out.</Notice>
        <Button label="Sign in" variant="primary" onPress={() => navigation.navigate("SignIn")} />
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.headRow}>
        <Kicker>
          {unread === 0 ? "All read" : unread === 1 ? "1 unread" : `${unread} unread`}
        </Kicker>
        {unread > 0 ? (
          <Pressable
            onPress={() => void markAllRead()}
            accessibilityRole="button"
            accessibilityLabel="Mark all read"
            hitSlop={8}
          >
            <Text style={styles.markAll}>Mark all read</Text>
          </Pressable>
        ) : null}
      </View>
      <Rule strong style={{ marginTop: space.s2 }} />

      {page.error ? <Notice tone="error">{page.error}</Notice> : null}
      {page.loading && page.items.length === 0 ? <Spinner label="Checking the bell" /> : null}

      {!page.loading && page.items.length === 0 && !page.error ? (
        <Empty>Nothing yet. Follows, comments and gig news land here.</Empty>
      ) : null}

      {page.items.map((notification) => (
        <Pressable
          key={notification.id}
          onPress={() => open(notification)}
          accessibilityRole="button"
          accessibilityLabel={`${notification.read ? "" : "Unread. "}${notification.line}`}
          style={({ pressed }) => [styles.row, pressed && { backgroundColor: ink.wash }]}
        >
          {/* The unread mark: a small accent ring, drawn not filled. */}
          <View style={[styles.dot, notification.read && styles.dotRead]} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={[styles.line, notification.read && styles.lineRead]}>
              {notification.line}
            </Text>
            {notification.comment_excerpt ? (
              <Text style={styles.excerpt} numberOfLines={2}>
                &ldquo;{notification.comment_excerpt}&rdquo;
              </Text>
            ) : null}
          </View>
          <Text style={styles.when}>{shortDate(notification.created_at)}</Text>
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
  headRow: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: space.s3,
  },
  markAll: { fontFamily: fonts.heading, fontSize: 13, color: colors.accent700 },
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
    marginTop: 5,
  },
  dotRead: { borderColor: "transparent" },
  line: {
    fontFamily: fonts.body,
    fontSize: 13,
    lineHeight: 19,
    color: colors.text,
  },
  lineRead: { color: ink.soft },
  excerpt: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11.5,
    lineHeight: 17,
    color: ink.faint,
    marginTop: 3,
  },
  when: { fontFamily: fonts.body, fontSize: 10, color: ink.faint, marginTop: 3, ...tabular },
});
