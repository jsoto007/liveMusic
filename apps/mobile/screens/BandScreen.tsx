/**
 * 07 — A band. The public profile, with the sound samples playable inline.
 *
 * One `Audio.Sound` at a time: two would let samples play over each other, and
 * each would hold its own connection to a signed URL.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useRoute, type RouteProp } from "@react-navigation/native";
import { Audio } from "expo-av";
import { Pause, Play } from "lucide-react-native";
import type { Artist, EventListing } from "@live-msc/shared";

import {
  Body,
  Button,
  Empty,
  Heading,
  Kicker,
  Notice,
  Plate,
  Rule,
  SectionHead,
  Spinner,
  Tag,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootStackParamList } from "../navigation/types";

export function BandScreen() {
  const { params } = useRoute<RouteProp<RootStackParamList, "Band">>();
  const { user } = useAuth();
  const handle = encodeURIComponent(params.handle);

  const { data, error, loading, reload } = useResource<{ artist: Artist }>(
    () => api.get<{ artist: Artist }>(`/api/v1/artists/${handle}`),
    [handle],
  );
  const events = useResource<{ events: EventListing[] }>(
    () => api.get<{ events: EventListing[] }>(`/api/v1/artists/${handle}/events`),
    [handle],
  );

  const artist = data?.artist ?? null;
  const { playingId, toggle } = useSamplePlayer();

  const toggleFollow = useCallback(async () => {
    if (!artist || !user) return;
    if (artist.is_following) {
      await api.delete(`/api/v1/artists/${artist.id}/follow`);
    } else {
      await api.post(`/api/v1/artists/${artist.id}/follow`);
    }
    reload();
  }, [artist, user, reload]);

  if (loading && !artist) {
    return (
      <View style={styles.screen}>
        <Spinner />
      </View>
    );
  }

  if (error || !artist) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Notice tone="error">{error ?? "That band could not be found."}</Notice>
      </ScrollView>
    );
  }

  const samples = artist.samples ?? [];

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Plate
        uri={artist.photo_url}
        height={176}
        placeholder="band photo"
        accessibilityLabel={artist.name}
      />

      <View style={{ paddingTop: space.s4 }}>
        <Kicker accent>Band{artist.neighborhood ? `  ·  ${artist.neighborhood}` : ""}</Kicker>
        <Heading size="h1" display style={{ fontSize: 32, lineHeight: 34, marginTop: space.s2 }}>
          {artist.name}
        </Heading>
        {artist.one_liner ? <Text style={styles.oneLiner}>{artist.one_liner}</Text> : null}
        {artist.available_for_hire ? (
          <View style={{ flexDirection: "row", marginTop: space.s2 }}>
            <Tag label="Available for hire" accent />
          </View>
        ) : null}
      </View>

      <View style={styles.actions}>
        <Button
          label={artist.is_following ? "Following" : "Follow"}
          variant="toggle"
          on={artist.is_following ?? false}
          disabled={!user}
          style={{ flex: 1 }}
          onPress={() => void toggleFollow()}
        />
        {samples[0]?.stream_url ? (
          <Button
            label={playingId === samples[0].id ? "Pause" : "Listen"}
            style={{ flex: 1 }}
            onPress={() => void toggle(samples[0]!.id, samples[0]!.stream_url!)}
          />
        ) : null}
      </View>

      {artist.bio ? <Body style={{ marginTop: space.s4 }}>{artist.bio}</Body> : null}

      {events.data?.events && events.data.events.length > 0 ? (
        <>
          <SectionHead title="Upcoming" />
          {events.data.events.map((event) => (
            <View key={event.id} style={styles.upcomingRow}>
              <Text style={styles.upcomingDate}>{event.date_long}</Text>
              <View style={{ flex: 1 }}>
                <Text style={styles.upcomingVenue}>{event.venue?.name}</Text>
                {event.support_line ? (
                  <Text style={styles.upcomingNote}>{event.support_line}</Text>
                ) : null}
              </View>
              <Text style={styles.duration}>{event.price_label ?? "—"}</Text>
            </View>
          ))}
        </>
      ) : null}

      {artist.members && artist.members.length > 0 ? (
        <>
          <Rule style={{ marginVertical: space.s4 }} />
          <Kicker>Members</Kicker>
          {artist.members.map((member) => (
            <Text key={member.name} style={styles.member}>
              {member.name}
              {member.instrument ? ` — ${member.instrument}` : ""}
            </Text>
          ))}
        </>
      ) : null}

      {artist.sounds_like ? (
        <>
          <Kicker style={{ marginTop: space.s4 }}>Sounds like</Kicker>
          <Body italic muted style={{ marginTop: 4 }}>
            {artist.sounds_like}
          </Body>
        </>
      ) : null}

      {artist.style_tags.length > 0 ? (
        <>
          <SectionHead title="Style" />
          <View style={styles.tagRow}>
            {artist.style_tags.map((tag) => (
              <Tag key={tag} label={tag} />
            ))}
          </View>
        </>
      ) : null}

      <SectionHead
        title="Sound samples"
        count={samples.length === 1 ? "1 sample" : `${samples.length} samples`}
      />
      {samples.length === 0 ? <Empty>No samples yet.</Empty> : null}
      {samples.map((sample) => {
        const isPlaying = playingId === sample.id;
        return (
          <View key={sample.id} style={styles.sampleRow}>
            <Button
              label=""
              variant="ghost"
              style={styles.playButton}
              icon={
                isPlaying ? (
                  <Pause size={13} color={colors.accent} fill={colors.accent} />
                ) : (
                  <Play size={13} color={colors.accent} fill={colors.accent} />
                )
              }
              onPress={() => sample.stream_url && void toggle(sample.id, sample.stream_url)}
              disabled={!sample.stream_url}
            />
            <View style={{ flex: 1 }}>
              <Text style={styles.sampleTitle}>{sample.title}</Text>
              {isPlaying ? <Text style={styles.playing}>PLAYING</Text> : null}
            </View>
            <Text style={styles.duration}>{sample.duration_label ?? "—"}</Text>
          </View>
        );
      })}
    </ScrollView>
  );
}

/** One sound at a time, unloaded on unmount so nothing plays on after you leave. */
function useSamplePlayer() {
  const soundRef = useRef<Audio.Sound | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      void soundRef.current?.unloadAsync();
      soundRef.current = null;
    };
  }, []);

  const toggle = useCallback(
    async (id: string, url: string) => {
      if (playingId === id) {
        await soundRef.current?.pauseAsync();
        setPlayingId(null);
        return;
      }
      // Release the previous sample before loading the next; leaving it loaded
      // leaks an audio session per tap.
      await soundRef.current?.unloadAsync();
      soundRef.current = null;

      try {
        const { sound } = await Audio.Sound.createAsync(
          { uri: url },
          { shouldPlay: true },
          (status) => {
            if (status.isLoaded && status.didJustFinish) setPlayingId(null);
          },
        );
        soundRef.current = sound;
        setPlayingId(id);
      } catch {
        setPlayingId(null);
      }
    },
    [playingId],
  );

  return { playingId, toggle };
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s4, paddingBottom: space.s8 },
  oneLiner: { fontFamily: fonts.bodyItalic, fontSize: 15, color: ink.soft, marginTop: 7 },
  actions: { flexDirection: "row", gap: space.s2, marginTop: space.s4 },
  upcomingRow: {
    flexDirection: "row",
    gap: space.s3,
    alignItems: "flex-start",
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  upcomingDate: { width: 74, fontFamily: fonts.heading, fontSize: 13, color: ink.soft, ...tabular },
  upcomingVenue: { fontFamily: fonts.heading, fontSize: 15.5, color: colors.text },
  upcomingNote: { fontFamily: fonts.bodyItalic, fontSize: 11, color: ink.faint, marginTop: 2 },
  member: { fontFamily: fonts.body, fontSize: 12, lineHeight: 21, color: ink.muted },
  tagRow: { flexDirection: "row", flexWrap: "wrap", marginTop: space.s3 },
  sampleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    paddingVertical: space.s2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  playButton: { width: 34, minHeight: 34, paddingHorizontal: 0 },
  sampleTitle: { fontFamily: fonts.heading, fontSize: 15, color: colors.text },
  playing: { fontFamily: fonts.body, fontSize: 9.5, letterSpacing: 1, color: colors.accent, marginTop: 3 },
  duration: { fontFamily: fonts.body, fontSize: 11, color: ink.soft, ...tabular },
});
