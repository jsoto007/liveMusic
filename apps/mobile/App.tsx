/**
 * Live Msc — app root.
 *
 * The Classical faces are loaded before anything renders: falling back to the
 * system font for a frame and then reflowing would break the one thing the
 * design is built on.
 */

import { useCallback } from "react";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { ActivityIndicator, View } from "react-native";
import {
  CormorantGaramond_400Regular,
  CormorantGaramond_600SemiBold,
  useFonts,
} from "@expo-google-fonts/cormorant-garamond";
import { Lora_400Regular, Lora_400Regular_Italic } from "@expo-google-fonts/lora";

import { AuthProvider } from "./lib/auth";
import { Navigation } from "./navigation";
import { colors } from "./lib/theme";

export default function App() {
  const [fontsLoaded, fontError] = useFonts({
    CormorantGaramond_400Regular,
    CormorantGaramond_600SemiBold,
    Lora_400Regular,
    Lora_400Regular_Italic,
  });

  const ready = fontsLoaded || Boolean(fontError);

  const renderApp = useCallback(
    () => (
      <AuthProvider>
        <StatusBar style="dark" />
        <Navigation />
      </AuthProvider>
    ),
    [],
  );

  return (
    <SafeAreaProvider>
      {ready ? (
        renderApp()
      ) : (
        <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: "center" }}>
          <ActivityIndicator color={colors.accent} />
        </View>
      )}
    </SafeAreaProvider>
  );
}
