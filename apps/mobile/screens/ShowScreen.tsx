/** 04 — A show. The full listing. */

import { useCallback } from "react";
import { Linking, ScrollView, StyleSheet, Text, View } from "react-native";
import { useNavigation, useRoute, type RouteProp } from "@react-navigation/native";
import { Bookmark, Ticket } from "lucide-react-native";
import type { EventListing } from "@live-msc/shared";

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
        height={200}
        placeholder="show poster"
        accessibilityLabel={`Poster for ${event.headline}`}
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
        {event.ticket_url ? (
          <Button
            label="Tickets"
            style={{ flex: 1 }}
            icon={<Ticket size={16} color={colors.text} />}
            // The URL came from whoever posted the show, so it is opened in the
            // system browser rather than an in-app view that shares our session.
            onPress={() => void Linking.openURL(event.ticket_url!)}
          />
        ) : null}
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

      {event.artist ? (
        <Button
          label={`More from ${event.artist.name} →`}
          variant="ghost"
          style={{ marginTop: space.s2 }}
          onPress={() => navigation.navigate("Band", { handle: event.artist!.slug })}
        />
      ) : null}
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
