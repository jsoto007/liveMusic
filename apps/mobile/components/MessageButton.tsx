/**
 * "Message" — opens with a first line, then lands in the thread.
 *
 * One anchor per button: a @handle, a band (reaches its current owner), or
 * a gig application (connects poster and applicant). The server decides who
 * is actually behind the anchor; the client never resolves identities.
 */

import { useState } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Mail } from "lucide-react-native";
import type { ChatMessage, Conversation } from "@live-msc/shared";

import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, radius, space } from "../lib/theme";
import type { RootNavigation } from "../navigation/types";
import { Button, Notice, inputStyle } from "./ui";

const MAX_MESSAGE_LENGTH = 2000;

export function MessageButton({
  anchor,
  recipientName,
  label = "Message",
  variant = "secondary",
  style,
  accessibilityLabel,
}: {
  anchor: { to?: string; artist_id?: string; application_id?: string };
  recipientName: string;
  label?: string;
  variant?: "secondary" | "ghost";
  style?: StyleProp<ViewStyle>;
  /** Required when `label` is empty and the Mail glyph stands alone. */
  accessibilityLabel?: string;
}) {
  const navigation = useNavigation<RootNavigation>();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function close() {
    setDraft("");
    setError(null);
    setOpen(false);
  }

  async function send() {
    const body = draft.trim();
    if (!body) return;
    setBusy(true);
    setError(null);
    const result = await api.post<{ conversation: Conversation; message: ChatMessage }>(
      "/api/v1/conversations",
      { ...anchor, body },
    );
    setBusy(false);
    if (!result.ok) {
      setError(
        result.code === "BLOCKED" ? "You can’t message this account." : result.error,
      );
      return;
    }
    const conversation = result.data?.conversation;
    close();
    if (conversation) {
      navigation.navigate("Thread", { conversationId: conversation.id });
    }
  }

  return (
    <>
      <Button
        label={label}
        variant={variant}
        style={style}
        accessibilityLabel={accessibilityLabel ?? `Message ${recipientName}`}
        icon={
          <Mail
            size={15}
            color={variant === "ghost" ? colors.accent : colors.text}
            strokeWidth={1.5}
          />
        }
        onPress={() => {
          if (!user) {
            navigation.navigate("SignIn");
            return;
          }
          setDraft("");
          setError(null);
          setOpen(true);
        }}
      />

      <Modal visible={open} transparent animationType="fade" onRequestClose={close}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={styles.frame}
        >
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={close}
            accessibilityRole="button"
            accessibilityLabel="Close"
          />
          <View style={styles.sheet}>
            <Text style={styles.title}>Message {recipientName}</Text>
            {error ? <Notice tone="error">{error}</Notice> : null}
            <TextInput
              style={[inputStyle, styles.body]}
              value={draft}
              onChangeText={setDraft}
              placeholder="Dates, rooms, rates — say what you need."
              placeholderTextColor={ink.faint}
              multiline
              maxLength={MAX_MESSAGE_LENGTH}
              accessibilityLabel={`Message to ${recipientName}`}
            />
            <View style={styles.actions}>
              <Button label="Cancel" variant="ghost" style={{ flex: 1 }} onPress={close} />
              <Button
                label={busy ? "Sending…" : "Send"}
                variant="primary"
                style={{ flex: 1 }}
                disabled={busy || !draft.trim()}
                onPress={() => void send()}
              />
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
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
  body: { minHeight: 84, textAlignVertical: "top", marginTop: space.s3 },
  actions: { flexDirection: "row", gap: space.s2, marginTop: space.s4 },
});
