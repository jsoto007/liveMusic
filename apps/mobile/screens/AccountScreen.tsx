/**
 * 08 — Your account, and your band's page.
 *
 * The sample uploader is where the direct-to-R2 flow surfaces: pick a file, it
 * goes straight to storage, and only then does the row appear.
 */

import { useCallback, useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import { ImagePlus, Plus, X } from "lucide-react-native";
import {
  ACCEPTED_AUDIO_TYPES,
  ACCEPTED_IMAGE_TYPES,
  inferContentType,
  uploadDirect,
  type Artist,
  type AudioSample,
  type EmailPreferences,
  type EventListing,
  type Place,
} from "@live-msc/shared";

import {
  AccountRow,
  BlockedPeoplePanel,
  MyApplicationsPanel,
  MyGigsPanel,
  PublicProfilePanel,
} from "../components/AccountPanels";
import { AddressField } from "../components/AddressField";
import {
  Body,
  Button,
  Chip,
  Empty,
  Heading,
  Kicker,
  Notice,
  Plate,
  Rule,
  Screen,
  SectionHead,
  Spinner,
  Tag,
  inputStyle,
} from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, radius, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";

export function AccountScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { user, artists, initializing, signOut, refreshProfile } = useAuth();
  const [newBandName, setNewBandName] = useState("");
  const [error, setError] = useState<string | null>(null);

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
          Your account
        </Heading>
        <Notice>Sign in to see your account.</Notice>
        <Button label="Sign in" variant="primary" onPress={() => navigation.navigate("SignIn")} />
        <Button
          label="Create an account"
          variant="ghost"
          style={{ marginTop: space.s2 }}
          onPress={() => navigation.navigate("Join")}
        />
      </Screen>
    );
  }

  async function createBand() {
    setError(null);
    const result = await api.post<{ artist: Artist }>("/api/v1/me/artists", {
      name: newBandName.trim(),
      city: user?.home_city ?? undefined,
    });
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setNewBandName("");
    await refreshProfile();
  }

  return (
    <Screen>
      <Kicker accent>Account</Kicker>
      <Heading size="h1" display style={{ fontSize: 30, lineHeight: 32, marginTop: 7 }}>
        {user.display_name}
      </Heading>
      <Text style={styles.subtitle}>
        {user.home_city ?? "No home city set"}  ·  {user.email}
      </Text>

      {error ? <Notice tone="error">{error}</Notice> : null}

      {!user.email_verified ? <VerifyBanner email={user.email ?? ""} /> : null}

      <PublicProfilePanel />

      <SectionHead title="Your pages" />
      <AccountRow
        label="Notifications"
        note="Follows, comments and gig news"
        onPress={() => navigation.navigate("Notifications")}
      />
      <AccountRow
        label="Messages"
        note="Hire enquiries and correspondence"
        onPress={() => navigation.navigate("Messages")}
      />
      <AccountRow
        label="The classifieds"
        note="Gigs wanted, and the bands for hire"
        onPress={() => navigation.navigate("Classifieds")}
      />

      <HomeCityField currentCity={user.home_city} onSaved={refreshProfile} />
      <EmailPreferencesPanel />

      {artists.map((artist) => (
        <BandPanel key={artist.id} artist={artist} />
      ))}

      <MyGigsPanel />
      <MyApplicationsPanel />
      <BlockedPeoplePanel />

      <SectionHead title="Start a band account" />
      <View style={{ flexDirection: "row", gap: space.s2, marginTop: space.s3 }}>
        <TextInput
          style={[inputStyle, { flex: 1 }]}
          value={newBandName}
          onChangeText={setNewBandName}
          placeholder="Band name"
          placeholderTextColor={ink.faint}
          maxLength={120}
          accessibilityLabel="Band name"
        />
        <Button
          label="Create"
          variant="primary"
          disabled={!newBandName.trim()}
          onPress={() => void createBand()}
        />
      </View>

      <Rule style={{ marginVertical: space.s6 }} />
      <Button label="Sign out" onPress={() => void signOut()} />
    </Screen>
  );
}

