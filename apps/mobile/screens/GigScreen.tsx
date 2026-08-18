/** 14 — A gig. The full classified: the ask, the pay, the hands raised. */

import { useState } from "react";
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
import type { Gig, GigApplication } from "@live-msc/shared";

import { MessageButton } from "../components/MessageButton";
import {
  Body,
  Button,
  Chip,
  Empty,
  Heading,
  Kicker,
  Notice,
  Rule,
  SectionHead,
  Spinner,
  Tag,
  inputStyle,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation, RootStackParamList } from "../navigation/types";

function SpecRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.specRow}>
      <Text style={styles.specLabel}>{label}</Text>
      <Text style={styles.specValue}>{value}</Text>
    </View>
  );
}

function statusLabel(status: GigApplication["status"]): string {
  return status === "accepted" ? "Accepted" : status === "declined" ? "Declined" : "Pending";
}

export function GigScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { params } = useRoute<RouteProp<RootStackParamList, "Gig">>();
  const { user, artists } = useAuth();

  const { data, error, loading, reload } = useResource<{ gig: Gig }>(
    () => api.get<{ gig: Gig }>(`/api/v1/gigs/${params.gigId}`),
    [params.gigId, user?.id ?? ""],
  );
  const gig = data?.gig ?? null;
  const canManage = gig?.can_manage ?? false;

  const applications = useResource<{ applications: GigApplication[] }>(
    () =>
      canManage
        ? api.get<{ applications: GigApplication[] }>(
            `/api/v1/gigs/${params.gigId}/applications`,
          )
        : Promise.resolve({ ok: true as const, data: { applications: [] }, status: 200 }),
    [params.gigId, canManage],
  );

  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const myApplications = gig?.my_applications ?? [];
  const availableBands = artists.filter(
    (artist) => !myApplications.some((application) => application.artist_id === artist.id),
  );
  const [applyAs, setApplyAs] = useState<string | null>(null);
  const applyArtistId = applyAs ?? availableBands[0]?.id ?? null;

  async function apply() {
    if (!gig || !applyArtistId) return;
    setBusy(true);
    setActionError(null);
    const result = await api.post(`/api/v1/gigs/${gig.id}/applications`, {
      artist_id: applyArtistId,
      message: message.trim() || undefined,
    });
    setBusy(false);
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    setMessage("");
    setApplyAs(null);
    reload();
  }

  async function withdraw(application: GigApplication) {
    if (!gig) return;
    setActionError(null);
    const result = await api.delete(
      `/api/v1/gigs/${gig.id}/applications/${application.id}`,
    );
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    reload();
  }

  async function decide(application: GigApplication, status: "accepted" | "declined") {
    if (!gig) return;
    setActionError(null);
    const result = await api.patch(
      `/api/v1/gigs/${gig.id}/applications/${application.id}`,
      { status },
    );
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    applications.reload();
  }

  async function setStatus(status: "open" | "closed") {
    if (!gig) return;
    setBusy(true);
    setActionError(null);
    const result = await api.patch(`/api/v1/gigs/${gig.id}`, { status });
    setBusy(false);
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    reload();
  }

  function confirmDelete() {
    if (!gig) return;
    Alert.alert("Take this gig off the board?", "Applications go with it.", [
      { text: "Keep it", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: () => {
          void (async () => {
            const result = await api.delete(`/api/v1/gigs/${gig.id}`);
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

  if (loading && !gig) {
    return (
      <View style={styles.screen}>
        <Spinner />
      </View>
    );
  }

  if (error || !gig) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Notice tone="error">{error ?? "That listing could not be found."}</Notice>
      </ScrollView>
    );
  }

  const open = gig.status === "open";

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Kicker accent>
        {open ? "Open" : "Closed"}  ·  {gig.city}
        {gig.neighborhood ? `, ${gig.neighborhood}` : ""}
      </Kicker>
      <Heading size="h1" display style={{ fontSize: 32, lineHeight: 34, marginTop: space.s2 }}>
        {gig.title}
      </Heading>

      <Pressable
        onPress={() => navigation.navigate("Profile", { handle: gig.posted_by.handle })}
        accessibilityRole="button"
        accessibilityLabel={`Posted by ${gig.posted_by.display_name}`}
        hitSlop={4}
      >
        <Text style={styles.byline}>
          Posted by {gig.posted_by.display_name}
          <Text style={styles.bylineHandle}>  @{gig.posted_by.handle}</Text>
        </Text>
      </Pressable>

      {!open ? <Notice>This gig is closed to new applications.</Notice> : null}
      {actionError ? <Notice tone="error">{actionError}</Notice> : null}

      <Rule style={{ marginVertical: space.s4 }} />

      {gig.venue_name ? <SpecRow label="Venue" value={gig.venue_name} /> : null}
      <SpecRow label="When" value={gig.date_label ?? "Date to be arranged"} />
      {gig.time_label ? <SpecRow label="Time" value={gig.time_label} /> : null}
      {/* "Not stated" is a different fact from "free" and prints as one. */}
      <SpecRow label="Pay" value={gig.pay_label ?? "Not stated"} />
      {gig.pay_note ? <SpecRow label="Pay note" value={gig.pay_note} /> : null}
      {gig.genre_label ? <SpecRow label="Genre" value={gig.genre_label} /> : null}

      {gig.description ? <Body style={{ marginTop: space.s4 }}>{gig.description}</Body> : null}

      {myApplications.length > 0 ? (
        <>
          <SectionHead title="Your hand is up" />
          {myApplications.map((application) => (
            <View key={application.id} style={styles.applicationRow}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.applicationName} numberOfLines={1}>
                  {application.artist?.name ?? "Your band"}
                </Text>
                {application.message ? (
                  <Text style={styles.applicationMessage} numberOfLines={2}>
                    {application.message}
                  </Text>
                ) : null}
              </View>
              <Tag
                label={statusLabel(application.status)}
                accent={application.status === "accepted"}
              />
              {/* Reaches whoever posted the gig, off this application. */}
              <MessageButton
                anchor={{ application_id: application.id }}
                recipientName={gig.posted_by.display_name}
                label=""
                variant="ghost"
                style={styles.rowIconButton}
                accessibilityLabel={`Message ${gig.posted_by.display_name}`}
              />
              <Button
                label=""
                variant="ghost"
                style={styles.withdrawButton}
                icon={<X size={13} color={ink.soft} />}
                accessibilityLabel="Withdraw this application"
                onPress={() => void withdraw(application)}
              />
            </View>
          ))}
        </>
      ) : null}

      {user && !canManage && open && availableBands.length > 0 ? (
        <>
          <SectionHead title="Apply" />
          {availableBands.length > 1 ? (
            <View style={styles.bandChips}>
              {availableBands.map((artist) => (
                <Chip
                  key={artist.id}
                  label={artist.name}
                  selected={applyArtistId === artist.id}
                  onPress={() => setApplyAs(artist.id)}
                />
              ))}
            </View>
          ) : (
            <Text style={styles.applyAs}>as {availableBands[0]?.name}</Text>
          )}
          <TextInput
            style={[inputStyle, styles.messageInput]}
            value={message}
            onChangeText={setMessage}
            placeholder="A line to whoever posted it (optional)"
            placeholderTextColor={ink.faint}
            multiline
            maxLength={1000}
            accessibilityLabel="Application message"
          />
          <Button
            label={busy ? "Sending…" : "Raise your hand"}
            variant="primary"
            disabled={busy || !applyArtistId}
            style={{ marginTop: space.s3 }}
            onPress={() => void apply()}
          />
        </>
      ) : null}

      {user && !canManage && open && artists.length === 0 && myApplications.length === 0 ? (
        <Body muted italic style={{ marginTop: space.s4 }}>
          Applying is done as a band — claim a band account under You first.
        </Body>
      ) : null}

      {!user ? (
        <View style={styles.signInRow}>
          <Body muted italic style={{ flex: 1 }}>
            Sign in to apply with your band.
          </Body>
          <Button label="Sign in" variant="ghost" onPress={() => navigation.navigate("SignIn")} />
        </View>
      ) : null}

      {canManage ? (
        <>
          <SectionHead
            title="Applications"
            count={
              gig.application_count === 1
                ? "1 hand up"
                : `${gig.application_count ?? 0} hands up`
            }
          />
          {applications.error ? <Notice tone="error">{applications.error}</Notice> : null}
          {applications.data && applications.data.applications.length === 0 ? (
            <Empty>No hands up yet.</Empty>
          ) : null}
          {applications.data?.applications.map((application) => (
            <View key={application.id} style={styles.manageRow}>
              <Pressable
                onPress={() =>
                  application.artist &&
                  navigation.navigate("Band", { handle: application.artist.slug })
                }
                accessibilityRole="button"
                accessibilityLabel={application.artist?.name ?? "A band"}
                style={({ pressed }) => [{ flex: 1, minWidth: 0 }, pressed && { backgroundColor: ink.wash }]}
              >
                <Text style={styles.applicationName} numberOfLines={1}>
                  {application.artist?.name ?? "A band"} →
                </Text>
                {application.message ? (
                  <Text style={styles.applicationMessage}>{application.message}</Text>
                ) : null}
              </Pressable>
              {application.status === "pending" ? (
                <View style={styles.decideButtons}>
                  <Button
                    label="Accept"
                    variant="primary"
                    style={styles.decideButton}
                    onPress={() => void decide(application, "accepted")}
                  />
                  <Button
                    label="Decline"
                    variant="ghost"
                    style={styles.decideButton}
                    onPress={() => void decide(application, "declined")}
                  />
                </View>
              ) : (
                <Tag
                  label={statusLabel(application.status)}
                  accent={application.status === "accepted"}
                />
              )}
              <MessageButton
                anchor={{ application_id: application.id }}
                recipientName={application.artist?.name ?? "the band"}
                style={styles.messageApplicant}
              />
            </View>
          ))}

          <SectionHead title="Manage" />
          <View style={{ marginTop: space.s3, gap: space.s2 }}>
            <Button
              label={busy ? "Working…" : open ? "Close to applications" : "Reopen the gig"}
              disabled={busy}
              onPress={() => void setStatus(open ? "closed" : "open")}
            />
            <Button label="Delete this gig" variant="ghost" onPress={confirmDelete} />
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
    marginTop: space.s2,
  },
  bylineHandle: { fontFamily: fonts.body, fontSize: 11, color: ink.faint },
  specRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: space.s3,
    paddingVertical: space.s2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  specLabel: {
    fontFamily: fonts.body,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: "uppercase",
    color: ink.soft,
  },
  specValue: {
    flexShrink: 1,
    textAlign: "right",
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.text,
    ...tabular,
  },
  applicationRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  applicationName: { fontFamily: fonts.heading, fontSize: 15, color: colors.text },
  applicationMessage: {
    fontFamily: fonts.body,
    fontSize: 12,
    lineHeight: 18,
    color: ink.soft,
    marginTop: 3,
  },
  withdrawButton: { width: 34, minHeight: 34, paddingHorizontal: 0 },
  rowIconButton: { width: 34, minHeight: 34, paddingHorizontal: 0 },
  messageApplicant: { alignSelf: "flex-start", minHeight: 36, paddingVertical: space.s1 },
  bandChips: { flexDirection: "row", flexWrap: "wrap", marginTop: space.s3 },
  applyAs: {
    fontFamily: fonts.bodyItalic,
    fontSize: 12,
    color: ink.soft,
    marginTop: space.s3,
  },
  messageInput: { minHeight: 64, textAlignVertical: "top", marginTop: space.s3 },
  signInRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    marginTop: space.s4,
  },
  manageRow: {
    paddingVertical: space.s3,
    gap: space.s2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  decideButtons: { flexDirection: "row", gap: space.s2 },
  decideButton: { flex: 1, minHeight: 36, paddingVertical: space.s1 },
});
