/** 13 — The classifieds. Gigs wanted, and the bands for hire. */

import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Plus } from "lucide-react-native";
import {
  GENRES,
  queryString,
  type Artist,
  type Genre,
  type Gig,
  type GigPage,
} from "@live-msc/shared";

import {
  Button,
  Chip,
  Empty,
  Notice,
  SectionHead,
  Spinner,
  Tag,
  inputStyle,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { useDebounced } from "../lib/useDebounced";
import { usePaged } from "../lib/usePaged";
import type { RootNavigation } from "../navigation/types";

const PAGE_SIZE = 30;

type Section = "gigs" | "hire";

export function ClassifiedsScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user } = useAuth();
  const [section, setSection] = useState<Section>("gigs");
  const [city, setCity] = useState("");
  const [genre, setGenre] = useState<Genre | null>(null);
  const debouncedCity = useDebounced(city);

  const gigs = usePaged<Gig>(async (offset) => {
    const result = await api.get<GigPage>(
      `/api/v1/gigs${queryString({
        city: debouncedCity.trim(),
        genre: genre ?? undefined,
        limit: PAGE_SIZE,
        offset,
      })}`,
    );
    if (!result.ok) return result;
    return {
      ok: true,
      status: result.status,
      data: {
        items: result.data?.gigs ?? [],
        total: result.data?.total ?? 0,
        hasMore: result.data?.has_more ?? false,
      },
    };
  }, [debouncedCity, genre]);

  const hire = usePaged<Artist>(async (offset) => {
    const result = await api.get<{ artists: Artist[]; total: number; has_more: boolean }>(
      `/api/v1/artists/for-hire${queryString({
        city: debouncedCity.trim(),
        limit: PAGE_SIZE,
        offset,
      })}`,
    );
    if (!result.ok) return result;
    return {
      ok: true,
      status: result.status,
      data: {
        items: result.data?.artists ?? [],
        total: result.data?.total ?? 0,
        hasMore: result.data?.has_more ?? false,
      },
    };
  }, [debouncedCity]);

  const active = section === "gigs" ? gigs : hire;

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <View style={styles.segments}>
        <Chip label="Gigs" selected={section === "gigs"} onPress={() => setSection("gigs")} />
        <Chip
          label="For hire"
          selected={section === "hire"}
          onPress={() => setSection("hire")}
        />
        <View style={{ flex: 1 }} />
        <Button
          label="Post a gig"
          variant="primary"
          icon={<Plus size={14} color={colors.accent} />}
          style={styles.postButton}
          onPress={() =>
            user ? navigation.navigate("PostGig") : navigation.navigate("SignIn")
          }
        />
      </View>

      <TextInput
        style={[inputStyle, { marginTop: space.s3 }]}
        value={city}
        onChangeText={setCity}
        placeholder="Filter by city"
        placeholderTextColor={ink.faint}
        maxLength={120}
        autoCorrect={false}
        accessibilityLabel="Filter by city"
      />

      {section === "gigs" ? (
        <View style={styles.chips}>
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
      ) : null}

      <SectionHead
        title={section === "gigs" ? "On the board" : "The hire desk"}
        count={
          active.loading
            ? "looking"
            : active.total === 1
              ? "1 listing"
              : `${active.total} listings`
        }
      />

      {active.error ? <Notice tone="error">{active.error}</Notice> : null}
      {active.loading && active.items.length === 0 ? <Spinner label="Reading the board" /> : null}

      {section === "gigs" ? (
        <>
          {!gigs.loading && gigs.items.length === 0 && !gigs.error ? (
            <Empty>Nothing on the board for that. Post the gig yourself.</Empty>
          ) : null}
          {gigs.items.map((gig) => (
            <Pressable
              key={gig.id}
              onPress={() => navigation.navigate("Gig", { gigId: gig.id })}
              accessibilityRole="button"
              accessibilityLabel={`${gig.title}, ${gig.city}`}
              style={({ pressed }) => [styles.row, pressed && { backgroundColor: ink.wash }]}
            >
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.rowTitle} numberOfLines={1}>
                  {gig.title}
                </Text>
                <Text style={styles.rowMeta} numberOfLines={1}>
                  {gig.city}
                  {gig.neighborhood ? `, ${gig.neighborhood}` : ""}
                  {gig.date_label ? `  ·  ${gig.date_label}` : ""}
                </Text>
                {gig.genre_label ? (
                  <View style={styles.tagRow}>
                    <Tag label={gig.genre_label} />
                  </View>
                ) : null}
              </View>
              <Text style={styles.rowPay}>{gig.pay_label ?? "—"}</Text>
            </Pressable>
          ))}
        </>
      ) : (
        <>
          {!hire.loading && hire.items.length === 0 && !hire.error ? (
            <Empty>No bands on the hire desk for that.</Empty>
          ) : null}
          {hire.items.map((artist) => (
            <Pressable
              key={artist.id}
              onPress={() => navigation.navigate("Band", { handle: artist.slug })}
              accessibilityRole="button"
              accessibilityLabel={artist.name}
              style={({ pressed }) => [styles.row, pressed && { backgroundColor: ink.wash }]}
            >
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.rowTitle} numberOfLines={1}>
                  {artist.name}
                </Text>
                <Text style={styles.rowMeta} numberOfLines={2}>
                  {artist.city ?? "City not stated"}
                  {artist.one_liner ? `  ·  ${artist.one_liner}` : ""}
                </Text>
                {artist.style_tags.length > 0 ? (
                  <View style={styles.tagRow}>
                    {artist.style_tags.slice(0, 4).map((tag) => (
                      <Tag key={tag} label={tag} />
                    ))}
                  </View>
                ) : null}
              </View>
            </Pressable>
          ))}
        </>
      )}

      {active.hasMore ? (
        <Button
          label={active.loadingMore ? "Fetching…" : "More"}
          variant="ghost"
          disabled={active.loadingMore}
          onPress={() => void active.loadMore()}
        />
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s4, paddingBottom: space.s8 },
  segments: { flexDirection: "row", alignItems: "center", gap: space.s1 },
  postButton: { minHeight: 38, paddingVertical: space.s1 },
  chips: { flexDirection: "row", flexWrap: "wrap", marginTop: space.s3 },
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  rowTitle: { fontFamily: fonts.heading, fontSize: 16.5, color: colors.text },
  rowMeta: { fontFamily: fonts.body, fontSize: 11.5, lineHeight: 17, color: ink.soft, marginTop: 2 },
  rowPay: { fontFamily: fonts.heading, fontSize: 14, color: colors.text, ...tabular },
  tagRow: { flexDirection: "row", flexWrap: "wrap", marginTop: space.s2 },
});