function BandPanel({ artist }: { artist: Artist }) {
  const navigation = useNavigation<RootNavigation>();
  const [hireOn, setHireOn] = useState(artist.available_for_hire);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [photoUploading, setPhotoUploading] = useState(false);

  const detail = useResource<{ artist: Artist }>(
    () => api.get<{ artist: Artist }>(`/api/v1/artists/${artist.id}`),
    [artist.id],
  );
  const listings = useResource<{ events: EventListing[] }>(
    () => api.get<{ events: EventListing[] }>(`/api/v1/me/artists/${artist.id}/events`),
    [artist.id],
  );

  const samples = detail.data?.artist.samples ?? [];

  const setHire = useCallback(
    async (next: boolean) => {
      setHireOn(next);
      const result = await api.patch(`/api/v1/artists/${artist.id}`, {
        available_for_hire: next,
      });
      if (!result.ok) {
        // Put the switch back rather than showing a state the server refused.
        setHireOn(!next);
        setError(result.error);
      }
    },
    [artist.id],
  );

  const addSample = useCallback(async () => {
    setError(null);
    const picked = await DocumentPicker.getDocumentAsync({
      type: [...ACCEPTED_AUDIO_TYPES],
      copyToCacheDirectory: true,
    });
    if (picked.canceled || !picked.assets[0]) return;

    const asset = picked.assets[0];
    const contentType = inferContentType(asset.name, asset.mimeType);
    if (!contentType || !ACCEPTED_AUDIO_TYPES.includes(contentType as never)) {
      setError("That is not an audio format we accept.");
      return;
    }

    setUploading(true);
    try {
      await uploadDirect<{ sample: AudioSample }>(
        api,
        {
          purpose: "artist_audio",
          targetId: artist.id,
          contentType,
          sizeBytes: asset.size,
        },
        { uri: asset.uri, name: asset.name, type: contentType },
        { completion: { title: asset.name.replace(/\.[^.]+$/, "").slice(0, 140) } },
      );
      detail.reload();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "The upload failed.");
    } finally {
      setUploading(false);
    }
  }, [artist.id, detail]);

  const setPhoto = useCallback(async () => {
    setError(null);
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError("Photo access is needed to set a band photo.");
      return;
    }
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (picked.canceled || !picked.assets[0]) return;

    const asset = picked.assets[0];
    const name = asset.fileName ?? "photo.jpg";
    const contentType = inferContentType(name, asset.mimeType);
    if (!contentType || !ACCEPTED_IMAGE_TYPES.includes(contentType as never)) {
      setError("That is not an image format we accept.");
      return;
    }

    setPhotoUploading(true);
    try {
      await uploadDirect<{ artist: Artist }>(
        api,
        {
          purpose: "artist_photo",
          targetId: artist.id,
          contentType,
          sizeBytes: asset.fileSize,
        },
        { uri: asset.uri, name, type: contentType },
      );
      detail.reload();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "The upload failed.");
    } finally {
      setPhotoUploading(false);
    }
  }, [artist.id, detail]);

  const removeSample = useCallback(
    async (sampleId: string) => {
      const result = await api.delete(`/api/v1/artists/${artist.id}/samples/${sampleId}`);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      detail.reload();
    },
    [artist.id, detail],
  );

  return (
    <View style={{ marginTop: space.s6 }}>
      <Rule />
      <View style={styles.bandHead}>
        <View style={{ flex: 1 }}>
          <Heading size="h4" display>
            {artist.name}
          </Heading>
          <Kicker style={{ marginTop: 4 }}>Band account</Kicker>
        </View>
        <Button
          label="View page →"
          variant="ghost"
          onPress={() => navigation.navigate("Band", { handle: artist.slug })}
        />
      </View>

      {error ? <Notice tone="error">{error}</Notice> : null}

      <View style={{ marginTop: space.s3 }}>
        <Plate
          uri={detail.data?.artist.photo_url}
          height={150}
          placeholder="band photo"
          accessibilityLabel={`${artist.name}`}
        />
        <Button
          label={
            photoUploading
              ? "Uploading…"
              : detail.data?.artist.photo_url
                ? "Replace the photo"
                : "Add a band photo"
          }
          disabled={photoUploading}
          icon={<ImagePlus size={15} color={colors.text} />}
          style={{ marginTop: space.s2 }}
          onPress={() => void setPhoto()}
        />
      </View>

      <View style={styles.statGrid}>
        <Stat n={detail.data?.artist.follower_count ?? 0} label="Following" />
        <Stat n={listings.data?.events.length ?? 0} label="Listings" />
        <Stat n={samples.length} label="Samples" last />
      </View>

      <View style={styles.hireRow}>
        <View style={{ flex: 1 }}>
          <Kicker>Hire profile</Kicker>
          <Text style={styles.hireNote}>Shown on your public page</Text>
        </View>
        <View style={{ flexDirection: "row" }}>
          <Chip label="Available" selected={hireOn} onPress={() => void setHire(true)} />
          <Chip label="Hidden" selected={!hireOn} onPress={() => void setHire(false)} />
        </View>
      </View>

      <SectionHead
        title="Sound samples"
        count={samples.length === 1 ? "1 sample" : `${samples.length} samples`}
      />
      <Button
        label={uploading ? "Uploading…" : "Add sample"}
        variant="ghost"
        disabled={uploading}
        icon={<Plus size={14} color={colors.accent} />}
        onPress={() => void addSample()}
      />

      {samples.length === 0 ? <Empty>No samples yet.</Empty> : null}
      {samples.map((sample) => (
        <View key={sample.id} style={styles.sampleRow}>
          <Text style={styles.sampleTitle}>{sample.title}</Text>
          <Text style={styles.duration}>{sample.duration_label ?? "—"}</Text>
          <Button
            label=""
            variant="ghost"
            style={styles.removeButton}
            icon={<X size={13} color={ink.soft} />}
            onPress={() => void removeSample(sample.id)}
          />
        </View>
      ))}

      <SectionHead title="Your listings" />
      {listings.data?.events.length === 0 ? <Empty>Nothing posted yet.</Empty> : null}
      {listings.data?.events.map((event) => (
        <View key={event.id} style={styles.listingRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.listingVenue}>{event.venue?.name}</Text>
            <Text style={styles.listingWhen}>
              {event.date_long}  ·  {event.time_label}
            </Text>
          </View>
          <Tag
            label={
              event.status === "published"
                ? "On the bill"
                : event.status === "cancelled"
                  ? "Cancelled"
                  : "Draft"
            }
            accent={event.status === "published"}
          />
        </View>
      ))}
    </View>
  );
}

