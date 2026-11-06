import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";
import {
  ActionButton,
  AppScreen,
  EmptyState,
  PageHeader,
  Panel,
  SectionTitle,
  StatusPill,
  palette
} from "@afcon360/mobile-ui";
import { authClient } from "../../src/services/api";

type Earning = {
  currency: string;
  gross_captured: string;
  driver_earnings: string;
  platform_commission_rate: string;
};

export default function Earnings() {
  const [items, setItems] = useState<Earning[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await authClient.request<{
        success: boolean;
        data: { by_currency: Earning[] };
      }>("/api/mobile/v1/driver/earnings");
      setItems(response.data.by_currency ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Earnings could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Earnings"
        title="Know what you have earned."
        description="Only captured trip payments are included. Each currency is shown separately; figures are never combined across currencies."
      />
      <Panel>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <SectionTitle>Captured trip earnings</SectionTitle>
          <StatusPill tone="neutral">{items.length} {items.length === 1 ? "currency" : "currencies"}</StatusPill>
        </View>

        {loading ? <ActivityIndicator color={palette.green} /> : null}
        {error ? (
          <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>
            {error}
          </Text>
        ) : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState
            title="No captured earnings yet"
            description="Your earnings appear after a trip is completed and the selected payment method is settled."
          />
        ) : null}

        {items.map(item => (
          <View
            key={item.currency}
            style={{
              gap: 9,
              padding: 14,
              borderRadius: 15,
              borderWidth: 1,
              borderColor: palette.border,
              backgroundColor: "#F8FBF9"
            }}
          >
            <StatusPill tone="neutral">{item.currency}</StatusPill>
            <Text style={{ color: palette.muted, fontSize: 11, fontWeight: "700" }}>
              Your captured driver earnings
            </Text>
            <Text style={{ color: palette.ink, fontSize: 26, fontWeight: "900" }}>
              {item.driver_earnings} {item.currency}
            </Text>
            <View style={{ height: 1, backgroundColor: palette.border }} />
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 16 }}>
              <View style={{ flex: 1, minWidth: 120, gap: 3 }}>
                <Text style={{ color: palette.muted, fontSize: 11 }}>Gross captured</Text>
                <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "700" }}>
                  {item.gross_captured} {item.currency}
                </Text>
              </View>
              <View style={{ flex: 1, minWidth: 120, gap: 3 }}>
                <Text style={{ color: palette.muted, fontSize: 11 }}>Platform commission</Text>
                <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "700" }}>
                  {item.platform_commission_rate}%
                </Text>
              </View>
            </View>
          </View>
        ))}

        <ActionButton
          label={loading ? "Refreshing…" : "Refresh earnings"}
          disabled={loading}
          onPress={() => { setLoading(true); void load(); }}
        />
      </Panel>
    </AppScreen>
  );
}
