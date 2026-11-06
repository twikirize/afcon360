import React, { useCallback, useState } from "react";
import { ActivityIndicator, AppState, Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, StatusPill, palette, EmptyState } from "@afcon360/mobile-ui";
import { useFocusEffect } from "expo-router";
import { authClient } from "../../src/services/api";

type ActivityItem = { request_id: string; booking_reference: string; status: string; converted?: boolean; booking_status?: string; created_at?: string; fare_estimate?: { amount?: number; currency?: string } };
export default function Activity() {
  const router = useRouter();
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await authClient.request<{ success: boolean; data: { items: ActivityItem[] } }>("/api/mobile/v1/activity");
      setItems(response.data.items ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Activity could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);
  useFocusEffect(
    useCallback(() => {
      void load();
      const subscription = AppState.addEventListener("change", state => {
        if (state === "active") void load();
      });
      return () => subscription.remove();
    }, [load])
  );

  return <AppScreen>
    <PageHeader eyebrow="Your activity" title="Your rides and bookings." description="Recent transport requests are loaded from AFCON360. Other services remain managed by their owning booking modules." />
    <Panel>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <SectionTitle>Recent rides</SectionTitle>
        <Pressable onPress={() => { setLoading(true); void load(); }}><Text style={{ color: palette.greenDark, fontWeight: "800" }}>Refresh</Text></Pressable>
      </View>
      {loading ? <ActivityIndicator color={palette.green} /> : null}
      {error ? <Text style={{ color: "#9A3A2F" }}>{error}</Text> : null}
      {!loading && !error && items.length === 0 ? <EmptyState title="No rides yet" description="When you request a ride, its reference and matching status will appear here." /> : null}
      {items.map(item => (
        <Pressable key={item.request_id} onPress={() => router.push({ pathname: "/ride-status/[reference]", params: { reference: item.booking_reference || item.request_id } })}
          style={{ borderTopWidth: 1, borderTopColor: palette.border, paddingVertical: 13, gap: 5 }}>
          <StatusPill tone={item.converted ? "green" : "gold"}>{item.booking_status ?? item.status}</StatusPill>
          <Text selectable style={{ color: palette.ink, fontWeight: "800" }}>{item.booking_reference || item.request_id}</Text>
          <Text style={{ color: palette.muted, fontSize: 12 }}>{item.fare_estimate?.amount ?? "Fare pending"} {item.fare_estimate?.currency ?? ""}</Text>
        </Pressable>
      ))}
    </Panel>
  </AppScreen>;
}
