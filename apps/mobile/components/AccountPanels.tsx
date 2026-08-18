/**
 * The social panels of the account screen: the public profile editor, the
 * navigation rows, and the reader's side of the classifieds board.
 */

import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useIsFocused, useNavigation } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import { ChevronRight, ImagePlus } from "lucide-react-native";
import {
  ACCEPTED_IMAGE_TYPES,
  inferContentType,
  uploadDirect,
  type Gig,
  type GigApplication,
  type User,
  type UserCard,
} from "@live-msc/shared";

import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, space, tabular } from "../lib/theme";
import { useResource } from "../lib/useResource";
import type { RootNavigation } from "../navigation/types";
import { UserRow } from "./UserRow";
import { Button, Empty, Field, Notice, Plate, SectionHead, Tag, inputStyle } from "./ui";

/** A plain navigation row: label, an optional note, a chevron. */
export function AccountRow({
  label,
  note,
  onPress,
}: {
  label: string;
  note?: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [styles.navRow, pressed && { backgroundColor: ink.wash }]}
    >
      <View style={{ flex: 1 }}>
        <Text style={styles.navLabel}>{label}</Text>
        {note ? <Text style={styles.navNote}>{note}</Text> : null}
      </View>
      <ChevronRight size={15} color={ink.faint} strokeWidth={1.5} />
    </Pressable>
  );
}

/** Portrait, @handle and bio — the parts of the account the public sees. */
export function PublicProfilePanel() {
  const navigation = useNavigation<RootNavigation>();
  const { user, refreshProfile } = useAuth();
  const [handle, setHandle] = useState(user?.handle ?? "");
  const [bio, setBio] = useState(user?.bio ?? "");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  if (!user) return null;

  const dirty =
    handle.trim().toLowerCase() !== user.handle || bio.trim() !== (user.bio ?? "");

  async function setAvatar() {
    if (!user) return;
    setError(null);
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError("Photo access is needed to set a portrait.");
      return;
    }
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (picked.canceled || !picked.assets[0]) return;

    const asset = picked.assets[0];
    const name = asset.fileName ?? "portrait.jpg";
    const contentType = inferContentType(name, asset.mimeType);
    if (!contentType || !ACCEPTED_IMAGE_TYPES.includes(contentType as never)) {
      setError("That is not an image format we accept.");
      return;
    }

    setUploading(true);
    try {
      await uploadDirect<{ user: User }>(
        api,
        {
          purpose: "user_avatar",
          targetId: user.id,
          contentType,
          sizeBytes: asset.fileSize,
        },
        { uri: asset.uri, name, type: contentType },
      );
      await refreshProfile();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "The upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function save() {
    if (!user) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    const patch: Record<string, string | null> = {};
    if (handle.trim().toLowerCase() !== user.handle) patch.handle = handle.trim();
    if (bio.trim() !== (user.bio ?? "")) patch.bio = bio.trim() || null;
    const result = await api.patch<{ user: User }>("/api/v1/me", patch);
    setBusy(false);
    if (!result.ok) {
      // HANDLE_TAKEN and validation refusals arrive with readable messages.
      setError(result.error);
      return;
    }
    setSaved(true);
    await refreshProfile();
  }

  return (
    <View>
      <SectionHead title="Public profile" />
      {error ? <Notice tone="error">{error}</Notice> : null}
      {saved && !dirty ? <Notice>Profile saved.</Notice> : null}

      <View style={{ marginTop: space.s3 }}>
        <View style={{ width: 148, alignSelf: "flex-start" }}>
          <Plate
            uri={user.avatar_url}
            height={132}
            placeholder="portrait"
            accessibilityLabel={`${user.display_name}'s portrait`}
          />
        </View>
        <Button
          label={
            uploading
              ? "Uploading…"
              : user.avatar_url
                ? "Replace the portrait"
                : "Add a portrait"
          }
          disabled={uploading}
          icon={<ImagePlus size={15} color={colors.text} />}
          style={{ marginTop: space.s2 }}
          onPress={() => void setAvatar()}
        />
      </View>

      <View style={{ marginTop: space.s4 }}>
        <Field
          label="Handle"
          note="3–30 characters of a–z, 0–9 and _. Your page lives at @handle."
        >
          <TextInput
            style={inputStyle}
            value={handle}
            onChangeText={setHandle}
            autoCapitalize="none"
            autoCorrect={false}
            maxLength={30}
            placeholder="your_handle"
            placeholderTextColor={ink.faint}
            accessibilityLabel="Handle"
          />
        </Field>
        <Field label="Bio">
          <TextInput
            style={[inputStyle, { minHeight: 64, textAlignVertical: "top" }]}
            value={bio}
            onChangeText={setBio}
            multiline
            maxLength={500}
            placeholder="A line or two about you"
            placeholderTextColor={ink.faint}
            accessibilityLabel="Bio"
          />
        </Field>
        {dirty ? (
          <Button
            label={busy ? "Saving…" : "Save profile"}
            variant="primary"
            disabled={busy}
            onPress={() => void save()}
          />
        ) : null}
        <Button
          label="View your public page →"
          variant="ghost"
          style={{ marginTop: space.s2 }}
          onPress={() => navigation.navigate("Profile", { handle: user.handle })}
        />
      </View>
    </View>
  );
}

