/**
 * The report desk. One subject per report — a listing, a comment, a review,
 * or a person — with a reason and an optional line for the editors.
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
} from "react-native";
import { REPORT_REASONS, type ReportReason } from "@live-msc/shared";

import { api } from "../lib/auth";
import { colors, fonts, ink, radius, space } from "../lib/theme";
import { Body, Button, Chip, Notice, inputStyle } from "./ui";

export type ReportSubject =
  | { comment_id: string }
  | { review_id: string }
  | { reported_user_id: string }
  | { event_id: string };

export function ReportModal({
  visible,
  subject,
  title,
  onClose,
}: {
  visible: boolean;
  subject: ReportSubject;
  /** What is being reported, e.g. "Report this comment". */
  title: string;
  onClose: () => void;
}) {
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  function close() {
    setReason(null);
    setDetail("");
    setError(null);
    setSent(false);
    onClose();
  }

  async function submit() {
    if (!reason) return;
    setBusy(true);
    setError(null);
    const result = await api.post("/api/v1/reports", {
      ...subject,
      reason,
      detail: detail.trim() || undefined,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setSent(true);
  }

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={close}>
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
          <Text style={styles.title}>{title}</Text>
          {sent ? (
            <>
              <Body style={{ marginTop: space.s3 }}>
                Thank you — the editors will take a look.
              </Body>
              <Button
                label="Done"
                variant="primary"
                style={{ marginTop: space.s4 }}
                onPress={close}
              />
            </>
          ) : (
            <>
              {error ? <Notice tone="error">{error}</Notice> : null}
              <View style={styles.chips}>
                {REPORT_REASONS.map((option) => (
                  <Chip
                    key={option.value}
                    label={option.label}
                    selected={reason === option.value}
                    onPress={() => setReason(option.value)}
                  />
                ))}
              </View>
              <TextInput
                style={[inputStyle, styles.detail]}
                value={detail}
                onChangeText={setDetail}
                placeholder="Anything the editors should know (optional)"
                placeholderTextColor={ink.faint}
                multiline
                maxLength={500}
                accessibilityLabel="Report detail"
              />
              <View style={styles.actions}>
                <Button label="Cancel" variant="ghost" style={{ flex: 1 }} onPress={close} />
                <Button
                  label={busy ? "Sending…" : "Send report"}
                  variant="primary"
                  style={{ flex: 1 }}
                  disabled={busy || !reason}
                  onPress={() => void submit()}
                />
              </View>
            </>
          )}
        </View>
      </KeyboardAvoidingView>
    </Modal>
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
  chips: { flexDirection: "row", flexWrap: "wrap", marginTop: space.s3 },
  detail: { minHeight: 64, textAlignVertical: "top", marginTop: space.s2 },
  actions: { flexDirection: "row", gap: space.s2, marginTop: space.s4 },
});
