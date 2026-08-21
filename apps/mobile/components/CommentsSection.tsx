/**
 * The comment section under a listing — newest first, likes as small
 * figures, @handles printed as links to their profiles.
 */

import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Flag, Heart, X } from "lucide-react-native";
import { queryString, type Comment, type CommentPage } from "@live-msc/shared";

import { api, useAuth } from "../lib/auth";
import { shortDate } from "../lib/format";
import { splitMentions } from "../lib/mentions";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { usePaged } from "../lib/usePaged";
import type { RootNavigation } from "../navigation/types";
import { ReportModal } from "./ReportModal";
import { Avatar } from "./UserRow";
import { Body, Button, Empty, Notice, SectionHead, Spinner, inputStyle } from "./ui";

const PAGE_SIZE = 20;
const MAX_COMMENT_LENGTH = 2000;

/** A comment body with its @handles set in the accent and made tappable. */
function MentionedBody({
  body,
  onMention,
}: {
  body: string;
  onMention: (handle: string) => void;
}) {
  const segments = splitMentions(body);
  return (
    <Text style={styles.body}>
      {segments.map((segment, index) =>
        segment.handle ? (
          <Text
            key={`${segment.text}-${index}`}
            style={styles.mention}
            onPress={() => onMention(segment.handle!)}
            accessibilityRole="link"
          >
            {segment.text}
          </Text>
        ) : (
          <Text key={`${segment.text.slice(0, 12)}-${index}`}>{segment.text}</Text>
        ),
      )}
    </Text>
  );
}

