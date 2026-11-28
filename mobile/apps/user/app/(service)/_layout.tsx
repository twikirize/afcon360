import React from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { Stack } from "expo-router";
import { palette } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";

/**
 * The service stack reproduces the Jinja surfaces rather than re-deciding who
 * may look at them.
 *
 * On the web, transport, accommodation, events and tourism are public pages:
 * `transport.routes.home`, `accommodation.routes.guest_search`,
 * `events.routes.list` and `tourism.routes.home` carry no `login_required`.
 * The only fencing on those pages is `{% if current_user.is_authenticated %}`
 * around the reader's own records — recent rides in
 * `templates/transport/new_home.html`, "Login to Book" in
 * `templates/accommodation/guest/detail.html`, the organizer block in
 * `templates/events/public/list.html`.
 *
 * A native route group cannot render one page two ways, so that fence moves
 * from the page onto the routes that exist only for a signed-in reader:
 * account settings, account deletion, and one rider's own trip. The four
 * public pages stay open to everyone.
 */
export default function UserServiceRoutes() {
  const { user, loading, restoreError, retryRestoreSession } = useAuth();

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: palette.canvas }}>
        <ActivityIndicator color={palette.green} />
      </View>
    );
  }

  if (restoreError) return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 24, backgroundColor: palette.canvas }}><Text style={{ color: palette.ink, textAlign: "center", lineHeight: 22 }}>{restoreError}</Text><Pressable accessibilityRole="button" onPress={() => void retryRestoreSession()} style={{ marginTop: 16, padding: 14, backgroundColor: palette.green, borderRadius: 10 }}><Text style={{ color: "#FFFFFF", fontWeight: "800" }}>Retry saved session</Text></Pressable></View>;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={Boolean(user)} redirectTo="/login">
        <Stack.Screen name="settings" />
        <Stack.Screen name="delete-account" />
        <Stack.Screen name="ride-status/[reference]" />
      </Stack.Protected>
    </Stack>
  );
}
