/** 15 — Post a gig. The ask, the room, the pay — onto the board. */

import { useState } from "react";
import { ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import DateTimePicker, { type DateTimePickerEvent } from "@react-native-community/datetimepicker";
import { CheckCircle } from "lucide-react-native";
import { GENRES, type Genre, type Gig } from "@live-msc/shared";

import {
  Body,
  Button,
  Chip,
  Field,
  Heading,
  Notice,
  Rule,
  inputStyle,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, space } from "../lib/theme";
import type { RootNavigation } from "../navigation/types";

function initialGigTime(): Date {
  const next = new Date();
  next.setDate(next.getDate() + 7);
  next.setHours(21, 0, 0, 0);
  return next;
}

export function PostGigScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user } = useAuth();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [city, setCity] = useState(user?.home_city ?? "");
  const [neighborhood, setNeighborhood] = useState("");
  const [venueName, setVenueName] = useState("");
  const [startsAt, setStartsAt] = useState<Date | null>(null);
  const [pickerMode, setPickerMode] = useState<"date" | "time" | null>(null);
  const [pay, setPay] = useState("");
  const [payNote, setPayNote] = useState("");
  const [genre, setGenre] = useState<Genre | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [posted, setPosted] = useState<Gig | null>(null);

  if (!user) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Heading size="h2" display>
          Post a gig
        </Heading>
        <Notice>You need an account to put a gig on the board.</Notice>
        <Button label="Sign in" variant="primary" onPress={() => navigation.navigate("SignIn")} />
      </ScrollView>
    );
  }

  if (posted) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <View style={{ alignItems: "center", marginTop: space.s8 }}>
          <CheckCircle size={34} strokeWidth={1.2} color={colors.accent} />
          <Heading size="h2" display style={{ marginTop: space.s3 }}>
            It&rsquo;s on the board
          </Heading>
          <Body muted style={{ textAlign: "center", marginTop: space.s2 }}>
            Bands can raise a hand from the classifieds now.
          </Body>
        </View>
        <Button
          label="See the listing"
          variant="primary"
          style={{ marginTop: space.s6 }}
          onPress={() => navigation.navigate("Gig", { gigId: posted.id })}
        />
        <Button
          label="Post another"
          variant="ghost"
          style={{ marginTop: space.s2 }}
          onPress={() => {
            setPosted(null);
            setTitle("");
            setDescription("");
            setNeighborhood("");
            setVenueName("");
            setStartsAt(null);
            setPay("");
            setPayNote("");
            setGenre(null);
          }}
        />
      </ScrollView>
    );
  }

  // Same reading as the door price: empty = not stated, "free" = 0.
  const payCents = (() => {
    const trimmed = pay.trim().replace(/^\$/, "");
    if (!trimmed) return undefined;
    if (/^free$/i.test(trimmed)) return 0;
    const value = Number(trimmed);
    return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : undefined;
  })();

  function changeStart(event: DateTimePickerEvent, selected?: Date) {
    setPickerMode(null);
    if (event.type !== "set" || !selected) return;
    setStartsAt((current) => {
      const base = current ?? initialGigTime();
      const next = new Date(base);
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
    setBusy(true);
    try {
      const result = await api.post<{ gig: Gig }>("/api/v1/gigs", {
        title: title.trim(),
        description: description.trim(),
        city: city.trim(),
        neighborhood: neighborhood.trim() || undefined,
        venue_name: venueName.trim() || undefined,
        starts_at: startsAt ? startsAt.toISOString() : undefined,
        timezone: startsAt
          ? Intl.DateTimeFormat().resolvedOptions().timeZone
          : undefined,
        pay_cents: payCents,
        pay_note: payNote.trim() || undefined,
        genre: genre ?? undefined,
      });
      if (!result.ok || !result.data) {
        setError(result.ok ? "The gig could not be posted." : result.error);
        return;
      }
      setPosted(result.data.gig);
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Heading size="h2" display>
        Post a gig
      </Heading>
      <Text style={styles.tagline}>Say what you need; the bands come to you.</Text>

      {error ? <Notice tone="error">{error}</Notice> : null}

      <View style={{ marginTop: space.s6 }}>
        <Field label="What you need">
          <TextInput
            style={inputStyle}
            value={title}
            onChangeText={setTitle}
            placeholder="Jazz trio for a Friday residency"
            placeholderTextColor={ink.faint}
            maxLength={160}
          />
        </Field>

        <Field label="The details">
          <TextInput
            style={[inputStyle, { minHeight: 96, textAlignVertical: "top" }]}
            value={description}
            onChangeText={setDescription}
            placeholder="The room, the night, the crowd, what you're listening for."
            placeholderTextColor={ink.faint}
            multiline
            maxLength={4000}
          />
        </Field>

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
            <Field label="Neighborhood">
              <TextInput
                style={inputStyle}
                value={neighborhood}
                onChangeText={setNeighborhood}
                placeholder="Optional"
                placeholderTextColor={ink.faint}
                maxLength={120}
              />
            </Field>
          </View>
          <View style={{ flex: 1 }}>
            <Field label="Venue">
              <TextInput
                style={inputStyle}
                value={venueName}
                onChangeText={setVenueName}
                placeholder="Optional"
                placeholderTextColor={ink.faint}
                maxLength={160}
              />
            </Field>
          </View>
        </View>

        {startsAt ? (
          <>
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
                <Field label="Start">
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
            <Button
              label="No date — remove it"
              variant="ghost"
              onPress={() => setStartsAt(null)}
            />
          </>
        ) : (
          <Field label="When" note="Leave it off if the date is still to be arranged.">
            <Button label="Add a date" onPress={() => setStartsAt(initialGigTime())} />
          </Field>
        )}

        {pickerMode && startsAt ? (
          <DateTimePicker
            value={startsAt}
            mode={pickerMode}
            minimumDate={pickerMode === "date" ? new Date() : undefined}
            minuteInterval={5}
            onChange={changeStart}
          />
        ) : null}

        <Rule style={{ marginVertical: space.s4 }} />

        <View style={{ flexDirection: "row", gap: space.s3 }}>
          <View style={{ flex: 1 }}>
            <Field label="Pay">
              <TextInput
                style={inputStyle}
                value={pay}
                onChangeText={setPay}
                placeholder="150, or Free"
                placeholderTextColor={ink.faint}
                keyboardType="decimal-pad"
              />
            </Field>
          </View>
          <View style={{ flex: 1 }}>
            <Field label="Pay note">
              <TextInput
                style={inputStyle}
                value={payNote}
                onChangeText={setPayNote}
                placeholder="plus the door"
                placeholderTextColor={ink.faint}
                maxLength={140}
              />
            </Field>
          </View>
        </View>

        <Field label="Genre">
          <View style={styles.chipRow}>
            {GENRES.map((option) => (
              <Chip
                key={option.value}
                label={option.label}
                selected={genre === option.value}
                onPress={() =>
                  setGenre((current) => (current === option.value ? null : option.value))
                }
              />
            ))}
          </View>
        </Field>
      </View>

      <Button
        label={busy ? "Sending…" : "Put it on the board"}
        variant="primary"
        disabled={busy || !title.trim() || !description.trim() || !city.trim()}
        style={{ marginTop: space.s4 }}
        onPress={() => void submit()}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s4, paddingBottom: space.s8 },
  tagline: { fontFamily: fonts.bodyItalic, fontSize: 11, color: ink.soft, marginTop: 6 },
  chipRow: { flexDirection: "row", flexWrap: "wrap" },
});
