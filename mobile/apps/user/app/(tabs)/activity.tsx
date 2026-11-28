import React, { useCallback, useState } from "react";
import { ActivityIndicator, AppState, Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { palette as basePalette } from "@afcon360/mobile-ui";
import {
  PamojaEmptyState as EmptyState,
  PamojaScreen as AppScreen,
  PamojaPageHeader as PageHeader,
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
  PamojaStatusPill as StatusPill,
} from "../../src/components/PamojaScreen";
import { useFocusEffect } from "expo-router";
import { authClient } from "../../src/services/api";
import { useAuth } from "../../src/auth/AuthProvider";
import { SignInScreen } from "../../src/auth/SignInScreen";

const palette = {
  ...basePalette,
  canvas: "#F5F6F2",
  surface: "#FFFFFF",
  ink: "#122419",
  muted: "#6C766E",
  green: "#0E5B36",
  greenDark: "#093E24",
  greenSoft: "#E8F4EC",
  border: "#E6EAE4",
  warningSoft: "#FFF4D5",
};

type ActivityItem = { request_id: string; booking_reference: string; kind?: "request" | "booking"; status: string; converted?: boolean; booking_status?: string; booking_mode?: string; service_type?: string; created_at?: string; fare_estimate?: { amount?: number; currency?: string } };
export default function Activity() {
  const router = useRouter();
  const { user } = useAuth();
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    // These are the reader's own records, which the web fences behind a
    // session. Without one there is nothing to request, so the tab never lets
    // a backend refusal reach the screen.
    if (!user) {
      setItems([]);
      setError(null);
      setLoading(false);
      return;
    }
    try {
      const response = await authClient.request<{ success: boolean; data: { items: ActivityItem[] } }>("/api/mobile/v1/activity");
      setItems(response.data.items ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Activity could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [user]);
  useFocusEffect(
    useCallback(() => {
      void load();
      const subscription = AppState.addEventListener("change", state => {
        if (state === "active") void load();
      });
      return () => subscription.remove();
    }, [load])
  );

  // Signed out, this tab is the app's sign-in surface, mounted here in place —
  // the same treatment Account gets, because "your rides" is personal data and
  // the website answers an anonymous visit with a login redirect. Wallet is the
  // exception: the web publishes a guest page for it, so the app ports that.
  if (!user) {
    return <SignInScreen />;
  }

  return <AppScreen>
    <PageHeader eyebrow="Your activity" title="Your rides and bookings." description="Your recent ride requests and confirmed transport bookings are loaded from AFCON360." />
    <Panel>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <SectionTitle>Recent rides</SectionTitle>
        <Pressable onPress={() => { setLoading(true); void load(); }}><Text style={{ color: palette.greenDark, fontWeight: "800" }}>Refresh</Text></Pressable>
      </View>
      {loading ? <ActivityIndicator color={palette.green} /> : null}
      {error ? <Text style={{ color: "#9A3A2F" }}>{error}</Text> : null}
      {!loading && !error && items.length === 0 ? <EmptyState title="No rides yet" description="When you request or schedule a ride, its reference and latest status will appear here." /> : null}
      {items.map(item => (
        <Pressable key={(item.kind || "request") + ":" + item.request_id} onPress={() => router.push({ pathname: "/(service)/ride-status/[reference]", params: { reference: item.booking_reference || item.request_id, kind: item.kind || "request" } } as never)}
          style={{ borderTopWidth: 1, borderTopColor: palette.border, paddingVertical: 13, gap: 5 }}>
          <StatusPill tone={item.converted ? "green" : "gold"}>{String(item.booking_status ?? item.status).replace(/_/g, " ")}</StatusPill>
          <Text selectable style={{ color: palette.ink, fontWeight: "800" }}>{item.booking_reference || item.request_id}</Text>
          <Text style={{ color: palette.muted, fontSize: 12 }}>{item.fare_estimate?.amount ?? "Fare pending"} {item.fare_estimate?.currency ?? ""}</Text>
        </Pressable>
      ))}
    </Panel>
  </AppScreen>;
}
