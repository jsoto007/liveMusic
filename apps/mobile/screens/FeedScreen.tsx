/** 11 — Following. The reader's personal edition of the paper. */

import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { queryString, type FeedItem, type FeedPage } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import { Stars } from "../components/Stars";
import { Body, Button, Empty, Heading, Notice, Spinner } from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { shortDate } from "../lib/format";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { usePaged } from "../lib/usePaged";
import type { RootNavigation } from "../navigation/types";

const PAGE_SIZE = 30;

export function FeedScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user, initializing } = useAuth();

  const page = usePaged<FeedItem>(async (offset) => {
    if (!user) {
      return { ok: true, status: 200, data: { items: [], total: 0, hasMore: false } };
    }
    const result = await api.get<FeedPage>(
      `/api/v1/me/feed${queryString({ limit: PAGE_SIZE, offset })}`,
    );
    if (!result.ok) return result;
    return {
      ok: true,
      status: result.status,
      data: {
        items: result.data?.items ?? [],
        total: result.data?.total ?? 0,
        hasMore: result.data?.has_more ?? false,
      },
    };
  }, [user?.id ?? ""]);

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
          Following
        </Heading>
        <Notice>
          Sign in and follow people and bands — their new shows, reviews and
          list picks print here.
        </Notice>
        <Button label="Sign in" variant="primary" onPress={() => navigation.navigate("SignIn")} />
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {page.error ? <Notice tone="error">{page.error}</Notice> : null}
      {page.loading && page.items.length === 0 ? <Spinner label="Setting your edition" /> : null}

      {!page.loading && page.items.length === 0 && !page.error ? (
        <Empty>
          Nothing here yet. Follow people and bands — new shows they post,
          reviews they write and shows they shelve will print on this page.
        </Empty>
      ) : null}

      {page.items.map((item, index) => (
        <View key={`${item.type}-${item.event.id}-${item.at}-${index}`} style={styles.item}>
          <View style={styles.lead}>
            <Text style={styles.line}>{item.line}</Text>
            <Text style={styles.when}>{shortDate(item.at)}</Text>
          </View>

          {item.type === "review" && item.review ? (
            <View style={styles.reviewBlock}>
              <Stars rating={item.review.rating} />
              {item.review.body ? (
                <Body style={{ marginTop: space.s1 }}>{item.review.body}</Body>
              ) : null}
            </View>
          ) : null}

          {item.type === "list_add" && item.list ? (
            <Pressable
              onPress={() => navigation.navigate("ListDetail", { listId: item.list!.id })}
              accessibilityRole="button"
              accessibilityLabel={`Open the list ${item.list.name}`}
              hitSlop={4}
            >
              <Text style={styles.listLink}>In &ldquo;{item.list.name}&rdquo; →</Text>
            </Pressable>
          ) : null}

          <ListingRow
            event={item.event}
            showNote={false}
            onPress={() => navigation.navigate("Show", { eventId: item.event.id })}
          />
        </View>
      ))}

      {page.hasMore ? (
        <Button
          label={page.loadingMore ? "Fetching…" : "More"}
          variant="ghost"
          disabled={page.loadingMore}
          onPress={() => void page.loadMore()}
        />
      ) : null}

      {page.items.length > 0 ? (
        <Text style={styles.colophon}>Your edition, from the people you follow.</Text>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s4, paddingBottom: space.s8 },
  item: { marginBottom: space.s2 },
  lead: {
    flexDirection: "row",
    alignItems: "baseline",
    gap: space.s3,
    marginTop: space.s2,
  },
  line: {
    flex: 1,
    minWidth: 0,
    fontFamily: fonts.bodyItalic,
    fontSize: 12.5,
    lineHeight: 18,
    color: ink.soft,
  },
  when: { fontFamily: fonts.body, fontSize: 10, color: ink.faint, ...tabular },
  reviewBlock: { marginTop: space.s2 },
  listLink: {
    fontFamily: fonts.heading,
    fontSize: 13,
    color: colors.accent700,
    marginTop: space.s2,
  },
  colophon: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    color: ink.ghost,
    textAlign: "center",
    marginTop: space.s6,
  },
});
