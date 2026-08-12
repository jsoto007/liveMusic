/** A row on the bill: time, act, price — the paper's basic unit. */

import { useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import type { EventListing } from "@live-msc/shared";

import { stockPosters } from "../lib/stockPosters";
import { colors, fonts, ink, space, tabular } from "../lib/theme";

export function ListingRow({
  event,
  onPress,
  showNote = true,
  leading,
}: {
  event: EventListing;
  onPress: () => void;
  showNote?: boolean;
  /** Overrides the time column — the map uses it for the pin number. */
  leading?: string;
}) {
  const venue = event.venue;
  const [failedUri, setFailedUri] = useState<string | null>(null);
  const posterUri =
    event.poster_url && event.poster_url !== failedUri ? event.poster_url : null;

  // Spelled out for VoiceOver/TalkBack: read as one listing, not as a run of
  // disconnected fragments.
  const spoken = [
    event.headline,
    event.genre_label,
    venue ? `at ${venue.name}` : null,
    `${event.day_label} ${event.time_label ?? ""}`.trim(),
    event.price_label ?? "price not stated",
    event.age_label,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={spoken}
      style={({ pressed }) => [styles.row, pressed && { backgroundColor: ink.wash }]}
    >
      <Text style={[styles.time, leading ? { color: colors.accent } : null]}>
        {leading ?? event.time_label ?? "—"}
      </Text>
      <View style={styles.plate}>
        {/* No uploaded poster prints the genre's house stock, so a row never
            runs without a photograph. Failures are tracked per URI so a
            recycled row retries the next event's real poster. */}
        <Image
          source={posterUri ? { uri: posterUri } : stockPosters[event.genre]}
          style={styles.poster}
          resizeMode="cover"
          onError={posterUri ? () => setFailedUri(posterUri) : undefined}
          accessibilityLabel={
            posterUri ? `Poster for ${event.headline}` : `${event.genre_label} photograph`
          }
        />
      </View>
      <View style={styles.body}>
        <Text style={styles.artist}>{event.headline}</Text>
        <Text style={styles.meta}>
          <Text style={styles.italic}>{event.genre_label}</Text>
          {venue ? `  ·  ${venue.name}` : ""}
          {venue?.neighborhood ? `, ${venue.neighborhood}` : ""}
        </Text>
        {showNote && event.short_line ? (
          <Text style={styles.note}>{event.short_line}</Text>
        ) : null}
      </View>
      <View style={styles.right}>
        <Text style={styles.price}>
          {event.distance_label ?? event.price_label ?? "—"}
        </Text>
        {event.distance_label ? null : <Text style={styles.ages}>{event.age_label}</Text>}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  time: {
    width: 62,
    fontFamily: fonts.heading,
    fontSize: 14,
    color: ink.soft,
    ...tabular,
  },
  plate: {
    width: 62,
    height: 62,
    padding: 2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    alignItems: "center",
    justifyContent: "center",
  },
  poster: { width: "100%", height: "100%" },
  body: { flex: 1, minWidth: 0 },
  artist: { fontFamily: fonts.heading, fontSize: 17, lineHeight: 21, color: colors.text },
  meta: { fontFamily: fonts.body, fontSize: 11.5, lineHeight: 17, color: ink.soft, marginTop: 2 },
  italic: { fontFamily: fonts.bodyItalic },
  note: { fontFamily: fonts.body, fontSize: 11.5, lineHeight: 18, color: ink.faint, marginTop: 4 },
  right: { alignItems: "flex-end" },
  price: { fontFamily: fonts.heading, fontSize: 14, color: colors.text, ...tabular },
  ages: { fontFamily: fonts.body, fontSize: 10, color: ink.faint, marginTop: 3, ...tabular },
});
