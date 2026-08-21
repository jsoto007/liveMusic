/** 09 — A person. The public profile: bands, shelves, notices. */

import { useCallback, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useNavigation, useRoute, type RouteProp } from "@react-navigation/native";
import { Ellipsis } from "lucide-react-native";
import type { EventList, Profile, Review } from "@live-msc/shared";

import { MessageButton } from "../components/MessageButton";
import { ReportModal } from "../components/ReportModal";
import { Stars } from "../components/Stars";
import {
  Body,
  Button,
  Empty,
  Heading,
  Kicker,
  Notice,
  Plate,
  Rule,
  SectionHead,
  Spinner,
  Tag,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { monthYear, shortDate } from "../lib/format";
import { colors, fonts, ink, radius, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation, RootStackParamList } from "../navigation/types";

export function ProfileScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { params } = useRoute<RouteProp<RootStackParamList, "Profile">>();
  const { user } = useAuth();
  const handle = encodeURIComponent(params.handle);

  const { data, error, loading, reload } = useResource<{ profile: Profile }>(
    () => api.get<{ profile: Profile }>(`/api/v1/users/${handle}`),
    [handle, user?.id ?? ""],
  );
  const lists = useResource<{ lists: EventList[] }>(
    () => api.get<{ lists: EventList[] }>(`/api/v1/users/${handle}/lists`),
    [handle, user?.id ?? ""],
  );
  const reviews = useResource<{ reviews: Review[]; total: number }>(
    () => api.get<{ reviews: Review[]; total: number }>(`/api/v1/users/${handle}/reviews?limit=10`),
    [handle],
  );

  const profile = data?.profile ?? null;
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);

  const toggleFollow = useCallback(async () => {
    if (!profile) return;
    if (!user) {
      navigation.navigate("SignIn");
      return;
    }
    setBusy(true);
    setActionError(null);
    const path = `/api/v1/users/${encodeURIComponent(profile.handle)}/follow`;
    const result = profile.is_following ? await api.delete(path) : await api.post(path);
    setBusy(false);
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    reload();
  }, [profile, user, navigation, reload]);

  const setBlocked = useCallback(
    async (blocked: boolean) => {
      if (!profile) return;
      setOverflowOpen(false);
      if (!user) {
        navigation.navigate("SignIn");
        return;
      }
      setActionError(null);
      const path = `/api/v1/users/${encodeURIComponent(profile.handle)}/block`;
      const result = blocked ? await api.post(path) : await api.delete(path);
      if (!result.ok) {
        setActionError(result.error);
        return;
      }
      reload();
    },
    [profile, user, navigation, reload],
  );

  if (loading && !profile) {
    return (
      <View style={styles.screen}>
        <Spinner />
      </View>
    );
  }

  if (error || !profile) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Notice tone="error">{error ?? "That person could not be found."}</Notice>
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.head}>
        <View style={{ width: 122 }}>
          <Plate
            uri={profile.avatar_url}
            height={108}
            placeholder="portrait"
            accessibilityLabel={profile.display_name}
          />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Kicker accent>
            {profile.role === "artist" ? "Musician" : "Reader"}
            {profile.home_city ? `  ·  ${profile.home_city}` : ""}
          </Kicker>
          <Heading size="h2" display style={{ marginTop: space.s1 }}>
            {profile.display_name}
          </Heading>
          <Text style={styles.handleLine}>@{profile.handle}</Text>
          <Text style={styles.memberSince}>
            Member since {monthYear(profile.member_since)}
          </Text>
        </View>
      </View>

      <Text style={styles.counts}>
        <Text style={styles.countFigure}>{profile.follower_count}</Text>
        {profile.follower_count === 1 ? " follower" : " followers"}
        {"   ·   "}
        <Text style={styles.countFigure}>{profile.following_count}</Text>
        {" following"}
        {"   ·   "}
        <Text style={styles.countFigure}>{profile.review_count}</Text>
        {profile.review_count === 1 ? " review" : " reviews"}
      </Text>

      {actionError ? <Notice tone="error">{actionError}</Notice> : null}

      {profile.is_blocked ? (
        <Notice>
          You&rsquo;ve blocked @{profile.handle}. Their comments and reviews are
          hidden from you.
        </Notice>
      ) : null}

      {profile.is_self ? (
        <Body italic muted style={{ marginTop: space.s3 }}>
          This is you.
        </Body>
      ) : (
        <View style={styles.actions}>
          {profile.is_blocked ? (
            <Button
              label="Unblock"
              style={{ flex: 1 }}
              onPress={() => void setBlocked(false)}
            />
          ) : (
            <Button
              label={profile.is_following ? "Following" : "Follow"}
              variant="toggle"
              on={profile.is_following ?? false}
              disabled={busy}
              style={{ flex: 1 }}
              onPress={() => void toggleFollow()}
            />
          )}
          {!profile.is_blocked ? (
            <MessageButton
              anchor={{ to: profile.handle }}
              recipientName={profile.display_name}
              style={{ flex: 1 }}
            />
          ) : null}
          <Button
            label=""
            icon={<Ellipsis size={16} color={colors.text} strokeWidth={1.5} />}
            style={styles.overflowButton}
            onPress={() => setOverflowOpen(true)}
          />
        </View>
      )}

      {profile.bio ? <Body style={{ marginTop: space.s4 }}>{profile.bio}</Body> : null}

      {profile.artists.length > 0 ? (
        <>
          <SectionHead
            title="Their bands"
            count={profile.artists.length === 1 ? "1 band" : `${profile.artists.length} bands`}
          />
          {profile.artists.map((artist) => (
            <Pressable
              key={artist.id}
              onPress={() => navigation.navigate("Band", { handle: artist.slug })}
              accessibilityRole="button"
              accessibilityLabel={artist.name}
              style={({ pressed }) => [styles.itemRow, pressed && { backgroundColor: ink.wash }]}
            >
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.itemTitle} numberOfLines={1}>
                  {artist.name}
                </Text>
                {artist.one_liner ? (
                  <Text style={styles.itemNote} numberOfLines={1}>
                    {artist.one_liner}
                  </Text>
                ) : null}
              </View>
              {artist.available_for_hire ? <Tag label="For hire" accent /> : null}
            </Pressable>
          ))}
        </>
      ) : null}

      <SectionHead
        title={profile.is_self ? "Your lists" : "Public lists"}
        count={
          lists.data
            ? lists.data.lists.length === 1
              ? "1 list"
              : `${lists.data.lists.length} lists`
            : undefined
        }
      />
      {lists.error ? <Notice tone="error">{lists.error}</Notice> : null}
      {lists.data && lists.data.lists.length === 0 ? (
        <Empty>Nothing on the shelf yet.</Empty>
      ) : null}
      {lists.data?.lists.map((list) => (
        <Pressable
          key={list.id}
          onPress={() => navigation.navigate("ListDetail", { listId: list.id })}
          accessibilityRole="button"
          accessibilityLabel={list.name}
          style={({ pressed }) => [styles.itemRow, pressed && { backgroundColor: ink.wash }]}
        >
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.itemTitle} numberOfLines={1}>
              {list.name}
            </Text>
            <Text style={styles.itemCount}>{list.count_label ?? ""}</Text>
          </View>
          {profile.is_self ? (
            <Tag label={list.is_public ? "Public" : "Private"} accent={list.is_public} />
          ) : null}
        </Pressable>
      ))}

      <SectionHead
        title="Recent reviews"
        count={
          reviews.data
            ? reviews.data.total === 1
              ? "1 review"
              : `${reviews.data.total} reviews`
            : undefined
        }
      />
      {reviews.error ? <Notice tone="error">{reviews.error}</Notice> : null}
      {reviews.data && reviews.data.reviews.length === 0 ? (
        <Empty>No reviews written yet.</Empty>
      ) : null}
      {reviews.data?.reviews.map((review) => (
        <Pressable
          key={review.id}
          onPress={() =>
            review.event && navigation.navigate("Show", { eventId: review.event.id })
          }
          accessibilityRole="button"
          accessibilityLabel={`Review of ${review.event?.headline ?? "a show"}`}
          style={({ pressed }) => [styles.reviewRow, pressed && { backgroundColor: ink.wash }]}
        >
          <View style={styles.reviewHead}>
            <Text style={styles.itemTitle} numberOfLines={1}>
              {review.event?.headline ?? "A show"}
            </Text>
            <Text style={styles.reviewWhen}>{shortDate(review.created_at)}</Text>
          </View>
          <View style={{ marginTop: 4 }}>
            <Stars rating={review.rating} />
          </View>
          {review.body ? (
            <Text style={styles.reviewBody} numberOfLines={3}>
              {review.body}
            </Text>
          ) : null}
        </Pressable>
      ))}

      {/* The overflow: block and report live behind the quiet button. */}
      <Modal
        visible={overflowOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setOverflowOpen(false)}
      >
        <View style={styles.overflowFrame}>
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={() => setOverflowOpen(false)}
            accessibilityRole="button"
            accessibilityLabel="Close"
          />
          <View style={styles.overflowSheet}>
            <Text style={styles.overflowTitle}>@{profile.handle}</Text>
            <Rule style={{ marginTop: space.s2 }} />
            <Button
              label={profile.is_blocked ? "Unblock this person" : "Block this person"}
              variant="ghost"
              style={{ marginTop: space.s2 }}
              onPress={() => void setBlocked(!profile.is_blocked)}
            />
            <Button
              label="Report this person"
              variant="ghost"
              onPress={() => {
                setOverflowOpen(false);
                if (!user) {
                  navigation.navigate("SignIn");
                  return;
                }
                setReportOpen(true);
              }}
            />
            <Button label="Cancel" onPress={() => setOverflowOpen(false)} />
          </View>
        </View>
      </Modal>

      <ReportModal
        visible={reportOpen}
        title="Report this person"
        subject={{ reported_user_id: profile.id }}
        onClose={() => setReportOpen(false)}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s4, paddingBottom: space.s8 },
  head: { flexDirection: "row", gap: space.s3, alignItems: "flex-start" },
  handleLine: { fontFamily: fonts.body, fontSize: 12, color: ink.soft, marginTop: 4 },
  memberSince: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    color: ink.faint,
    marginTop: 4,
  },
  counts: {
    fontFamily: fonts.body,
    fontSize: 12,
    color: ink.soft,
    marginTop: space.s4,
  },
  countFigure: { fontFamily: fonts.heading, fontSize: 14, color: colors.text, ...tabular },
  actions: { flexDirection: "row", gap: space.s2, marginTop: space.s3 },
  overflowButton: { width: 52 },
  itemRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  itemTitle: { fontFamily: fonts.heading, fontSize: 15.5, color: colors.text, flexShrink: 1 },
  itemNote: { fontFamily: fonts.bodyItalic, fontSize: 11, color: ink.faint, marginTop: 2 },
  itemCount: { fontFamily: fonts.body, fontSize: 10.5, color: ink.faint, marginTop: 2, ...tabular },
  reviewRow: {
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  reviewHead: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: space.s2,
  },
  reviewWhen: { fontFamily: fonts.body, fontSize: 10, color: ink.faint, ...tabular },
  reviewBody: {
    fontFamily: fonts.body,
    fontSize: 13,
    lineHeight: 20,
    color: ink.muted,
    marginTop: space.s1,
  },
  overflowFrame: {
    flex: 1,
    justifyContent: "flex-end",
    backgroundColor: "rgba(32,31,29,0.35)",
  },
  overflowSheet: {
    backgroundColor: colors.bg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ink.divider,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingHorizontal: 20,
    paddingTop: space.s4,
    paddingBottom: space.s8,
  },
  overflowTitle: { fontFamily: fonts.heading, fontSize: 16, color: colors.text },
});