function Stat({ n, label, last = false }: { n: number; label: string; last?: boolean }) {
  return (
    <View style={[styles.stat, last && { borderRightWidth: 0 }]}>
      <Text style={styles.statN}>{n}</Text>
      <Text style={styles.statLabel}>{label.toUpperCase()}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  subtitle: { fontFamily: fonts.bodyItalic, fontSize: 11.5, color: ink.soft, marginTop: 6 },
  bandHead: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    marginTop: space.s4,
  },
  statGrid: {
    flexDirection: "row",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    borderRadius: radius.md,
    marginTop: space.s3,
  },
  stat: {
    flex: 1,
    alignItems: "center",
    paddingVertical: space.s3,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: ink.divider,
  },
  statN: { fontFamily: fonts.heading, fontSize: 24, color: colors.text, ...tabular },
  statLabel: { fontFamily: fonts.body, fontSize: 9, letterSpacing: 1.1, color: ink.faint, marginTop: 6 },
  hireRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s3,
    marginTop: space.s4,
  },
  hireNote: { fontFamily: fonts.bodyItalic, fontSize: 11, color: ink.faint, marginTop: 4 },
  sampleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    paddingVertical: space.s2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  sampleTitle: { flex: 1, fontFamily: fonts.heading, fontSize: 15, color: colors.text },
  duration: { fontFamily: fonts.body, fontSize: 11, color: ink.soft, ...tabular },
  removeButton: { width: 34, minHeight: 34, paddingHorizontal: 0 },
  listingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  listingVenue: { fontFamily: fonts.heading, fontSize: 16, color: colors.text },
  listingWhen: { fontFamily: fonts.body, fontSize: 11, color: ink.soft, marginTop: 3, ...tabular },
  preferenceRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  preferenceLabel: { fontFamily: fonts.body, fontSize: 14, color: colors.text },
});

