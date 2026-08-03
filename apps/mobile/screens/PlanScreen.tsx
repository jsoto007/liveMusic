/**
 * 02 — The Plan. What is on near you, drawn rather than mapped.
 *
 * The pins are projected from real venue coordinates onto a drawn grid, so
 * their relative geography holds without a tile server — which also keeps the
 * reader's location out of a third party's logs.
 */

import { useCallback, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import * as Location from "expo-location";
import { queryString, type EventListing } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import { Button, Empty, Heading, Kicker, Notice, Screen, SectionHead, Spinner } from "../components/ui";
import { api } from "../lib/auth";
import { colors, fonts, ink, radius, shadow, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";

interface NearbyResponse {
  events: EventListing[];
  count: number;
  radius_miles: number;
}

const FALLBACK = { latitude: 41.824, longitude: -71.4128 };
const MAP_HEIGHT = 320;

interface Placed {
  event: EventListing;
  left: number;
  top: number;
}

/**
 * Equirectangular projection into percentage offsets, padded to 8–92% so a
 * pin at the extreme still sits inside the frame.
 */
function placePins(events: EventListing[]): Placed[] {
  const located = events.filter(
    (event) => event.venue?.latitude != null && event.venue?.longitude != null,
  );
  if (located.length === 0) return [];

  const lats = located.map((event) => event.venue!.latitude!);
  const lons = located.map((event) => event.venue!.longitude!);
  const minLat = Math.min(...lats);
  const minLon = Math.min(...lons);
  const latSpan = Math.max(...lats) - minLat;
  const lonSpan = Math.max(...lons) - minLon;

  // A single venue gives a zero span; centre it rather than dividing by zero.
  const scale = (value: number, min: number, span: number) =>
    span < 1e-9 ? 50 : 8 + ((value - min) / span) * 84;

  return located.map((event) => ({
    event,
    left: scale(event.venue!.longitude!, minLon, lonSpan),
    // Latitude grows north; screen coordinates grow down.
    top: 100 - scale(event.venue!.latitude!, minLat, latSpan),
  }));
}

export function PlanScreen() {
  const navigation = useNavigation<RootNavigation>();
  const [origin, setOrigin] = useState(FALLBACK);
  const [locationNote, setLocationNote] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  const { data, error, loading } = useResource<NearbyResponse>(
    () =>
      api.get<NearbyResponse>(
        `/api/v1/events/nearby${queryString({ ...origin, radius_miles: 5 })}`,
      ),
    [origin.latitude, origin.longitude],
  );

  const pins = useMemo(() => placePins(data?.events ?? []), [data]);

  const requestLocation = useCallback(async () => {
    setLocating(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        // Declining is a legitimate answer, not an error to nag about.
        setLocationNote("Showing the city centre instead.");
        return;
      }
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      setOrigin({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      });
      setLocationNote(null);
    } catch {
      setLocationNote("Could not read your location. Showing the city centre.");
    } finally {
      setLocating(false);
    }
  }, []);

  // Deliberately NOT requested on mount. Prompting for location the instant a
  // screen opens, before the reader has any reason to say yes, is how an app
  // trains people to refuse it. The city centre is shown until they ask.

  return (
    <Screen>
      <View style={styles.head}>
        <View style={{ flex: 1 }}>
          <Heading size="h2" display>
            The Plan
          </Heading>
          <Kicker style={{ marginTop: 5 }}>
            {data ? `${data.count} within ${data.radius_miles} miles` : "Shows near you"}
          </Kicker>
        </View>
        <Button
          label={locating ? "Locating…" : "Use my location"}
          onPress={() => void requestLocation()}
          disabled={locating}
        />
      </View>

      {locationNote ? <Notice>{locationNote}</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}

      <View style={styles.mapframe}>
        {/* The drawn grid: horizontal and vertical hairlines, no tiles. */}
        {Array.from({ length: 11 }, (_, index) => (
          <View key={`h${index}`} style={[styles.gridLine, { top: index * 30 }]} />
        ))}
        {Array.from({ length: 13 }, (_, index) => (
          <View key={`v${index}`} style={[styles.gridLineV, { left: index * 30 }]} />
        ))}

        {pins.map(({ event, left, top }) => (
          <Pressable
            key={event.id}
            onPress={() => navigation.navigate("Show", { eventId: event.id })}
            accessibilityRole="button"
            accessibilityLabel={`${event.pin_number}. ${event.headline} at ${event.venue?.name}`}
            style={[
              styles.pin,
              { left: `${left}%`, top: (top / 100) * MAP_HEIGHT - 14 },
            ]}
          >
            <Text style={styles.pinLabel}>{event.pin_number}</Text>
          </Pressable>
        ))}

        <View style={styles.scale}>
          <View style={styles.scaleBar} />
          <Text style={styles.scaleLabel}>½ MI</Text>
        </View>
      </View>

      <SectionHead title="Nearest first" count="Next fourteen days" />

      {loading && !data ? <Spinner /> : null}
      {data?.events.map((event) => (
        <ListingRow
          key={event.id}
          event={event}
          leading={String(event.pin_number ?? "")}
          showNote={false}
          onPress={() => navigation.navigate("Show", { eventId: event.id })}
        />
      ))}
      {!loading && data?.count === 0 ? (
        <Empty>Nothing within five miles this fortnight.</Empty>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  head: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    gap: space.s3,
    marginBottom: space.s3,
  },
  mapframe: {
    height: MAP_HEIGHT,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    borderRadius: radius.md,
    overflow: "hidden",
  },
  gridLine: {
    position: "absolute",
    left: 0,
    right: 0,
    height: StyleSheet.hairlineWidth,
    backgroundColor: ink.divider,
  },
  gridLineV: {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: StyleSheet.hairlineWidth,
    backgroundColor: ink.divider,
  },
  pin: {
    position: "absolute",
    width: 28,
    height: 28,
    marginLeft: -14,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "rgba(32,31,29,0.45)",
    ...shadow.sm,
  },
  pinLabel: { fontFamily: fonts.heading, fontSize: 12, color: ink.soft, ...tabular },
  scale: {
    position: "absolute",
    right: 12,
    bottom: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    paddingVertical: 5,
    paddingHorizontal: 9,
  },
  scaleBar: { width: 26, height: 1, backgroundColor: colors.text },
  scaleLabel: { fontFamily: fonts.body, fontSize: 9.5, letterSpacing: 1, color: ink.soft },
});
