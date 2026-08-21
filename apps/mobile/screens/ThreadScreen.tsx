/**
 * 17 — A thread. Letters between two parties — ruled and bordered, never
 * bubbled. Served newest-first; printed oldest-first, the way letters file.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useNavigation, useRoute, type RouteProp } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Send } from "lucide-react-native";
import {
  queryString,
  type ChatMessage,
  type Conversation,
  type MessagePage,
} from "@live-msc/shared";

import { UserRow } from "../components/UserRow";
import { Button, Empty, Notice, Rule, Spinner, inputStyle } from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { shortDate } from "../lib/format";
import { colors, fonts, ink, radius, space, tabular } from "../lib/theme";
import { usePaged } from "../lib/usePaged";
import { useResource } from "../lib/useResource";
import type { RootNavigation, RootStackParamList } from "../navigation/types";

const PAGE_SIZE = 50;
const MAX_MESSAGE_LENGTH = 2000;

/** The native-stack bar above this screen; the keyboard inset must clear it. */
const STACK_HEADER_HEIGHT = 44;

export function ThreadScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { params } = useRoute<RouteProp<RootStackParamList, "Thread">>();
  const { user, initializing } = useAuth();
  const insets = useSafeAreaInsets();

  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView | null>(null);
  // The page opens pinned to the newest line; "Load earlier" unpins it so
  // older pages don't yank the reader back to the bottom.
  const pinnedToEnd = useRef(true);
  const readStampedFor = useRef<string | null>(null);

  const thread = useResource<{ conversation: Conversation } | null>(
    () =>
      user
        ? api.get<{ conversation: Conversation }>(
            `/api/v1/conversations/${params.conversationId}`,
          )
        : Promise.resolve({ ok: true as const, status: 200, data: null }),
    [params.conversationId, user?.id ?? ""],
  );

  const page = usePaged<ChatMessage>(async (offset) => {
    if (!user) {
      return { ok: true, status: 200, data: { items: [], total: 0, hasMore: false } };
    }
    const result = await api.get<MessagePage>(
      `/api/v1/conversations/${params.conversationId}/messages${queryString({
        limit: PAGE_SIZE,
        offset,
      })}`,
    );
    if (!result.ok) return result;
    return {
      ok: true,
      status: result.status,
      data: {
        items: result.data?.messages ?? [],
        total: result.data?.total ?? 0,
        hasMore: result.data?.has_more ?? false,
      },
    };
  }, [params.conversationId, user?.id ?? ""]);

  // Opening the thread reads it — stamped once the letters have arrived.
  useEffect(() => {
    if (!user || page.loading || readStampedFor.current === params.conversationId) return;
    readStampedFor.current = params.conversationId;
    void api.post(`/api/v1/conversations/${params.conversationId}/read`);
  }, [user, page.loading, params.conversationId]);

  // Newest-first from the API; printed oldest-first. A line appended locally
  // after a send can reappear when an older page lands, so keyed once by id.
  const letters = useMemo(() => {
    const seen = new Set<string>();
    const unique: ChatMessage[] = [];
    for (const message of page.items) {
      if (seen.has(message.id)) continue;
      seen.add(message.id);
      unique.push(message);
    }
    return unique.reverse();
  }, [page.items]);

  async function send() {
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setSendError(null);
    const result = await api.post<{ message: ChatMessage }>(
      `/api/v1/conversations/${params.conversationId}/messages`,
      { body },
    );
    setSending(false);
    if (!result.ok) {
      setSendError(
        result.code === "BLOCKED" ? "You can’t message this account." : result.error,
      );
      return;
    }
    setDraft("");
    pinnedToEnd.current = true;
    const sent = result.data?.message;
    if (sent) {
      // Items run newest-first, so the fresh line goes on the front.
      page.mutate((items) => [sent, ...items]);
    } else {
      page.reload();
    }
  }

  if (initializing || (thread.loading && !thread.data)) {
    return (
      <View style={styles.screen}>
        <Spinner />
      </View>
    );
  }

  if (!user) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Notice>Sign in to read your messages.</Notice>
        <Button label="Sign in" variant="primary" onPress={() => navigation.navigate("SignIn")} />
      </ScrollView>
    );
  }

  const conversation = thread.data?.conversation ?? null;
  if (thread.error || !conversation) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Notice tone="error">
          {thread.error ?? "That conversation could not be found."}
        </Notice>
      </ScrollView>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={
        Platform.OS === "ios" ? insets.top + STACK_HEADER_HEIGHT : 0
      }
    >
      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        onContentSizeChange={() => {
          if (pinnedToEnd.current) scrollRef.current?.scrollToEnd({ animated: false });
        }}
      >
        {/* The other party's byline heads the page; the subject rides under it. */}
        <UserRow
          person={conversation.with}
          note={conversation.subject}
          onPress={() =>
            navigation.navigate("Profile", { handle: conversation.with.handle })
          }
        />

        {page.error ? <Notice tone="error">{page.error}</Notice> : null}
        {page.loading && letters.length === 0 ? <Spinner label="Opening the file" /> : null}

        {page.hasMore ? (
          <Button
            label={page.loadingMore ? "Fetching…" : "Load earlier"}
            variant="ghost"
            disabled={page.loadingMore}
            style={{ marginTop: space.s2 }}
            onPress={() => {
              pinnedToEnd.current = false;
              void page.loadMore();
            }}
          />
        ) : null}

        {!page.loading && letters.length === 0 && !page.error ? (
          <Empty>Nothing here yet — write the first line.</Empty>
        ) : null}

        {letters.map((message, index) => {
          const mine = message.sender.id === user.id;
          const day = new Date(message.created_at).toDateString();
          const previousDay =
            index > 0 ? new Date(letters[index - 1]!.created_at).toDateString() : null;
          return (
            <View key={message.id}>
              {/* Timestamps print sparingly — a dated rule where the day turns. */}
              {day !== previousDay ? (
                <View style={styles.dayRow}>
                  <Rule style={{ flex: 1 }} />
                  <Text style={styles.dayLabel}>{shortDate(message.created_at)}</Text>
                  <Rule style={{ flex: 1 }} />
                </View>
              ) : null}
              <View style={[styles.letter, mine ? styles.letterMine : styles.letterTheirs]}>
                <Text style={styles.letterBody}>{message.body}</Text>
              </View>
            </View>
          );
        })}
      </ScrollView>

      {sendError ? (
        <View style={{ paddingHorizontal: 20 }}>
          <Notice tone="error">{sendError}</Notice>
        </View>
      ) : null}

      <View style={[styles.composer, { paddingBottom: Math.max(insets.bottom, space.s2) }]}>
        <TextInput
          style={[inputStyle, styles.composerInput]}
          value={draft}
          onChangeText={setDraft}
          placeholder={`Write to ${conversation.with.display_name}`}
          placeholderTextColor={ink.faint}
          multiline
          maxLength={MAX_MESSAGE_LENGTH}
          accessibilityLabel={`Write to ${conversation.with.display_name}`}
        />
        <Button
          label={sending ? "Sending…" : "Send"}
          icon={<Send size={14} color={colors.text} strokeWidth={1.5} />}
          disabled={sending || !draft.trim()}
          onPress={() => void send()}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s2, paddingBottom: space.s4 },
  dayRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s3,
    marginTop: space.s4,
  },
  dayLabel: { fontFamily: fonts.body, fontSize: 10, color: ink.faint, ...tabular },
  letter: { maxWidth: "85%", marginTop: space.s3 },
  letterMine: {
    alignSelf: "flex-end",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    borderRadius: radius.md,
    paddingVertical: space.s2,
    paddingHorizontal: space.s3,
  },
  letterTheirs: {
    alignSelf: "flex-start",
    borderLeftWidth: 2,
    borderLeftColor: colors.neutral300,
    paddingLeft: space.s3,
    paddingVertical: space.s1,
  },
  letterBody: {
    fontFamily: fonts.body,
    fontSize: 13.5,
    lineHeight: 21,
    color: colors.text,
  },
  composer: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: space.s2,
    paddingHorizontal: 20,
    paddingTop: space.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ink.divider,
    backgroundColor: colors.bg,
  },
  composerInput: { flex: 1, maxHeight: 120 },
});