/** Shown until the address is confirmed — a prompt, not a blocker. */
function VerifyBanner({ email }: { email: string }) {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function resend() {
    setBusy(true);
    await api.post("/api/v1/auth/verify-email/resend", { email });
    setBusy(false);
    setSent(true);
  }

  if (sent) {
    return <Notice>A new confirmation link is on its way to {email}.</Notice>;
  }

  return (
    <View style={{ marginTop: space.s4 }}>
      <Notice>Your email isn&rsquo;t confirmed yet, so notices won&rsquo;t reach you.</Notice>
      <Button
        label={busy ? "Sending…" : "Send another link"}
        variant="ghost"
        disabled={busy}
        onPress={() => void resend()}
      />
    </View>
  );
}

/** Home city, with address suggestions — it centres the map. */
function HomeCityField({
  currentCity,
  onSaved,
}: {
  currentCity: string | null;
  onSaved: () => Promise<void>;
}) {
  const [city, setCity] = useState(currentCity ?? "");
  const [busy, setBusy] = useState(false);
  const dirty = city.trim() !== (currentCity ?? "").trim();

  async function save(next?: string) {
    const value = (next ?? city).trim();
    setBusy(true);
    const result = await api.patch("/api/v1/me", { home_city: value || null });
    setBusy(false);
    if (result.ok) await onSaved();
  }

  return (
    <>
      <SectionHead title="Home city" />
      <View style={{ marginTop: space.s3 }}>
        <AddressField
          label="Where you are"
          value={city}
          onChangeText={setCity}
          onSelect={(place: Place) => {
            const resolved = place.city ?? place.name;
            setCity(resolved);
            void save(resolved);
          }}
          placeholder="Providence"
          note="Used to centre the map and pick your default listings."
          maxLength={120}
        />
        {dirty ? (
          <Button
            label={busy ? "Saving…" : "Save"}
            disabled={busy}
            onPress={() => void save()}
          />
        ) : null}
      </View>
    </>
  );
}

/** What we're allowed to email about. */
function EmailPreferencesPanel() {
  const { data, error, reload } = useResource<{ preferences: EmailPreferences }>(
    () => api.get<{ preferences: EmailPreferences }>("/api/v1/me/email-preferences"),
    [],
  );
  const [saving, setSaving] = useState(false);
  const preferences = data?.preferences;

  async function update(patch: Partial<EmailPreferences>) {
    setSaving(true);
    await api.patch("/api/v1/me/email-preferences", patch);
    setSaving(false);
    reload();
  }

  return (
    <>
      <SectionHead title="Notices" count={saving ? "saving" : undefined} />
      {error ? <Notice tone="error">{error}</Notice> : null}

      <PreferenceRow
        label="New shows from bands you follow"
        note="One email when a band you follow posts a listing."
        value={preferences?.notify_new_shows ?? false}
        onChange={(value) => void update({ notify_new_shows: value })}
      />
      <PreferenceRow
        label="Reminders for shows you're going to"
        note="The day before, for anything you've marked."
        value={preferences?.notify_show_reminders ?? false}
        onChange={(value) => void update({ notify_show_reminders: value })}
      />

      {preferences?.unsubscribed_all ? (
        <Body muted italic style={{ marginTop: space.s2 }}>
          You&rsquo;re unsubscribed from everything. Turning either notice back on
          starts them again — account mail reaches you regardless.
        </Body>
      ) : null}
    </>
  );
}

function PreferenceRow({
  label,
  note,
  value,
  onChange,
}: {
  label: string;
  note: string;
  value: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <View style={styles.preferenceRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.preferenceLabel}>{label}</Text>
        <Text style={styles.hireNote}>{note}</Text>
      </View>
      <View style={{ flexDirection: "row" }}>
        <Chip label="On" selected={value} onPress={() => onChange(true)} />
        <Chip label="Off" selected={!value} onPress={() => onChange(false)} />
      </View>
    </View>
  );
}
