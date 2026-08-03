/** 05 — Post a show. Three fields, and it prints tonight. */

import { useState } from "react";
import { Platform, StyleSheet, Text, TextInput, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import { CheckCircle } from "lucide-react-native";
import {
  AGE_OPTIONS,
  GENRES,
  inferContentType,
  uploadDirect,
  type AgeRestriction,
  type EventListing,
  type Genre,
  type Place,
} from "@live-msc/shared";

import { AddressField } from "../components/AddressField";
import {
  Body,
  Button,
  Chip,
  Field,
  Heading,
  Kicker,
  Notice,
  Rule,
  Screen,
  inputStyle,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import type { RootNavigation } from "../navigation/types";

/**
 * Build the instant from the date and time the band typed.
 *
 * Constructed from the parts so the device's own zone is the reference —
 * which is what someone means when they type "9pm" for a room down the road.
 */
function toIsoInstant(date: string, time: string): string | null {
  const dateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date.trim());
  const timeMatch = /^(\d{1,2}):(\d{2})$/.exec(time.trim());
  if (!dateMatch || !timeMatch) return null;

  const [, year, month, day] = dateMatch.map(Number) as [unknown, number, number, number];
  const [, hour, minute] = timeMatch.map(Number) as [unknown, number, number];
  if (hour > 23 || minute > 59 || month < 1 || month > 12 || day < 1 || day > 31) return null;

  const local = new Date(year, month - 1, day, hour, minute);
  // Reject a date the calendar rolled over (e.g. 31 February).
  if (local.getMonth() !== month - 1 || local.getDate() !== day) return null;
  return local.toISOString();
}

export function PostScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user, artists } = useAuth();

  const [headline, setHeadline] = useState("");
  const [venueName, setVenueName] = useState("");
  const [city, setCity] = useState(user?.home_city ?? "");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("21:00");
  const [showMore, setShowMore] = useState(false);
  const [price, setPrice] = useState("");
  const [ages, setAges] = useState<AgeRestriction>("21_plus");
  const [genre, setGenre] = useState<Genre>("rock_punk");
  const [note, setNote] = useState("");
  const [poster, setPoster] = useState<ImagePicker.ImagePickerAsset | null>(null);
  // Held so the venue is posted with the exact coordinates the band picked,
  // rather than wherever a later name search happens to land.
  const [venuePlace, setVenuePlace] = useState<Place | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [posted, setPosted] = useState<EventListing | null>(null);

  if (!user) {
    return (
      <Screen>
        <Heading size="h2" display>
          Post a show
        </Heading>
        <Notice>You need an account to put a show on the bill.</Notice>
        <Button label="Sign in" variant="primary" onPress={() => navigation.navigate("SignIn")} />
      </Screen>
    );
  }

  if (posted) {
    return (
      <Screen>
        <View style={{ alignItems: "center", marginTop: space.s8 }}>
          <CheckCircle size={34} strokeWidth={1.2} color={colors.accent} />
          <Heading size="h2" display style={{ marginTop: space.s3 }}>
            It&rsquo;s on the bill
          </Heading>
          <Body muted style={{ textAlign: "center", marginTop: space.s2 }}>
            Set into the listings and pushed to everyone following you.
          </Body>
        </View>
        <Button
          label="See it in the bill"
          variant="primary"
          style={{ marginTop: space.s6 }}
          onPress={() => navigation.navigate("Show", { eventId: posted.id })}
        />
        <Button
          label="Post another"
          variant="ghost"
          style={{ marginTop: space.s2 }}
          onPress={() => {
            setPosted(null);
            setHeadline("");
            setNote("");
            setPoster(null);
            setVenuePlace(null);
          }}
        />
      </Screen>
    );
  }

  const priceCents = (() => {
    const trimmed = price.trim().replace(/^\$/, "");
    if (!trimmed) return undefined;
    if (/^free$/i.test(trimmed)) return 0;
    const value = Number(trimmed);
    return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : undefined;
  })();

  async function pickPoster() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError("Photo access is needed to attach a poster.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (!result.canceled && result.assets[0]) setPoster(result.assets[0]);
  }

  async function submit() {
    setError(null);
    const startsAt = toIsoInstant(date, time);
    if (!startsAt) {
      setError("Enter the date as YYYY-MM-DD and the time as HH:MM.");
      return;
    }

    setBusy(true);
    try {
      const created = await api.post<{ event: EventListing }>("/api/v1/events", {
        headline: headline.trim(),
        artist_id: artists[0]?.id,
        starts_at: startsAt,
        venue: {
          name: venueName.trim(),
          city: city.trim(),
          address: venuePlace?.label,
          latitude: venuePlace?.latitude,
          longitude: venuePlace?.longitude,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        },
        genre,
        price_cents: priceCents,
        age_restriction: ages,
        short_line: note.trim() || undefined,
        publish: true,
      });

      if (!created.ok || !created.data) {
        setError(created.ok ? "The show could not be posted." : created.error);
        return;
      }

      const event = created.data.event;

      // The poster is a separate, optional step — a failed image upload must
      // not lose the listing the band just wrote.
      if (poster) {
        const name = poster.fileName ?? "poster.jpg";
        const contentType = inferContentType(name, poster.mimeType);
        if (contentType) {
          try {
            await uploadDirect(
              api,
              {
                purpose: "event_poster",
                targetId: event.id,
                contentType,
                sizeBytes: poster.fileSize,
              },
              // React Native's FormData takes a {uri, name, type} descriptor
              // and streams the file itself — the bytes never enter JS memory.
              { uri: poster.uri, name, type: contentType },
            );
          } catch {
            setError("The show is posted, but the poster did not upload. You can add it later.");
          }
        }
      }

      setPosted(event);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Heading size="h2" display>
        Post a show
      </Heading>
      <Text style={styles.tagline}>Three fields. It prints tonight.</Text>

      {error ? <Notice tone="error">{error}</Notice> : null}

      <View style={{ marginTop: space.s6 }}>
        <Field label="Who's playing">
          <TextInput
            style={inputStyle}
            value={headline}
            onChangeText={setHeadline}
            placeholder="Bloodroot Choir"
            placeholderTextColor={ink.faint}
            maxLength={160}
          />
        </Field>

        <AddressField
          label="Where"
          value={venueName}
          onChangeText={(next) => {
            setVenueName(next);
            // Typing again invalidates the pin we had.
            setVenuePlace(null);
          }}
          onSelect={(place) => {
            setVenuePlace(place);
            if (place.city) setCity(place.city);
          }}
          placeholder="Dusk, or 301 Harris Ave"
          note="Pick the room and it lands on the map."
          maxLength={160}
        />

        <Field label="City">
          <TextInput
            style={inputStyle}
            value={city}
            onChangeText={setCity}
            placeholder="Providence"
            placeholderTextColor={ink.faint}
            maxLength={120}
          />
        </Field>

        <View style={{ flexDirection: "row", gap: space.s3 }}>
          <View style={{ flex: 1 }}>
            <Field label="Date">
              <TextInput
                style={inputStyle}
                value={date}
                onChangeText={setDate}
                placeholder="2026-08-14"
                placeholderTextColor={ink.faint}
                keyboardType={Platform.OS === "ios" ? "numbers-and-punctuation" : "default"}
                maxLength={10}
              />
            </Field>
          </View>
          <View style={{ flex: 1 }}>
            <Field label="First set">
              <TextInput
                style={inputStyle}
                value={time}
                onChangeText={setTime}
                placeholder="21:00"
                placeholderTextColor={ink.faint}
                keyboardType={Platform.OS === "ios" ? "numbers-and-punctuation" : "default"}
                maxLength={5}
              />
            </Field>
          </View>
        </View>
      </View>

      <Rule style={{ marginVertical: space.s4 }} />

      <Button
        label={showMore ? "Add the details — Hide" : "Add the details — Open"}
        variant="ghost"
        onPress={() => setShowMore((open) => !open)}
      />

      {showMore ? (
        <View style={{ marginTop: space.s4 }}>
          <Field label="Poster" note="Uploaded straight to storage — it never passes through our servers.">
            <Button
              label={poster ? "Poster chosen — change" : "Choose a poster"}
              onPress={() => void pickPoster()}
            />
          </Field>

          <View style={{ flexDirection: "row", gap: space.s3 }}>
            <View style={{ flex: 1 }}>
              <Field label="Door price">
                <TextInput
                  style={inputStyle}
                  value={price}
                  onChangeText={setPrice}
                  placeholder="10, or Free"
                  placeholderTextColor={ink.faint}
                  keyboardType="decimal-pad"
                />
              </Field>
            </View>
          </View>

          <Field label="Ages">
            <View style={styles.chipRow}>
              {AGE_OPTIONS.map((option) => (
                <Chip
                  key={option.value}
                  label={option.label}
                  selected={ages === option.value}
                  onPress={() => setAges(option.value)}
                />
              ))}
            </View>
          </Field>

          <Field label="Genre">
            <View style={styles.chipRow}>
              {GENRES.map((option) => (
                <Chip
                  key={option.value}
                  label={option.label}
                  selected={genre === option.value}
                  onPress={() => setGenre(option.value)}
                />
              ))}
            </View>
          </Field>

          <Field label="A line for the paper">
            <TextInput
              style={[inputStyle, { minHeight: 72, textAlignVertical: "top" }]}
              value={note}
              onChangeText={setNote}
              placeholder="One sentence. Who you sound like, what the room will be."
              placeholderTextColor={ink.faint}
              multiline
              maxLength={300}
            />
          </Field>
        </View>
      ) : null}

      <Rule style={{ marginVertical: space.s4 }} />

      <Kicker>How it will read</Kicker>
      <Rule strong style={{ marginTop: 4 }} />
      <View style={styles.previewRow}>
        <Text style={styles.previewTime}>{time || "—:—"}</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.previewArtist}>{headline.trim() || "Your band"}</Text>
          <Text style={styles.previewMeta}>
            {GENRES.find((option) => option.value === genre)?.label}
            {venueName.trim() ? `  ·  ${venueName.trim()}` : "  ·  Venue"}
          </Text>
        </View>
        <Text style={styles.previewPrice}>
          {priceCents === undefined ? "—" : priceCents === 0 ? "Free" : `$${priceCents / 100}`}
        </Text>
      </View>

      <Button
        label={busy ? "Sending…" : "Send it to press"}
        variant="primary"
        disabled={busy}
        style={{ marginTop: space.s4 }}
        onPress={() => void submit()}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  tagline: { fontFamily: fonts.bodyItalic, fontSize: 11, color: ink.soft, marginTop: 6 },
  chipRow: { flexDirection: "row", flexWrap: "wrap" },
  previewRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  previewTime: { width: 62, fontFamily: fonts.heading, fontSize: 14, color: ink.soft, ...tabular },
  previewArtist: { fontFamily: fonts.heading, fontSize: 17, color: colors.text },
  previewMeta: { fontFamily: fonts.body, fontSize: 11.5, color: ink.soft, marginTop: 2 },
  previewPrice: { fontFamily: fonts.heading, fontSize: 14, color: colors.text, ...tabular },
});
