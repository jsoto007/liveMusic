/** 04 — A show. The full listing, its reviews, and the talk underneath. */

import { useCallback, useState } from "react";
import { Alert, Linking, ScrollView, StyleSheet, Text, View } from "react-native";
import { useNavigation, useRoute, type RouteProp } from "@react-navigation/native";
import { Bookmark, Flag, ListPlus, Ticket } from "lucide-react-native";
import {
  isOpenableTicketUrl,
  ticketButtonLabel,
  ticketHost,
  type EventListing,
} from "@live-msc/shared";

import { AddToListSheet } from "../components/AddToListSheet";
import { CommentsSection } from "../components/CommentsSection";
import { ReportModal } from "../components/ReportModal";
import { ReviewsSection } from "../components/ReviewsSection";
import {
  Body,
  Button,
  Heading,
  Kicker,
  Notice,
  Plate,
  Rule,
  SectionHead,
  Spinner,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { stockPosters } from "../lib/stockPosters";
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

export function ShowScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { params } = useRoute<RouteProp<RootStackParamList, "Show">>();
  const { user } = useAuth();

  const { data, error, loading, reload } = useResource<{ event: EventListing }>(
    () => api.get<{ event: EventListing }>(`/api/v1/events/${params.eventId}`),
    [params.eventId],
  );

  const event = data?.event ?? null;
  const [listSheetOpen, setListSheetOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [managing, setManaging] = useState(false);

  /** Hand the reader off to whoever is actually selling the ticket.

   * Opened with the system browser, never an in-app view: this is a third
   * party's payment page and it must show its own address bar so the reader
   * can see whose site is asking for their card. */
  const openTickets = useCallback(async () => {
    const url = event?.ticket_url;
    if (!isOpenableTicketUrl(url)) return;
    try {
      await Linking.openURL(url!);
    } catch {
      Alert.alert(
        "Could not open the ticket page",
        `Try ${ticketHost(url)} in your browser.`,
      );
    }
  }, [event?.ticket_url]);

  const cancelShow = useCallback(() => {
    Alert.alert(
      "Take this show off the bill?",
      "It stays visible, marked cancelled, so anyone who was going finds out. This cannot be undone.",
      [
        { text: "Keep it", style: "cancel" },
        {
          text: "Cancel the show",
          style: "destructive",
          onPress: () => {
            void (async () => {
              setManaging(true);
              const result = await api.post(
                `/api/v1/events/${params.eventId}/cancel`,
                {},
              );
              setManaging(false);
              if (!result.ok) {
                Alert.alert("That did not work", result.error);
                return;
              }
              reload();
            })();
          },
        },
      ],
    );
  }, [params.eventId, reload]);

  const setInterest = useCallback(
    async (patch: { saved?: boolean; going?: boolean }) => {
      if (!user) {
        navigation.navigate("SignIn");
        return;
      }
      await api.put(`/api/v1/events/${params.eventId}/interest`, patch);
      reload();
    },
    [user, navigation, params.eventId, reload],
  );

  if (loading && !event) {
    return (
      <View style={styles.screen}>
        <Spinner />
      </View>
    );
  }

  if (error || !event) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Notice tone="error">{error ?? "That listing could not be found."}</Notice>
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Plate
        uri={event.poster_url}
        fallbackSource={stockPosters[event.genre]}
        height={200}
        placeholder="show poster"
        accessibilityLabel={
          event.poster_url
            ? `Poster for ${event.headline}`
            : `${event.genre_label} photograph`
        }
      />
      {event.poster_credit ? <Text style={styles.plateCredit}>{event.poster_credit}</Text> : null}

      <View style={{ paddingTop: space.s4 }}>
        <Kicker accent>
          {event.day_label}  ·  {event.date_long}
        </Kicker>
        <Heading size="h1" display style={{ fontSize: 34, lineHeight: 36, marginTop: space.s2 }}>
          {event.headline}
        </Heading>
        {event.support_line ? (
          <Text style={styles.support}>{event.support_line}</Text>
        ) : null}
        {event.cancelled ? (
          <Notice tone="error">This show has been cancelled.</Notice>
        ) : null}
      </View>

      <Rule style={{ marginVertical: space.s4 }} />

      <SpecRow
        label="Venue"
        value={`${event.venue?.name ?? "—"}${
          event.venue?.neighborhood ? `, ${event.venue.neighborhood}` : ""
        }`}
      />
      {event.doors_label ? <SpecRow label="Doors" value={event.doors_label} /> : null}
      <SpecRow label="First set" value={event.time_label ?? "—"} />
      {/* "Not stated" is a different fact from "free" and prints as one. */}
      <SpecRow label="Door price" value={event.price_label ?? "Not stated"} />
      <SpecRow label="Ages" value={event.age_label} />

      {event.blurb ? <Body style={{ marginTop: space.s4 }}>{event.blurb}</Body> : null}

      {event.lineup && event.lineup.length > 0 ? (
        <>
          <SectionHead title="On the bill" />
          {event.lineup.map((slot, index) => (
            <View key={`${slot.name}-${index}`} style={styles.lineupRow}>
              <Text style={styles.lineupTime}>{slot.time_label ?? "—"}</Text>
              <View style={{ flex: 1 }}>
                <Text style={styles.lineupName}>{slot.name}</Text>
                {slot.note ? <Text style={styles.lineupNote}>{slot.note}</Text> : null}
              </View>
            </View>
          ))}
        </>
      ) : null}

      <View style={styles.actions}>
        <Button
          label={event.going ? "You're going" : "I'm going"}
          variant="toggle"
          on={event.going}
          style={{ flex: 1 }}
          onPress={() => void setInterest({ going: !event.going })}
        />
        <Button
          label=""
          on={event.saved}
          icon={
            <Bookmark
              size={17}
              color={event.saved ? colors.accent : colors.text}
              fill={event.saved ? colors.accent : "transparent"}
            />
          }
          onPress={() => void setInterest({ saved: !event.saved })}
        />
      </View>

      {/* A show that needs a ticket says so, names the seller, and hands the
          reader straight to that seller's page. Nothing is sold in here. */}
      {isOpenableTicketUrl(event.ticket_url) && !event.cancelled ? (
        <>
          <Button
            label={ticketButtonLabel(event.ticket_url)}
            variant="primary"
            icon={<Ticket size={16} color={colors.accent} />}
            style={{ marginTop: space.s2 }}
            onPress={() => void openTickets()}
          />
          <Text style={styles.ticketNote}>
            Tickets are sold by {ticketHost(event.ticket_url)}, not by Live Msc.
            The link opens in your browser.
          </Text>
        </>
      ) : null}

      <Button
        label="Add to a list"
        icon={<ListPlus size={16} color={colors.text} strokeWidth={1.5} />}
        style={{ marginTop: space.s2 }}
        onPress={() =>
          user ? setListSheetOpen(true) : navigation.navigate("SignIn")
        }
      />

      {event.artist ? (
        <Button
          label={`More from ${event.artist.name} →`}
          variant="ghost"
          style={{ marginTop: space.s2 }}
          onPress={() => navigation.navigate("Band", { handle: event.artist!.slug })}
        />
      ) : null}

      {/* Whoever posted the show can take it off the bill. The server decides
          this from the authenticated user — `can_manage` is its answer, not
          something inferred here from an artist id the client also holds. */}
      {event.can_manage && !event.cancelled ? (
        <Button
          label={managing ? "Cancelling…" : "Cancel this show"}
          variant="ghost"
          disabled={managing}
          style={{ marginTop: space.s2 }}
          onPress={cancelShow}
        />
      ) : null}

      <ReviewsSection eventId={params.eventId} alreadyStarted={event.already_started} />
      <CommentsSection eventId={params.eventId} />

      {/* A listing carries a headline, a note and an uploaded poster, so it
          needs the same flag as anything else a reader can write. */}
      {!event.can_manage ? (
        <Button
          label="Report this listing"
          variant="ghost"
          icon={<Flag size={14} color={ink.soft} strokeWidth={1.5} />}
          style={{ marginTop: space.s6 }}
          onPress={() =>
            user ? setReportOpen(true) : navigation.navigate("SignIn")
          }
        />
      ) : null}

      <AddToListSheet
        visible={listSheetOpen}
        eventId={params.eventId}
        onClose={() => setListSheetOpen(false)}
      />

      <ReportModal
        visible={reportOpen}
        subject={{ event_id: params.eventId }}
        title="Report this listing"
        onClose={() => setReportOpen(false)}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s4, paddingBottom: space.s8 },
  plateCredit: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    color: ink.faint,
    marginTop: space.s1,
  },
  ticketNote: {
    fontFamily: fonts.body,
    fontSize: 12,
    lineHeight: 18,
    color: ink.soft,
    marginTop: space.s1,
  },
  support: {
    fontFamily: fonts.bodyItalic,
    fontSize: 16,
    color: ink.soft,
    marginTop: space.s2,
  },
  specRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
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
  specValue: { fontFamily: fonts.body, fontSize: 13, color: colors.text, ...tabular },
  lineupRow: {
    flexDirection: "row",
    gap: space.s3,
    alignItems: "flex-start",
    paddingVertical: space.s2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  lineupTime: { width: 58, fontFamily: fonts.heading, fontSize: 13, color: ink.soft, ...tabular },
  lineupName: { fontFamily: fonts.heading, fontSize: 15, color: colors.text },
  lineupNote: { fontFamily: fonts.bodyItalic, fontSize: 11, color: ink.faint, marginTop: 1 },
  actions: { flexDirection: "row", gap: space.s2, marginTop: space.s4, flexWrap: "wrap" },
});
