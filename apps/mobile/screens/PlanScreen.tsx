/**
 * 02 — The Plan. What is on near you, on a real street map.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import * as Location from "expo-location";
import MapView, { Marker, UrlTile, type Region } from "react-native-maps";
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
  fallback_nearest: boolean;
}

const FALLBACK = { latitude: 41.824, longitude: -71.4128 };
const MAP_HEIGHT = 320;
const INITIAL_REGION: Region = { ...FALLBACK, latitudeDelta: 0.14, longitudeDelta: 0.14 };
const TILE_URL = "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png";

export function PlanScreen() {
  const navigation = useNavigation<RootNavigation>();
  const [origin, setOrigin] = useState(FALLBACK);
  const [originIsReader, setOriginIsReader] = useState(false);
  const [locationNote, setLocationNote] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  const { data, error, loading } = useResource<NearbyResponse>(
    () =>
      api.get<NearbyResponse>(
        `/api/v1/events/nearby${queryString({ ...origin, radius_miles: 5 })}`,
      ),
    [origin.latitude, origin.longitude],
  );

  const map = useRef<MapView | null>(null);
  const hasFramed = useRef(false);

  useEffect(() => {
    const located = (data?.events ?? []).filter(
      (event) => event.venue?.latitude != null && event.venue?.longitude != null,
    );
    if (!map.current || located.length === 0 || hasFramed.current) return;
    hasFramed.current = true;
    map.current.fitToCoordinates(
      located.map((event) => ({
        latitude: event.venue!.latitude!,
        longitude: event.venue!.longitude!,
      })),
      { edgePadding: { top: 45, right: 45, bottom: 45, left: 45 }, animated: false },
    );
  }, [data]);

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
      setOriginIsReader(true);
      hasFramed.current = false;
      map.current?.animateToRegion(
        {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          latitudeDelta: 0.14,
          longitudeDelta: 0.14,
        },
        400,
      );
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
            {data
              ? data.fallback_nearest
                ? `${data.count} nearest available`
                : `${data.count} within ${data.radius_miles} miles`
              : "Shows near you"}
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

      {data?.fallback_nearest ? (
        <Notice>Nothing within five miles, so these are the nearest upcoming shows.</Notice>
      ) : null}

      <MapView
        ref={map}
        style={styles.mapframe}
        initialRegion={INITIAL_REGION}
        mapType="none"
        showsUserLocation={originIsReader}
        showsMyLocationButton={false}
        toolbarEnabled={false}
        loadingEnabled
        accessibilityLabel="Map of nearby upcoming shows"
      >
        <UrlTile urlTemplate={TILE_URL} maximumZ={19} flipY={false} />
        {(data?.events ?? []).map((event) =>
          event.venue?.latitude != null && event.venue.longitude != null ? (
          <Marker
            key={event.id}
            coordinate={{
              latitude: event.venue.latitude,
              longitude: event.venue.longitude,
            }}
            title={event.headline}
            description={`${event.venue.name} · ${event.day_label} ${event.time_label}`}
            onPress={() => navigation.navigate("Show", { eventId: event.id })}
            accessibilityLabel={`${event.pin_number}. ${event.headline} at ${event.venue?.name}`}
          >
            <View style={styles.pin}>
              <Text style={styles.pinLabel}>{event.pin_number}</Text>
            </View>
          </Marker>
          ) : null,
        )}
      </MapView>

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
        <Empty>No located shows are scheduled in the next fortnight.</Empty>
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
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    borderRadius: radius.md,
    overflow: "hidden",
  },
  pin: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "rgba(32,31,29,0.45)",
    ...shadow.sm,
  },
  pinLabel: { fontFamily: fonts.heading, fontSize: 12, color: ink.soft, ...tabular },
});
