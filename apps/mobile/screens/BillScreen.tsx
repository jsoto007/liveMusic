/** 01 — The Bill. Tonight's listings, set as a page. */

import { useCallback, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Bookmark, Search } from "lucide-react-native";
import {
  DAY_FILTERS,
  queryString,
  type BillPage,
  type DayBucket,
  type EventListing,
} from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import {
  Body,
  Button,
  Chip,
  Empty,
  Heading,
  Kicker,
  Notice,
  Plate,
  Rule,
  Screen,
  SectionHead,
  Spinner,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";

export function BillScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user } = useAuth();
  const [day, setDay] = useState<"all" | DayBucket>("all");

  const { data, error, loading, reload } = useResource<BillPage>(
    () => api.get<BillPage>(`/api/v1/events${queryString({ day })}`),
    [day],
  );

  const featured = data?.events[0] ?? null;

  // The featured show has the plate already; printing it again in the list
  // would duplicate the listing on one page.
  const sections = useMemo(() => {
    if (!data) return [];
    if (!featured) return data.sections;
    return data.sections
      .map((section) => ({
        ...section,
        events: section.events.filter((event) => event.id !== featured.id),
      }))
      .filter((section) => section.events.length > 0);
  }, [data, featured]);

  const toggleSave = useCallback(
    async (event: EventListing) => {
      if (!user) {
        navigation.navigate("SignIn");
        return;
      }
      await api.put(`/api/v1/events/${event.id}/interest`, { saved: !event.saved });
      reload();
    },
    [user, navigation, reload],
  );

  return (
    <Screen>
      {/* The masthead. The navigator's header is hidden on the tabs so each
          screen can carry the paper's own, in the display cut on the ground
          colour rather than a chrome bar. */}
      <View style={styles.masthead}>
        <View style={{ flex: 1 }}>
          <Heading size="h1" display style={{ fontSize: 30, lineHeight: 32 }}>
            Live Msc
          </Heading>
          <Kicker style={{ marginTop: 6 }}>
            {user?.home_city ? `${user.home_city}  ·  ` : ""}
            {todayLine()}
          </Kicker>
        </View>
        <Pressable
          onPress={() => navigation.navigate("Search")}
          accessibilityRole="button"
          accessibilityLabel="Search listings"
          hitSlop={12}
        >
          <Search size={20} color={colors.accent} strokeWidth={1.5} />
        </Pressable>
      </View>
      <Rule style={{ marginTop: space.s3 }} />

      <View style={styles.filters}>
        {DAY_FILTERS.map((option) => (
          <Chip
            key={option.value}
            label={option.label}
            selected={day === option.value}
            onPress={() => setDay(option.value)}
          />
        ))}
      </View>
      <Rule strong />

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}

      {featured ? (
        <View style={{ paddingTop: space.s4 }}>
          <Kicker accent style={{ marginBottom: space.s2 }}>
            Tonight&rsquo;s pick
          </Kicker>
          <Plate
            uri={featured.poster_url}
            height={182}
            placeholder={`poster / press shot — ${featured.headline}`}
            accessibilityLabel={`Poster for ${featured.headline}`}
          />
          <View style={styles.featuredHead}>
            <View style={{ flex: 1, paddingRight: space.s3 }}>
              <Heading size="h3" display>
                {featured.headline}
              </Heading>
              <Text style={styles.featuredMeta}>
                {featured.genre_label}
                {featured.venue ? `  ·  ${featured.venue.name}` : ""}
              </Text>
            </View>
            <Text style={styles.featuredTime}>{featured.time_label}</Text>
          </View>
          {featured.short_line ? (
            <Body style={{ marginTop: space.s2 }}>{featured.short_line}</Body>
          ) : null}
          <View style={styles.actions}>
            <Button
              label="Read the listing"
              variant="primary"
              style={{ flex: 1 }}
              onPress={() => navigation.navigate("Show", { eventId: featured.id })}
            />
            <Button
              label=""
              variant="secondary"
              on={featured.saved}
              icon={
                <Bookmark
                  size={17}
                  color={featured.saved ? colors.accent : colors.text}
                  fill={featured.saved ? colors.accent : "transparent"}
                />
              }
              onPress={() => void toggleSave(featured)}
            />
          </View>
          <Rule style={{ marginTop: space.s4 }} />
        </View>
      ) : null}

      {!loading && data && data.count === 0 ? (
        <Empty>Nothing on the bill for that. Clear a filter, or post the show yourself.</Empty>
      ) : (
        sections.map((section) => (
          <View key={section.key}>
            <SectionHead title={section.label} count={section.count_label} />
            {section.events.map((event) => (
              <ListingRow
                key={event.id}
                event={event}
                onPress={() => navigation.navigate("Show", { eventId: event.id })}
              />
            ))}
          </View>
        ))
      )}

      <Text style={styles.colophon}>Set and printed nightly. Corrections to the editor.</Text>
    </Screen>
  );
}

function todayLine(): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "long",
  })
    .format(new Date())
    .toUpperCase();
}

const styles = StyleSheet.create({
  masthead: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    gap: space.s3,
  },
  filters: { flexDirection: "row", flexWrap: "wrap", paddingVertical: space.s3 },
  featuredHead: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    marginTop: space.s3,
  },
  featuredMeta: {
    fontFamily: fonts.bodyItalic,
    fontSize: 12,
    color: ink.soft,
    marginTop: 3,
  },
  featuredTime: { fontFamily: fonts.heading, fontSize: 17, color: colors.text, ...tabular },
  actions: { flexDirection: "row", gap: space.s2, marginTop: space.s3 },
  colophon: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    color: ink.ghost,
    textAlign: "center",
    marginTop: space.s6,
  },
});
