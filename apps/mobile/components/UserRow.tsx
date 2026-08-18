/** A person as a byline row: the small portrait, the name, the @handle. */

import { useEffect, useState, type ReactNode } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import type { UserCard } from "@live-msc/shared";

import { api, useAuth } from "../lib/auth";
import { colors, fonts, ink, radius, space } from "../lib/theme";
import type { RootNavigation } from "../navigation/types";
import { Button } from "./ui";

/** The small portrait plate. A person without one prints their initial. */
export function Avatar({
  person,
  size = 40,
}: {
  person: Pick<UserCard, "display_name" | "avatar_url">;
  size?: number;
}) {
  const [failed, setFailed] = useState(false);
  const uri = !failed && person.avatar_url ? person.avatar_url : null;
  return (
    <View style={[styles.avatar, { width: size, height: size }]}>
      {uri ? (
        <Image
          source={{ uri }}
          style={styles.avatarImage}
          resizeMode="cover"
          onError={() => setFailed(true)}
          accessibilityLabel={person.display_name}
        />
      ) : (
        <Text style={[styles.avatarInitial, { fontSize: size * 0.44 }]}>
          {(person.display_name.trim()[0] ?? "?").toUpperCase()}
        </Text>
      )}
    </View>
  );
}

export function UserRow({
  person,
  onPress,
  trailing,
  note,
}: {
  person: UserCard;
  onPress: () => void;
  /** A control on the right — a follow button, an unblock button. */
  trailing?: ReactNode;
  /** One line under the name — a bio, a status. */
  note?: string | null;
}) {
  return (
    <View style={styles.row}>
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={`${person.display_name}, @${person.handle}`}
        style={({ pressed }) => [styles.main, pressed && { backgroundColor: ink.wash }]}
      >
        <Avatar person={person} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.name} numberOfLines={1}>
            {person.display_name}
          </Text>
          <Text style={styles.handle} numberOfLines={1}>
            @{person.handle}
          </Text>
          {note ? (
            <Text style={styles.note} numberOfLines={1}>
              {note}
            </Text>
          ) : null}
        </View>
      </Pressable>
      {trailing}
    </View>
  );
}

/**
 * The follow toggle for a person. Signed-out taps go to the sign-in sheet,
 * matching how the rest of the app gates its writes.
 */
export function FollowButton({
  person,
  onChanged,
}: {
  person: UserCard;
  onChanged?: (following: boolean) => void;
}) {
  const navigation = useNavigation<RootNavigation>();
  const { user } = useAuth();
  const [following, setFollowing] = useState(person.is_following ?? false);
  const [busy, setBusy] = useState(false);

  // A reload can change the flag under us (another screen followed them).
  useEffect(() => {
    setFollowing(person.is_following ?? false);
  }, [person.is_following]);

  if (person.is_self || (user !== null && person.id === user.id)) return null;

  async function toggle() {
    if (!user) {
      navigation.navigate("SignIn");
      return;
    }
    setBusy(true);
    const path = `/api/v1/users/${encodeURIComponent(person.handle)}/follow`;
    const result = following
      ? await api.delete<{ is_following: boolean }>(path)
      : await api.post<{ is_following: boolean }>(path);
    setBusy(false);
    if (result.ok && result.data) {
      setFollowing(result.data.is_following);
      onChanged?.(result.data.is_following);
    }
  }

  return (
    <Button
      label={following ? "Following" : "Follow"}
      variant="toggle"
      on={following}
      disabled={busy}
      style={styles.followButton}
      onPress={() => void toggle()}
    />
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.s2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.divider,
  },
  main: {
    flex: 1,
    minWidth: 0,
    flexDirection: "row",
    alignItems: "center",
    gap: space.s3,
    paddingVertical: space.s3,
  },
  avatar: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  avatarImage: { width: "100%", height: "100%" },
  avatarInitial: { fontFamily: fonts.heading, color: ink.soft },
  name: { fontFamily: fonts.heading, fontSize: 16, color: colors.text },
  handle: { fontFamily: fonts.body, fontSize: 11, color: ink.soft, marginTop: 2 },
  note: { fontFamily: fonts.bodyItalic, fontSize: 11, color: ink.faint, marginTop: 3 },
  followButton: { minHeight: 34, paddingVertical: space.s1 },
});