export function CommentsSection({ eventId }: { eventId: string }) {
  const navigation = useNavigation<RootNavigation>();
  const { user } = useAuth();
  const [draft, setDraft] = useState("");
  const [posting, setPosting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reporting, setReporting] = useState<Comment | null>(null);

  const page = usePaged<Comment>(async (offset) => {
    const result = await api.get<CommentPage>(
      `/api/v1/events/${eventId}/comments${queryString({ limit: PAGE_SIZE, offset })}`,
    );
    if (!result.ok) return result;
    return {
      ok: true,
      status: result.status,
      data: {
        items: result.data?.comments ?? [],
        total: result.data?.total ?? 0,
        hasMore: result.data?.has_more ?? false,
      },
    };
  }, [eventId, user?.id ?? ""]);

  async function post() {
    const body = draft.trim();
    if (!body) return;
    setPosting(true);
    setActionError(null);
    const result = await api.post<{ comment: Comment }>(
      `/api/v1/events/${eventId}/comments`,
      { body },
    );
    setPosting(false);
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    setDraft("");
    page.reload();
  }

  async function toggleLike(comment: Comment) {
    if (!user) {
      navigation.navigate("SignIn");
      return;
    }
    const path = `/api/v1/comments/${comment.id}/like`;
    const result = comment.viewer_liked
      ? await api.delete<{ like_count: number; viewer_liked: boolean }>(path)
      : await api.post<{ like_count: number; viewer_liked: boolean }>(path);
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    const updated = result.data;
    page.mutate((items) =>
      items.map((item) =>
        item.id === comment.id
          ? { ...item, like_count: updated?.like_count ?? item.like_count, viewer_liked: updated?.viewer_liked ?? item.viewer_liked }
          : item,
      ),
    );
  }

  async function remove(comment: Comment) {
    const result = await api.delete(`/api/v1/comments/${comment.id}`);
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    page.reload();
  }

  const countLabel = page.total === 1 ? "1 comment" : `${page.total} comments`;

  return (
    <View>
      <SectionHead title="Comments" count={page.loading ? undefined : countLabel} />

      {actionError ? <Notice tone="error">{actionError}</Notice> : null}
      {page.error ? <Notice tone="error">{page.error}</Notice> : null}

      {user ? (
        <View style={styles.composer}>
          <TextInput
            style={[inputStyle, styles.composerInput]}
            value={draft}
            onChangeText={setDraft}
            placeholder="Say something about this show"
            placeholderTextColor={ink.faint}
            multiline
            maxLength={MAX_COMMENT_LENGTH}
            accessibilityLabel="Write a comment"
          />
          <Button
            label={posting ? "Posting…" : "Post"}
            variant="primary"
            disabled={posting || !draft.trim()}
            onPress={() => void post()}
          />
        </View>
      ) : (
        <View style={styles.signInRow}>
          <Body muted italic style={{ flex: 1 }}>
            Sign in to join the conversation.
          </Body>
          <Button label="Sign in" variant="ghost" onPress={() => navigation.navigate("SignIn")} />
        </View>
      )}

      {page.loading && page.items.length === 0 ? <Spinner label="Fetching the talk" /> : null}
      {!page.loading && page.items.length === 0 ? (
        <Empty>No comments yet. Start it off.</Empty>
      ) : null}

      {page.items.map((comment) => (
        <View key={comment.id} style={styles.comment}>
          <Pressable
            onPress={() => navigation.navigate("Profile", { handle: comment.author.handle })}
            accessibilityRole="button"
            accessibilityLabel={`${comment.author.display_name}'s profile`}
            style={({ pressed }) => [styles.byline, pressed && { backgroundColor: ink.wash }]}
          >
            <Avatar person={comment.author} size={26} />
            <Text style={styles.author} numberOfLines={1}>
              {comment.author.display_name}
              <Text style={styles.authorHandle}>  @{comment.author.handle}</Text>
            </Text>
            <Text style={styles.when}>{shortDate(comment.created_at)}</Text>
          </Pressable>

          <MentionedBody
            body={comment.body}
            onMention={(handle) => navigation.navigate("Profile", { handle })}
          />

          <View style={styles.commentActions}>
            <Pressable
              onPress={() => void toggleLike(comment)}
              hitSlop={8}
              accessibilityRole="button"
              accessibilityState={{ selected: comment.viewer_liked }}
              accessibilityLabel={
                comment.viewer_liked
                  ? `Unlike, ${comment.like_count} likes`
                  : `Like, ${comment.like_count} likes`
              }
              style={styles.likeRow}
            >
              <Heart
                size={13}
                strokeWidth={1.5}
                color={comment.viewer_liked ? colors.accent : ink.soft}
                fill={comment.viewer_liked ? colors.accent : "transparent"}
              />
              <Text
                style={[
                  styles.likeCount,
                  comment.viewer_liked && { color: colors.accent700 },
                ]}
              >
                {comment.like_count}
              </Text>
            </Pressable>

            <View style={{ flex: 1 }} />

            {comment.can_delete ? (
              <Pressable
                onPress={() => void remove(comment)}
                hitSlop={8}
                accessibilityRole="button"
                accessibilityLabel="Delete this comment"
              >
                <X size={13} color={ink.soft} strokeWidth={1.5} />
              </Pressable>
            ) : user ? (
              <Pressable
                onPress={() => setReporting(comment)}
                hitSlop={8}
                accessibilityRole="button"
                accessibilityLabel="Report this comment"
              >
                <Flag size={13} color={ink.soft} strokeWidth={1.5} />
              </Pressable>
            ) : null}
          </View>
        </View>
      ))}

      {page.hasMore ? (
        <Button
          label={page.loadingMore ? "Fetching…" : "More comments"}
          variant="ghost"
          disabled={page.loadingMore}
          onPress={() => void page.loadMore()}
        />
      ) : null}

      <ReportModal
        visible={reporting !== null}
        title="Report this comment"
        subject={{ comment_id: reporting?.id ?? "" }}
        onClose={() => setReporting(null)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  composer: { marginTop: space.s3, gap: space.s2 },
  composerInput: { minHeight: 64, textAlignVertical: "top" },
  signInRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    marginTop: space.s2,
  },
  comment: {
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
  body: {
    fontFamily: fonts.body,
    fontSize: 13,
    lineHeight: 20,
    color: ink.muted,
    marginTop: space.s2,
  },
  mention: { color: colors.accent700 },
  commentActions: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: space.s2,
  },
  likeRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  likeCount: { fontFamily: fonts.body, fontSize: 11, color: ink.soft, ...tabular },
});
