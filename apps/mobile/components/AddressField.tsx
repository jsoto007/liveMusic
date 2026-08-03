/**
 * An address field with suggestions from the geocoding proxy.
 *
 * Same contract as the web component: it degrades to a plain text field when
 * LocationIQ is unconfigured or unreachable, because an address input that
 * stops accepting typed text because a third party is down is worse than no
 * autocomplete at all.
 */

import { useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { MapPin } from "lucide-react-native";
import { queryString, type Place, type PlaceSearchResult } from "@live-msc/shared";

import { api } from "../lib/auth";
import { colors, fonts, ink, radius, shadow, space } from "../lib/theme";
import { Field, inputStyle } from "./ui";

const DEBOUNCE_MS = 320;
const MIN_QUERY = 3;

export function AddressField({
  label,
  value,
  onChangeText,
  onSelect,
  placeholder,
  note,
  countries,
  maxLength = 300,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  onSelect: (place: Place) => void;
  placeholder?: string;
  note?: string;
  countries?: string;
  maxLength?: number;
}) {
  const [places, setPlaces] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [unavailable, setUnavailable] = useState(false);

  const skipNextLookup = useRef(false);
  const generation = useRef(0);

  useEffect(() => {
    if (unavailable) return;
    if (skipNextLookup.current) {
      skipNextLookup.current = false;
      return;
    }

    const term = value.trim();
    if (term.length < MIN_QUERY) {
      setPlaces([]);
      setOpen(false);
      return;
    }

    const current = ++generation.current;
    const timer = setTimeout(() => {
      void api
        .get<PlaceSearchResult>(
          `/api/v1/geocode/autocomplete${queryString({ q: term, countries })}`,
        )
        .then((result) => {
          // A slower earlier response must not overwrite a newer one.
          if (generation.current !== current) return;
          if (!result.ok || !result.data) return;
          if (!result.data.configured) {
            setUnavailable(true);
            return;
          }
          setPlaces(result.data.places);
          setOpen(result.data.places.length > 0);
        });
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [value, countries, unavailable]);

  function choose(place: Place) {
    skipNextLookup.current = true;
    onChangeText(place.name || place.label);
    onSelect(place);
    setOpen(false);
    setPlaces([]);
  }

  return (
    <Field label={label} note={note}>
      <View style={styles.inputRow}>
        <MapPin size={15} color={ink.faint} />
        <TextInput
          style={[inputStyle, styles.input]}
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={ink.faint}
          maxLength={maxLength}
          autoCorrect={false}
          accessibilityLabel={label}
        />
      </View>

      {open && places.length > 0 ? (
        <View style={styles.suggestions} accessibilityRole="list">
          {places.map((place, index) => (
            <Pressable
              key={`${place.label}-${index}`}
              onPress={() => choose(place)}
              accessibilityRole="button"
              accessibilityLabel={place.label}
              style={({ pressed }) => [
                styles.suggestion,
                index === places.length - 1 && { borderBottomWidth: 0 },
                pressed && { backgroundColor: ink.accentWash },
              ]}
            >
              <Text style={styles.suggestionName}>{place.name || place.label}</Text>
              <Text style={styles.suggestionDetail} numberOfLines={2}>
                {place.label}
              </Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </Field>
  );
}

const styles = StyleSheet.create({
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    borderRadius: radius.md,
    paddingLeft: space.s3,
  },
  input: { flex: 1, borderWidth: 0, paddingHorizontal: 0 },
  // The one place elevation is used: the list has to read as floating above
  // the field below it, and a hairline alone will not do that.
  suggestions: {
    marginTop: 4,
    backgroundColor: colors.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    borderRadius: radius.md,
    overflow: "hidden",
    ...shadow.md,
  },
  suggestion: {
    paddingVertical: space.s2,
    paddingHorizontal: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  suggestionName: { fontFamily: fonts.heading, fontSize: 15, color: colors.text },
  suggestionDetail: {
    fontFamily: fonts.body,
    fontSize: 11.5,
    lineHeight: 16,
    color: ink.soft,
    marginTop: 2,
  },
});
