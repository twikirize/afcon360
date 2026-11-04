import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";
import { AppScreen, PageHeader, Panel, SectionTitle, StatusPill, EmptyState, palette } from "@afcon360/mobile-ui";
import { authClient } from "../../src/services/api";

type Earning = { currency: string; gross_captured: string; driver_earnings: string; platform_commission_rate: string };
export default function Earnings() {
  const [items, setItems] = useState<Earning[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const response = await authClient.request<{ success: boolean; data: { by_currency: Earning[] } }>("/api/mobile/v1/driver/earnings");
      setItems(response.data.by_currency ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Earnings could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  return <AppScreen>
    <PageHeader eyebrow="Earnings" title="Know what you have earned." description="Figures are calculated from completed trips whose payments have been captured. Different currencies are shown separately." />
    <Panel>
      <SectionTitle>Captured trip earnings</SectionTitle>
      {loading ? <ActivityIndicator color={palette.green} /> : null}
      {error ? <Text style={{ color: "#9A3A2F" }}>{error}</Text> : null}
      {!loading && !error && items.length === 0 ? <EmptyState title="No captured earnings yet" description="Your earnings will appear after a trip is completed and the selected payment method is settled." /> : null}
      {items.map(item => (
        <View key={item.currency} style={{ borderTopWidth: 1, borderTopColor: palette.border, paddingVertical: 13, gap: 5 }}>
          <StatusPill>{item.currency}</StatusPill>
          <Text style={{ color: palette.ink, fontSize: 24, fontWeight: "900" }}>{item.driver_earnings} {item.currency}</Text>
          <Text style={{ color: palette.muted, fontSize: 12 }}>Gross captured: {item.gross_captured} {item.currency}</Text>
          <Text style={{ color: palette.muted, fontSize: 12 }}>Platform commission rate: {item.platform_commission_rate}%</Text>
        </View>
      ))}
    </Panel>
  </AppScreen>;
}
