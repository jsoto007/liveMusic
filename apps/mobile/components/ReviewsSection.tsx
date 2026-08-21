/**
 * Reviews under a listing: the aggregate figures, the reader's own review
 * once the doors have opened, and everyone else's below it.
 */

import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Flag } from "lucide-react-native";
import { queryString, type Review, type ReviewPage } from "@live-msc/shared";

import { api, useAuth } from "../lib/auth";
import { shortDate } from "../lib/format";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";
import { ReportModal } from "./ReportModal";
import { StarInput, Stars } from "./Stars";
import { Avatar } from "./UserRow";
import { Body, Button, Empty, Kicker, Notice, SectionHead, Spinner, inputStyle } from "./ui";

const MAX_REVIEW_LENGTH = 2000;

export function ReviewsSection({
  eventId,
  alreadyStarted,
}: {
  eventId: string;
  /** Reviews open once the show has — the server enforces it; this only
   *  decides whether to offer the form or explain the wait. */
  alreadyStarted: boolean;
}) {
  const navigation = useNavigation<RootNavigation>();
  const { user } = useAuth();

  const { data, error, loading, reload } = useResource<ReviewPage>(
    () =>
      api.get<ReviewPage>(
        `/api/v1/events/${eventId}/reviews${queryString({ limit: 50 })}`,
      ),
    [eventId, user?.id ?? ""],
  );

  const [editing, setEditing] = useState(false);
  const [rating, setRating] = useState(0);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [reporting, setReporting] = useState<Review | null>(null);

  const mine = data?.my_review ?? null;
  // The list repeats the viewer's review; it prints in its own block instead.
  const others = (data?.reviews ?? []).filter((review) => !review.can_edit);
  const reviewCount = data?.review_count ?? 0;
  const avg = data?.avg_rating ?? null;

  function beginEdit() {
    setRating(mine?.rating ?? 0);
    setDraft(mine?.body ?? "");
    setFormError(null);
    setEditing(true);
  }

  async function submit() {
    if (rating < 1) {
      setFormError("Choose a star rating first.");
      return;
    }
    setBusy(true);
    setFormError(null);
    const body = draft.trim() || null;
    const result = mine
      ? await api.patch<{ review: Review }>(`/api/v1/reviews/${mine.id}`, { rating, body })
      : await api.post<{ review: Review }>(`/api/v1/events/${eventId}/reviews`, {
          rating,
          body: body ?? undefined,
        });
    setBusy(false);
    if (!result.ok) {
      setFormError(result.error);
      return;
    }
    setEditing(false);
    setRating(0);
    setDraft("");
    reload();
  }

  async function removeMine() {
    if (!mine) return;
    setBusy(true);
    const result = await api.delete(`/api/v1/reviews/${mine.id}`);
    setBusy(false);
    if (!result.ok) {
      setFormError(result.error);
      return;
    }
    setEditing(false);
    reload();
  }

  const showForm = editing || (user !== null && mine === null && alreadyStarted);

  return (
    <View>
      <SectionHead
        title="Reviews"
        count={
          loading ? undefined : reviewCount === 1 ? "1 review" : `${reviewCount} reviews`
        }
      />

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner label="Fetching the notices" /> : null}

      {reviewCount > 0 && avg !== null ? (
        <View style={styles.aggregate}>
          <Stars rating={Math.round(avg)} />
          <Text style={styles.aggregateFigure}>{avg.toFixed(1)}</Text>
          <Text style={styles.aggregateCount}>
            from {reviewCount === 1 ? "1 review" : `${reviewCount} reviews`}
          </Text>
        </View>
      ) : null}

      {formError ? <Notice tone="error">{formError}</Notice> : null}

      {showForm ? (
        <View style={styles.form}>
          <Kicker>{mine ? "Edit your review" : "Write your review"}</Kicker>
          <View style={{ marginTop: space.s2 }}>
            <StarInput value={rating} onChange={setRating} />
          </View>
          <TextInput
            style={[inputStyle, styles.formInput]}
            value={draft}
            onChangeText={setDraft}
            placeholder="How was the night? (optional)"
            placeholderTextColor={ink.faint}
            multiline
            maxLength={MAX_REVIEW_LENGTH}
            accessibilityLabel="Review text"
          />
          <View style={styles.formActions}>
            {mine ? (
              <Button label="Cancel" variant="ghost" onPress={() => setEditing(false)} />
            ) : null}
            <Button
              label={busy ? "Sending…" : mine ? "Save" : "Post review"}
              variant="primary"
              disabled={busy}
              style={{ flex: 1 }}
              onPress={() => void submit()}
            />
          </View>
        </View>
      ) : mine ? (
        <View style={styles.mineBlock}>
          <Kicker accent>Your review</Kicker>
          <View style={{ marginTop: space.s2 }}>
            <Stars rating={mine.rating} />
          </View>
          {mine.body ? <Body style={{ marginTop: space.s2 }}>{mine.body}</Body> : null}
          <View style={styles.formActions}>
            <Button label="Edit" variant="ghost" onPress={beginEdit} />
            <Button
              label={busy ? "Removing…" : "Remove"}
              variant="ghost"
              disabled={busy}
              onPress={() => void removeMine()}
            />
          </View>
        </View>
      ) : user === null && alreadyStarted ? (
        <View style={styles.signInRow}>
          <Body muted italic style={{ flex: 1 }}>
            Sign in to write a review.
          </Body>
          <Button label="Sign in" variant="ghost" onPress={() => navigation.navigate("SignIn")} />
        </View>
      ) : !alreadyStarted ? (
        <Body muted italic style={{ marginTop: space.s2 }}>
          Reviews open once the show starts.
        </Body>
      ) : null}

      {!loading && reviewCount === 0 && others.length === 0 && !mine ? (
        <Empty>No reviews yet.</Empty>
      ) : null}

      {others.map((review) => (
        <View key={review.id} style={styles.review}>
          <Pressable
            onPress={() => navigation.navigate("Profile", { handle: review.author.handle })}
            accessibilityRole="button"
            accessibilityLabel={`${review.author.display_name}'s profile`}
            style={({ pressed }) => [styles.byline, pressed && { backgroundColor: ink.wash }]}
          >
            <Avatar person={review.author} size={26} />
            <Text style={styles.author} numberOfLines={1}>
              {review.author.display_name}
              <Text style={styles.authorHandle}>  @{review.author.handle}</Text>
            </Text>
            <Text style={styles.when}>{shortDate(review.created_at)}</Text>
          </Pressable>
          <View style={styles.reviewStars}>
            <Stars rating={review.rating} />
            {review.edited ? <Text style={styles.edited}>edited</Text> : null}
            <View style={{ flex: 1 }} />
            {user ? (
              <Pressable
                onPress={() => setReporting(review)}
                hitSlop={8}
                accessibilityRole="button"
                accessibilityLabel="Report this review"
              >
                <Flag size={13} color={ink.soft} strokeWidth={1.5} />
              </Pressable>
            ) : null}
          </View>
          {review.body ? <Body style={{ marginTop: space.s1 }}>{review.body}</Body> : null}
        </View>
      ))}

      <ReportModal
        visible={reporting !== null}
        title="Report this review"
        subject={{ review_id: reporting?.id ?? "" }}
        onClose={() => setReporting(null)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  aggregate: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    marginTop: space.s3,
  },
  aggregateFigure: { fontFamily: fonts.heading, fontSize: 16, color: colors.text, ...tabular },
  aggregateCount: { fontFamily: fonts.body, fontSize: 11, color: ink.soft, ...tabular },
  form: { marginTop: space.s3 },
  formInput: { minHeight: 72, textAlignVertical: "top", marginTop: space.s3 },
  formActions: { flexDirection: "row", gap: space.s2, marginTop: space.s3 },
  mineBlock: {
    marginTop: space.s3,
    paddingBottom: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  signInRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    marginTop: space.s2,
  },
  review: {
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  byline: { flexDirection: "row", alignItems: "center", gap: space.s2 },
  author: {
    flex: 1,
    minWidth: 0,
    fontFamily: fonts.heading,
    fontSize: 13.5,
    color: colors.text,
  },
  authorHandle: { fontFamily: fonts.body, fontSize: 10.5, color: ink.faint },
  when: { fontFamily: fonts.body, fontSize: 10, color: ink.faint, ...tabular },
  reviewStars: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    marginTop: space.s2,
  },
  edited: { fontFamily: fonts.bodyItalic, fontSize: 10, color: ink.faint },
});
