/**
 * The Classical primitives for React Native.
 *
 * Same rules as the web: buttons are outlines, cards are bordered and
 * unfilled, hairlines carry the structure, figures set tabular.
 */

import { useState, type ReactNode } from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type ImageRequireSource,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  colors,
  fonts,
  ink,
  maxContentWidth,
  radius,
  space,
  tabular,
  type,
} from "../lib/theme";

/**
 * The page frame for a tab screen.
 *
 * The tab navigator's own header is hidden (see `navigation/index.tsx`) so
 * each screen can carry the editorial header the design calls for — a big
 * display title on the ground colour, not a chrome bar. This supplies the
 * safe-area inset that header would otherwise have provided.
 */
export function Screen({
  children,
  scroll = true,
  onRefresh,
  refreshing = false,
}: {
  children: ReactNode;
  scroll?: boolean;
  /** Pull down to fetch again. Pass this on any page whose content comes from
   * the network: without it, a page whose first load failed is a dead end —
   * the reader gets one error line and no way to try again short of killing
   * the app, which is exactly what a spotty connection produces. */
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  const insets = useSafeAreaInsets();
  const padding = { paddingTop: insets.top + space.s4 };

  if (!scroll) {
    return <View style={[screenStyles.root, padding]}>{children}</View>;
  }

  return (
    <ScrollView
      style={screenStyles.root}
      contentContainerStyle={[screenStyles.content, padding]}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.accent}
            colors={[colors.accent]}
          />
        ) : undefined
      }
    >
      {children}
    </ScrollView>
  );
}

const screenStyles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  content: {
    paddingHorizontal: 20,
    paddingBottom: space.s8,
    // The measure. On a phone `maxWidth` is never reached and this is inert;
    // on an iPad it stops body copy running the full width of the display.
    width: "100%",
    maxWidth: maxContentWidth,
    alignSelf: "center",
  },
});

export function Heading({
  children,
  size = "h3",
  display = false,
  style,
}: {
  children: ReactNode;
  size?: "h1" | "h2" | "h3" | "h4" | "h5";
  display?: boolean;
  style?: StyleProp<TextStyle>;
}) {
  return (
    <Text
      style={[
        {
          fontFamily: display ? fonts.headingDisplay : fonts.heading,
          fontSize: type[size],
          lineHeight: type[size] * 1.12,
          color: colors.text,
          letterSpacing: -0.15,
        },
        style,
      ]}
    >
      {children}
    </Text>
  );
}

export function Kicker({
  children,
  accent = false,
  style,
}: {
  children: ReactNode;
  accent?: boolean;
  style?: StyleProp<TextStyle>;
}) {
  return (
    <Text
      style={[
        {
          fontFamily: fonts.body,
          fontSize: type.kicker,
          letterSpacing: 1.3,
          textTransform: "uppercase",
          color: accent ? colors.accent : ink.faint,
        },
        style,
      ]}
    >
      {children}
    </Text>
  );
}

export function Body({
  children,
  muted = false,
  italic = false,
  style,
}: {
  children: ReactNode;
  muted?: boolean;
  italic?: boolean;
  style?: StyleProp<TextStyle>;
}) {
  return (
    <Text
      style={[
        {
          fontFamily: italic ? fonts.bodyItalic : fonts.body,
          fontSize: type.small,
          lineHeight: type.small * 1.7,
          color: muted ? ink.soft : ink.muted,
        },
        style,
      ]}
    >
      {children}
    </Text>
  );
}

export function Rule({ strong = false, style }: { strong?: boolean; style?: StyleProp<ViewStyle> }) {
  return (
    <View
      style={[
        { height: StyleSheet.hairlineWidth * (strong ? 2 : 1) },
        { backgroundColor: strong ? "rgba(32,31,29,0.40)" : ink.divider },
        style,
      ]}
    />
  );
}

export function SectionHead({ title, count }: { title: string; count?: string }) {
  return (
    <View style={{ marginTop: space.s6 }}>
      <View style={styles.sectionHeadRow}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {count ? <Text style={styles.sectionCount}>{count}</Text> : null}
      </View>
      <Rule strong />
    </View>
  );
}

/**
 * The image wrapper. Every photograph goes through it — a thin
 * surface-coloured mat with a hairline outline, so pictures read as plates
 * tipped into the page rather than banners across it.
 */
export function Plate({
  uri,
  placeholder = "No image",
  height = 190,
  accessibilityLabel,
  fallbackSource,
}: {
  uri?: string | null;
  placeholder?: string;
  height?: number;
  accessibilityLabel: string;
  /** Shown when `uri` is absent or fails to load. Posters are short-lived
      presigned URLs, so a plate left on screen past the TTL must fall back
      to something rather than go blank. */
  fallbackSource?: ImageRequireSource;
}) {
  // Tracked per URI rather than as a boolean so a plate reused for a new
  // event (a re-fetched detail, a new featured pick) retries its real poster.
  const [failedUri, setFailedUri] = useState<string | null>(null);
  const posterUri = uri && uri !== failedUri ? uri : null;
  const source = posterUri ? { uri: posterUri } : fallbackSource;
  return (
    <View style={[styles.plate, { height }]}>
      {source ? (
        <Image
          source={source}
          style={styles.plateImage}
          resizeMode="cover"
          onError={posterUri ? () => setFailedUri(posterUri) : undefined}
          accessibilityLabel={accessibilityLabel}
          accessible
        />
      ) : (
        <Text style={styles.plateEmpty}>{placeholder}</Text>
      )}
    </View>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "toggle";

export function Button({
  label,
  onPress,
  variant = "secondary",
  on = false,
  disabled = false,
  icon,
  style,
  accessibilityLabel,
}: {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  /** For toggles: engaged moves the stroke to the accent, never to a fill. */
  on?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  style?: StyleProp<ViewStyle>;
  /** For icon-only buttons, whose empty label reads as nothing. */
  accessibilityLabel?: string;
}) {
  const strokeColor =
    variant === "primary" || (variant === "toggle" && on)
      ? colors.accent
      : variant === "toggle"
        ? "rgba(32,31,29,0.55)"
        : ink.divider;
  const textColor =
    variant === "primary" || (variant === "toggle" && on) || variant === "ghost"
      ? colors.accent
      : colors.text;

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled, selected: on }}
      style={({ pressed }) => [
        styles.button,
        {
          borderColor: variant === "ghost" ? "transparent" : strokeColor,
          opacity: disabled ? 0.45 : 1,
          backgroundColor: pressed ? ink.accentWash : "transparent",
        },
        style,
      ]}
    >
      {icon}
      <Text style={[styles.buttonLabel, { color: textColor }]}>{label}</Text>
    </Pressable>
  );
}

