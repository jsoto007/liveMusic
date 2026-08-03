/** Sign in and join. */

import { useState } from "react";
import { ScrollView, StyleSheet, TextInput } from "react-native";
import { useNavigation } from "@react-navigation/native";

import { Body, Button, Field, Heading, Notice, inputStyle } from "../components/ui";
import { useAuth } from "../lib/auth";
import { colors, ink, space } from "../lib/theme";
import type { RootNavigation } from "../navigation/types";

const MIN_PASSWORD_LENGTH = 12;

export function SignInScreen() {
  const navigation = useNavigation<RootNavigation>();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

      <Button
        label={busy ? "Creating…" : "Create account"}
        variant="primary"
        disabled={busy}
        onPress={() => void submit()}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: 20, paddingTop: space.s6, paddingBottom: space.s8 },
});
