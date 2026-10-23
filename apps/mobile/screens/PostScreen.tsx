/** 05 — Post a show. Three fields, and it prints tonight. */

import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import DateTimePicker, { type DateTimePickerEvent } from "@react-native-community/datetimepicker";
import * as ImagePicker from "expo-image-picker";
import { CheckCircle } from "lucide-react-native";
import {
  AGE_OPTIONS,
  GENRES,
  inferContentType,
  isOpenableTicketUrl,
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
  Plate,
  Rule,
  Screen,
  inputStyle,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import type { RootNavigation } from "../navigation/types";

function initialShowTime(): Date {
  const next = new Date();
  next.setDate(next.getDate() + 1);
  next.setHours(21, 0, 0, 0);
  return next;
}

export function PostScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user, artists } = useAuth();

  const [headline, setHeadline] = useState("");
  const [venueName, setVenueName] = useState("");
  const [city, setCity] = useState(user?.home_city ?? "");
  const [startsAt, setStartsAt] = useState(initialShowTime);
  const [pickerMode, setPickerMode] = useState<"date" | "time" | null>(null);
  const [showMore, setShowMore] = useState(false);
  const [price, setPrice] = useState("");
  const [ages, setAges] = useState<AgeRestriction>("21_plus");
  const [genre, setGenre] = useState<Genre>("rock_punk");
  const [note, setNote] = useState("");
  const [ticketUrl, setTicketUrl] = useState("");
  const [poster, setPoster] = useState<ImagePicker.ImagePickerAsset | null>(null);
  // Held so the venue is posted with the exact coordinates the band picked,
  // rather than wherever a later name search happens to land.
  const [venuePlace, setVenuePlace] = useState<Place | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [posted, setPosted] = useState<EventListing | null>(null);
  // Told separately from `error`, which belongs to the form and is not
  // rendered once the confirmation screen replaces it. Without this the
  // band saw "It's on the bill" with a tick and never learned that the
  // photo they chose had not attached.
  const [posterFailed, setPosterFailed] = useState(false);

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
        {posterFailed ? (
          <Notice tone="error">
            The photo did not upload, so the listing is running with stock art.
            Everything else is on the bill. Try adding the photo again from the
            listing in a little while.
          </Notice>
        ) : null}
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
            setPosterFailed(false);
            setHeadline("");
            setNote("");
            setTicketUrl("");
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
    // No permission request before the picker.
    //
    // `launchImageLibraryAsync` presents the system picker, which runs out of
    // process and hands back only the one image the reader chose. It needs no
    // authorisation at all. Calling `requestMediaLibraryPermissionsAsync`
    // first made iOS ask for access to the *entire* photo library — a far
    // larger grant than attaching one picture requires, and one the reader can
    // refuse, at which point the feature was dead for no reason.
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (!result.canceled && result.assets[0]) setPoster(result.assets[0]);
  }

  function changeStart(event: DateTimePickerEvent, selected?: Date) {
    setPickerMode(null);
    if (event.type !== "set" || !selected) return;
    setStartsAt((current) => {
      const next = new Date(current);
      if (pickerMode === "date") {
        next.setFullYear(selected.getFullYear(), selected.getMonth(), selected.getDate());
      } else {
        next.setHours(selected.getHours(), selected.getMinutes(), 0, 0);
      }
      return next;
    });
  }

  async function submit() {
    setError(null);
    setPosterFailed(false);
    if (startsAt.getTime() <= Date.now()) {
      setError("Choose a date and time in the future.");
      return;
    }

    const ticket = ticketUrl.trim();
    if (ticket && !isOpenableTicketUrl(ticket)) {
      setError("The ticket link needs to be a full web address, starting http:// or https://.");
      return;
    }

    setBusy(true);
    try {
      const created = await api.post<{ event: EventListing }>("/api/v1/events", {
        headline: headline.trim(),
        artist_id: artists[0]?.id,
        starts_at: startsAt.toISOString(),
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
        ticket_url: ticket || undefined,
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
            setPosterFailed(true);
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
              <Button
                label={new Intl.DateTimeFormat(undefined, {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                }).format(startsAt)}
                onPress={() => setPickerMode("date")}
              />
            </Field>
          </View>
          <View style={{ flex: 1 }}>
            <Field label="First set">
              <Button
                label={new Intl.DateTimeFormat(undefined, {
                  hour: "numeric",
                  minute: "2-digit",
                }).format(startsAt)}
                onPress={() => setPickerMode("time")}
              />
            </Field>
          </View>
        </View>

        {pickerMode ? (
          <DateTimePicker
            value={startsAt}
            mode={pickerMode}
            minimumDate={pickerMode === "date" ? new Date() : undefined}
            minuteInterval={5}
            onChange={changeStart}
          />
        ) : null}

        <Field label="Photo" note="Choose a poster or show photo. It uploads directly to R2 storage.">
          {poster ? (
            <Plate
              uri={poster.uri}
              height={160}
              placeholder="Show photo"
              accessibilityLabel="Selected show photo"
            />
          ) : null}
          <Button
            label={poster ? "Photo chosen — change" : "Add a photo"}
            style={poster ? { marginTop: space.s2 } : undefined}
            onPress={() => void pickPoster()}
          />
        </Field>
      </View>

      <Rule style={{ marginVertical: space.s4 }} />

      <Button
        label={showMore ? "Add the details — Hide" : "Add the details — Open"}
        variant="ghost"
        onPress={() => setShowMore((open) => !open)}
      />

      {showMore ? (
        <View style={{ marginTop: space.s4 }}>
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

          <Field
            label="Ticket link"
            note="Where tickets are actually sold — the venue's box office, or your ticketing page. Readers are sent straight there."
          >
            <TextInput
              style={inputStyle}
              value={ticketUrl}
              onChangeText={setTicketUrl}
              placeholder="https://dice.fm/event/…"
              placeholderTextColor={ink.faint}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              inputMode="url"
              maxLength={500}
            />
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
        <Text style={styles.previewTime}>
          {new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(
            startsAt,
          )}
        </Text>
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