export function Chip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      style={({ pressed }) => [
        styles.chip,
        {
          borderColor: selected ? colors.accent : ink.divider,
          backgroundColor: pressed ? ink.wash : "transparent",
        },
      ]}
    >
      <Text style={[styles.chipLabel, { color: selected ? colors.accent700 : colors.text }]}>
        {label}
      </Text>
    </Pressable>
  );
}

export function Tag({ label, accent = false }: { label: string; accent?: boolean }) {
  return (
    <View style={[styles.tag, accent ? styles.tagAccent : styles.tagOutline]}>
      <Text style={[styles.tagLabel, { color: accent ? colors.accent800 : colors.accent }]}>
        {label}
      </Text>
    </View>
  );
}

export function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return (
    <View
      style={[
        styles.notice,
        tone === "error" && {
          borderLeftColor: colors.accent700,
          backgroundColor: "rgba(182,130,53,0.06)",
        },
      ]}
      accessibilityLiveRegion={tone === "error" ? "assertive" : "none"}
    >
      <Text style={styles.noticeText}>{children}</Text>
    </View>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <Text style={styles.empty}>{children}</Text>;
}

export function Spinner({ label = "Setting the page" }: { label?: string }) {
  return (
    <View style={styles.spinner}>
      <ActivityIndicator color={colors.accent} />
      <Kicker style={{ marginTop: space.s2 }}>{label}</Kicker>
    </View>
  );
}

export function Field({
  label,
  children,
  note,
}: {
  label: string;
  children: ReactNode;
  note?: string;
}) {
  return (
    <View style={{ marginBottom: space.s4 }}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {children}
      {note ? <Text style={styles.fieldNote}>{note}</Text> : null}
    </View>
  );
}

export const inputStyle: TextStyle = {
  minHeight: 40,
  paddingHorizontal: space.s2,
  paddingVertical: space.s2,
  fontFamily: fonts.body,
  fontSize: 14,
  color: colors.text,
  borderWidth: StyleSheet.hairlineWidth,
  borderColor: ink.divider,
  borderRadius: radius.md,
};

const styles = StyleSheet.create({
  sectionHeadRow: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  sectionTitle: {
    fontFamily: fonts.heading,
    fontSize: 12,
    letterSpacing: 1.9,
    textTransform: "uppercase",
    color: colors.text,
  },
  sectionCount: {
    fontFamily: fonts.body,
    fontSize: 10,
    letterSpacing: 0.8,
    textTransform: "uppercase",
    color: ink.ghost,
    ...tabular,
  },
  plate: {
    borderWidth: 6,
    borderColor: colors.surface,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  plateImage: { width: "100%", height: "100%" },
  plateEmpty: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    color: ink.faint,
    textAlign: "center",
    paddingHorizontal: space.s4,
  },
  button: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.md,
    paddingVertical: space.s2,
    paddingHorizontal: space.s3 * 1.2,
    minHeight: 44,
  },
  buttonLabel: { fontFamily: fonts.heading, fontSize: 14 },
  chip: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.md,
    paddingVertical: 6,
    paddingHorizontal: 13,
    marginRight: 6,
    marginBottom: 6,
  },
  chipLabel: { fontFamily: fonts.body, fontSize: 12, letterSpacing: 0.5 },
  tag: {
    paddingVertical: 3,
    paddingHorizontal: 10,
    borderRadius: radius.md * 0.75,
    marginRight: 6,
    marginBottom: 6,
  },
  tagOutline: { borderWidth: StyleSheet.hairlineWidth, borderColor: colors.accent },
  tagAccent: { backgroundColor: colors.accent100 },
  tagLabel: { fontFamily: fonts.body, fontSize: 11 },
  notice: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.divider,
    borderLeftWidth: 2,
    borderLeftColor: colors.accent,
    borderRadius: radius.sm,
    padding: space.s3,
    marginVertical: space.s3,
  },
  noticeText: { fontFamily: fonts.body, fontSize: 13, color: colors.text, lineHeight: 20 },
  empty: {
    fontFamily: fonts.bodyItalic,
    fontSize: 13,
    color: ink.faint,
    textAlign: "center",
    marginVertical: space.s8,
  },
  spinner: { alignItems: "center", marginVertical: space.s8 },
  fieldLabel: {
    fontFamily: fonts.body,
    fontSize: 12,
    color: ink.soft,
    marginBottom: 5,
  },
  fieldNote: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    color: ink.faint,
    marginTop: 4,
  },
});
