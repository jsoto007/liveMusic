/** 03 — Look it up. Search across acts, rooms and neighbourhoods. */

import { useEffect, useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Search } from "lucide-react-native";
import { GENRES, queryString, type EventListing, type Genre } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import { Chip, Empty, Notice, Screen, SectionHead, Spinner, inputStyle } from "../components/ui";
import { api } from "../lib/auth";
import { ink, radius, space } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";

function useDebounced<T>(value: T, delayMs = 300): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return settled;
}

export function SearchScreen() {
  const navigation = useNavigation<RootNavigation>();
  const [term, setTerm] = useState("");
  const [genres, setGenres] = useState<Genre[]>([]);
  const debounced = useDebounced(term);

  const { data, error, loading } = useResource<{ events: EventListing[]; count: number }>(
    () =>
      api.get<{ events: EventListing[]; count: number }>(
        `/api/v1/events${queryString({ q: debounced, genre: genres })}`,
      ),
    [debounced, genres.join(",")],
  );

  const toggleGenre = (genre: Genre) =>
    setGenres((current) =>
      current.includes(genre) ? current.filter((g) => g !== genre) : [...current, genre],
    );

  const count = data?.count ?? 0;

  return (
    <Screen>
      <View style={styles.searchField}>
        <Search size={16} color={ink.faint} />
        <TextInput
          style={[inputStyle, styles.searchInput]}
          value={term}
          onChangeText={setTerm}
          placeholder="Band, venue or genre"
          placeholderTextColor={ink.faint}
          accessibilityLabel="Search listings"
          maxLength={80}
          autoCorrect={false}
          returnKeyType="search"
        />
      </View>

      <View style={styles.chips}>
        {GENRES.map((genre) => (
          <Chip
            key={genre.value}
            label={genre.label}
            selected={genres.includes(genre.value)}
            onPress={() => toggleGenre(genre.value)}
          />
        ))}
      </View>

      <SectionHead
        title="Results"
        count={loading ? "searching" : count === 1 ? "1 show" : `${count} shows`}
      />

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner label="Looking" /> : null}

      {data?.events.map((event) => (
        <ListingRow
          key={event.id}
          event={event}
          showNote={false}
          onPress={() => navigation.navigate("Show", { eventId: event.id })}
        />
      ))}

      {!loading && data && count === 0 ? (
        <Empty>Nothing on the bill for that. Clear a filter, or post the show yourself.</Empty>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  searchField: {
    marginTop: space.s2,
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    borderRadius: radius.md,
    paddingHorizontal: space.s3,
  },
  searchInput: { flex: 1, borderWidth: 0, paddingHorizontal: 0 },
  chips: { flexDirection: "row", flexWrap: "wrap", marginTop: space.s3 },
});
