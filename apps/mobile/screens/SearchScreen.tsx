/** 03 — Look it up. Acts, rooms, neighbourhoods — and the people reading. */

import { useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Search } from "lucide-react-native";
import {
  GENRES,
  queryString,
  type EventListing,
  type Genre,
  type PeoplePage,
} from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import { FollowButton, UserRow } from "../components/UserRow";
import {
  Button,
  Chip,
  Empty,
  Notice,
  Screen,
  SectionHead,
  Spinner,
  inputStyle,
} from "../components/ui";
import { api } from "../lib/auth";
import { ink, radius, space } from "../lib/theme";
import { useDebounced } from "../lib/useDebounced";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";

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

  // People need at least two characters; under that the server refuses, so
  // the page simply shows no people section rather than an error.
  const people = useResource<PeoplePage>(
    () =>
      debounced.trim().length >= 2
        ? api.get<PeoplePage>(
            `/api/v1/users/search${queryString({ q: debounced.trim(), limit: 10 })}`,
          )
        : Promise.resolve({
            ok: true as const,
            data: { people: [], total: 0, has_more: false },
            status: 200,
          }),
    [debounced],
  );

  const toggleGenre = (genre: Genre) =>
    setGenres((current) =>
      current.includes(genre) ? current.filter((g) => g !== genre) : [...current, genre],
    );

  const count = data?.count ?? 0;
  const foundPeople = people.data?.people ?? [];

  return (
    <Screen>
      <View style={styles.searchField}>
        <Search size={16} color={ink.faint} />
        <TextInput
          style={[inputStyle, styles.searchInput]}
          value={term}
          onChangeText={setTerm}
          placeholder="Band, venue, genre or person"
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

      <Button
        label="Browse the classifieds →"
        variant="ghost"
        onPress={() => navigation.navigate("Classifieds")}
      />

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

      {foundPeople.length > 0 ? (
        <>
          <SectionHead
            title="People"
            count={
              people.data?.total === 1 ? "1 person" : `${people.data?.total ?? 0} people`
            }
          />
          {foundPeople.map((person) => (
            <UserRow
              key={person.id}
              person={person}
              note={person.bio ?? null}
              onPress={() => navigation.navigate("Profile", { handle: person.handle })}
              trailing={<FollowButton person={person} />}
            />
          ))}
        </>
      ) : null}
      {people.error ? <Notice tone="error">{people.error}</Notice> : null}
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
