/**
 * 02 — The Plan. What is on near you, on a real street map.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import * as Location from "expo-location";
import MapView, { Marker, PROVIDER_DEFAULT, type Region } from "react-native-maps";
import { queryString, type EventListing, type PlaceSearchResult } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import { Button, Empty, Heading, Kicker, Notice, Screen, SectionHead, Spinner } from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, radius, shadow, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";

interface NearbyResponse {
  events: EventListing[];
  count: number;
  radius_miles: number;
  fallback_nearest: boolean;
}

/** Where the map starts when we know nothing at all: no location permission,
 * no account, no home city. Deliberately the paper's own city rather than a
 * pretend "centre of the world", and only ever a starting frame — the moment
 * a reader signs in with a home city, or taps "use my location", the origin
 * moves and this is never seen again. */
const LAST_RESORT_ORIGIN = { latitude: 41.824, longitude: -71.4128 };
const MAP_HEIGHT = 320;
const INITIAL_REGION: Region = {
  ...LAST_RESORT_ORIGIN,
  latitudeDelta: 0.14,
  longitudeDelta: 0.14,
};

export function PlanScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user } = useAuth();
  const [origin, setOrigin] = useState(LAST_RESORT_ORIGIN);
  const [originIsReader, setOriginIsReader] = useState(false);
  const [originLabel, setOriginLabel] = useState<string | null>(null);
  const [locationNote, setLocationNote] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  const homeCity = user?.home_city?.trim() || null;

  const map = useRef<MapView | null>(null);
  const hasFramed = useRef(false);

  // Centre on the reader's own city before asking for anything.
  //
  // The map used to open on a hard-coded pair of coordinates whatever the
  // reader had told us: someone whose home city was New York, looking at a
  // bill that was entirely New York, was shown "nothing within five miles"
  // and a list of shows 140 miles away. The city is already on their account;
  // this just uses it. Skipped entirely once GPS has given us something
  // better, and never overrides it.
  useEffect(() => {
    if (!homeCity || originIsReader) return;
    let cancelled = false;
    void (async () => {
      const result = await api.get<PlaceSearchResult>(
        `/api/v1/geocode/autocomplete${queryString({ q: homeCity, limit: 1 })}`,
      );
      if (cancelled || !result.ok) return;
      const place = result.data.places[0];
      if (!place) return;
      setOrigin({ latitude: place.latitude, longitude: place.longitude });
      setOriginLabel(place.city ?? homeCity);
      hasFramed.current = false;
    })();
    return () => {
      cancelled = true;
    };
    // `originIsReader` is read, not tracked: once GPS wins, this must not
    // re-run and drag the map back to the city centre.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [homeCity]);

  const { data, error, loading, refreshing, reload } = useResource<NearbyResponse>(
    () =>
      api.get<NearbyResponse>(
        `/api/v1/events/nearby${queryString({ ...origin, radius_miles: 5 })}`,
      ),
    [origin.latitude, origin.longitude],
  );


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
    <Screen onRefresh={reload} refreshing={refreshing}>
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
        <Notice>
          {originIsReader
            ? "Nothing within five miles of you, so these are the nearest upcoming shows."
            : originLabel
              ? `Nothing within five miles of ${originLabel}, so these are the nearest upcoming shows.`
              : "These are the nearest upcoming shows. Tap “use my location”, or set a home city on your account, to centre this on you."}
        </Notice>
      ) : null}

      {/* Apple's own map, not a raster overlay.
       *
       * This used to draw CARTO's basemap through a `UrlTile` with no API
       * key. CARTO now stamps "API KEY REQUIRED" across every unauthenticated
       * tile, so the Map tab shipped covered in someone else's watermark —
       * and using it that way was a terms-of-service problem besides. MapKit
       * is already on the device, needs no key, no attribution plumbing and
       * no third-party request, and it renders in the light style the rest of
       * the paper is set in. */}
      <MapView
        ref={map}
        provider={PROVIDER_DEFAULT}
        style={styles.mapframe}
        initialRegion={INITIAL_REGION}
        showsUserLocation={originIsReader}
        showsMyLocationButton={false}
        toolbarEnabled={false}
        loadingEnabled
        accessibilityLabel="Map of nearby upcoming shows"
      >
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
