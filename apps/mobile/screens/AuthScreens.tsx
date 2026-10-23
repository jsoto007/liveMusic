/** Sign in and join. */

import { useState } from "react";
import { Linking, ScrollView, StyleSheet, Text, TextInput } from "react-native";
import { useNavigation } from "@react-navigation/native";

import { Body, Button, Field, Heading, Notice, inputStyle } from "../components/ui";
import { api, useAuth } from "../lib/auth";
import { PRIVACY_URL, TERMS_URL } from "../lib/legal";
import { colors, fonts, ink, space } from "../lib/theme";
import type { RootNavigation } from "../navigation/types";

const MIN_PASSWORD_LENGTH = 12;

export function SignInScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resetSent, setResetSent] = useState(false);

  /** Ask for a reset link.
   *
   * The link itself lands in the reader's mail and opens the web app, which
   * is where the reset form lives — but without this the only way back into a
   * forgotten account from a phone was to find the website unaided. The
   * server answers identically whether or not the address is registered, so
   * the message here does the same and never confirms an account exists. */
  async function sendResetLink() {
    setError(null);
    if (!email.trim()) {
      setError("Enter your email address first, and we will send a reset link.");
      return;
    }
    setBusy(true);
    await api.post("/api/v1/auth/forgot-password", { email: email.trim() });
    setBusy(false);
    setResetSent(true);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    const message = await signIn(email, password);
    setBusy(false);
    if (message) {
      setError(message);
      return;
    }
    navigation.goBack();
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Heading size="h2" display>
        Sign in
      </Heading>
      {error ? <Notice tone="error">{error}</Notice> : null}

      <Field label="Email">
        <TextInput
          style={inputStyle}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          placeholderTextColor={ink.faint}
        />
      </Field>
      <Field label="Password">
        <TextInput
          style={inputStyle}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="current-password"
          placeholderTextColor={ink.faint}
        />
      </Field>

      <Button
        label={busy ? "Signing in…" : "Sign in"}
        variant="primary"
        disabled={busy}
        onPress={() => void submit()}
      />
      {resetSent ? (
        <Notice>
          If that address has an account, a reset link is on its way. Open it on
          this phone and you will come back here signed in.
        </Notice>
      ) : (
        <Button
          label="Forgotten your password?"
          variant="ghost"
          style={{ marginTop: space.s2 }}
          disabled={busy}
          onPress={() => void sendResetLink()}
        />
      )}
      <Button
        label="No account yet? Join"
        variant="ghost"
        style={{ marginTop: space.s2 }}
        onPress={() => navigation.navigate("Join")}
      />
    </ScrollView>
  );
}

export function JoinScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { register } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [homeCity, setHomeCity] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    // Checked here for a fast message; the server enforces the real policy.
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    setBusy(true);
    setError(null);
    const message = await register({ email, password, displayName, homeCity });
    setBusy(false);
    if (message) {
      setError(message);
      return;
    }
    navigation.navigate("Tabs");
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Heading size="h2" display>
        Join
      </Heading>
      <Body muted style={{ marginTop: 6 }}>
        Read the bill, keep shows, and post your own.
      </Body>
      {error ? <Notice tone="error">{error}</Notice> : null}

      <Field label="Your name">
        <TextInput
          style={inputStyle}
          value={displayName}
          onChangeText={setDisplayName}
          maxLength={80}
          placeholderTextColor={ink.faint}
        />
      </Field>
      <Field label="Email">
        <TextInput
          style={inputStyle}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          placeholderTextColor={ink.faint}
        />
      </Field>
      <Field label="Home city">
        <TextInput
          style={inputStyle}
          value={homeCity}
          onChangeText={setHomeCity}
          placeholder="Providence"
          maxLength={120}
          placeholderTextColor={ink.faint}
        />
      </Field>
      <Field label="Password" note={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
        <TextInput
          style={inputStyle}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="new-password"
          placeholderTextColor={ink.faint}
        />
      </Field>

      {/* Guideline 1.2: a reader who can post, comment and review has to be
          shown the terms — including the line about what gets you removed —
          before the account exists, not buried in a settings screen after. */}
      <Text style={styles.agreement}>
        By creating an account you agree to the{" "}
        <Text style={styles.link} onPress={() => void Linking.openURL(TERMS_URL)}>
          terms of use
        </Text>{" "}
        and the{" "}
        <Text style={styles.link} onPress={() => void Linking.openURL(PRIVACY_URL)}>
          privacy policy
        </Text>
        . There is no tolerance for abusive listings, messages or comments —
        anything reported is read by the editors, and accounts that post it are
        removed.
      </Text>

      <Button
        label={busy ? "Creating…" : "Create account"}
        variant="primary"
        style={{ marginTop: space.s3 }}
        disabled={busy}
        onPress={() => void submit()}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s6, paddingBottom: space.s8 },
  agreement: {
    fontFamily: fonts.body,
    fontSize: 12,
    lineHeight: 19,
    color: ink.soft,
    marginTop: space.s2,
  },
  // accent-700, not accent: this is body-size text, and the interface accent
  // is only tuned to ~3:1 (see CLAUDE.md §1, the contrast rule).
  link: { color: colors.accent700, textDecorationLine: "underline" },
});
