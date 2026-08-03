/** 06 — Your list. Going, and kept for later. */

import { StyleSheet, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import type { EventListing } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import { Button, Empty, Heading, Kicker, Notice, Screen, SectionHead, Spinner } from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";

interface ListResponse {
  going: EventListing[];
  saved: EventListing[];
  summary: string;
}

export function ListScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user, initializing } = useAuth();

  const { data, error, loading } = useResource<ListResponse>(
    () => api.get<ListResponse>("/api/v1/me/list"),
    [user?.id ?? ""],
  );

  if (initializing) {
    return (
      <View style={styles.screen}>
        <Spinner />
      </View>
    );
  }

  if (!user) {
    return (
      <Screen>
        <Heading size="h2" display>
          Your list
        </Heading>
        <Notice>Sign in to keep shows and mark what you&rsquo;re going to.</Notice>
        <Button label="Sign in" variant="primary" onPress={() => navigation.navigate("SignIn")} />
      </Screen>
    );
  }

  return (
    <Screen>
      <Heading size="h2" display>
        Your list
      </Heading>
      <Kicker style={{ marginTop: 6 }}>{data?.summary ?? "—"}</Kicker>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}

      <SectionHead title="Going" />
      {data?.going.length === 0 ? (
        <Empty>Nothing marked yet.</Empty>
      ) : (
        data?.going.map((event) => (
          <ListingRow
            key={event.id}
            event={event}
            showNote={false}
            onPress={() => navigation.navigate("Show", { eventId: event.id })}
          />
        ))
      )}

      <SectionHead title="Kept for later" />
      {data?.saved.length === 0 ? (
        <Empty>Nothing kept yet.</Empty>
      ) : (
        data?.saved.map((event) => (
          <ListingRow
            key={event.id}
            event={event}
            showNote={false}
            onPress={() => navigation.navigate("Show", { eventId: event.id })}
          />
        ))
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
});