/** Gigs the reader has posted to the board, with how many hands are up. */
export function MyGigsPanel() {
  const navigation = useNavigation<RootNavigation>();
  const focused = useIsFocused();
  const { data, error } = useResource<{ gigs: Gig[] }>(
    () => api.get<{ gigs: Gig[] }>("/api/v1/me/gigs"),
    [focused],
  );
  const gigs = data?.gigs ?? [];

  return (
    <View>
      <SectionHead
        title="Your gigs"
        count={gigs.length === 1 ? "1 posted" : `${gigs.length} posted`}
      />
      {error ? <Notice tone="error">{error}</Notice> : null}
      {data && gigs.length === 0 ? <Empty>Nothing on the board yet.</Empty> : null}
      {gigs.map((gig) => (
        <Pressable
          key={gig.id}
          onPress={() => navigation.navigate("Gig", { gigId: gig.id })}
          accessibilityRole="button"
          accessibilityLabel={gig.title}
          style={({ pressed }) => [styles.itemRow, pressed && { backgroundColor: ink.wash }]}
        >
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.itemTitle} numberOfLines={1}>
              {gig.title}
            </Text>
            <Text style={styles.itemMeta}>
              {gig.city}
              {gig.date_label ? `  ·  ${gig.date_label}` : ""}
            </Text>
          </View>
          <Text style={styles.itemCount}>
            {gig.application_count === 1 ? "1 applied" : `${gig.application_count ?? 0} applied`}
          </Text>
          {gig.status === "closed" ? <Tag label="Closed" /> : null}
        </Pressable>
      ))}
    </View>
  );
}

/** Where the reader's bands have raised a hand, and how it went. */
export function MyApplicationsPanel() {
  const navigation = useNavigation<RootNavigation>();
  const focused = useIsFocused();
  const { data, error } = useResource<{ applications: GigApplication[] }>(
    () => api.get<{ applications: GigApplication[] }>("/api/v1/me/applications"),
    [focused],
  );
  const applications = data?.applications ?? [];

  return (
    <View>
      <SectionHead
        title="Your applications"
        count={applications.length === 1 ? "1 open" : `${applications.length} sent`}
      />
      {error ? <Notice tone="error">{error}</Notice> : null}
      {data && applications.length === 0 ? (
        <Empty>No hands raised yet. The classifieds are waiting.</Empty>
      ) : null}
      {applications.map((application) => (
        <Pressable
          key={application.id}
          onPress={() => navigation.navigate("Gig", { gigId: application.gig_id })}
          accessibilityRole="button"
          accessibilityLabel={application.gig?.title ?? "A gig"}
          style={({ pressed }) => [styles.itemRow, pressed && { backgroundColor: ink.wash }]}
        >
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.itemTitle} numberOfLines={1}>
              {application.gig?.title ?? "A gig"}
            </Text>
            <Text style={styles.itemMeta}>
              as {application.artist?.name ?? "your band"}
            </Text>
          </View>
          <Tag
            label={
              application.status === "accepted"
                ? "Accepted"
                : application.status === "declined"
                  ? "Declined"
                  : "Pending"
            }
            accent={application.status === "accepted"}
          />
        </Pressable>
      ))}
    </View>
  );
}

/** People the reader has blocked, each with the way back. */
export function BlockedPeoplePanel() {
  const navigation = useNavigation<RootNavigation>();
  const focused = useIsFocused();
  const { data, error, reload } = useResource<{ people: UserCard[] }>(
    () => api.get<{ people: UserCard[] }>("/api/v1/me/blocks"),
    [focused],
  );
  const [rowError, setRowError] = useState<string | null>(null);
  const people = data?.people ?? [];

  async function unblock(person: UserCard) {
    setRowError(null);
    const result = await api.delete(
      `/api/v1/users/${encodeURIComponent(person.handle)}/block`,
    );
    if (!result.ok) {
      setRowError(result.error);
      return;
    }
    reload();
  }

  return (
    <View>
      <SectionHead
        title="Blocked people"
        count={people.length === 1 ? "1 person" : `${people.length} people`}
      />
      {error ? <Notice tone="error">{error}</Notice> : null}
      {rowError ? <Notice tone="error">{rowError}</Notice> : null}
      {data && people.length === 0 ? <Empty>No one blocked.</Empty> : null}
      {people.map((person) => (
        <UserRow
          key={person.id}
          person={person}
          onPress={() => navigation.navigate("Profile", { handle: person.handle })}
          trailing={
            <Button
              label="Unblock"
              variant="ghost"
              style={styles.unblockButton}
              onPress={() => void unblock(person)}
            />
          }
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  navRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s3,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  navLabel: { fontFamily: fonts.heading, fontSize: 15, color: colors.text },
  navNote: { fontFamily: fonts.bodyItalic, fontSize: 11, color: ink.faint, marginTop: 2 },
  itemRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  itemTitle: { fontFamily: fonts.heading, fontSize: 15, color: colors.text },
  itemMeta: { fontFamily: fonts.body, fontSize: 11, color: ink.soft, marginTop: 2 },
  itemCount: { fontFamily: fonts.body, fontSize: 11, color: ink.soft, ...tabular },
  unblockButton: { minHeight: 34, paddingVertical: space.s1 },
});
