import React, { useCallback, useState } from "react";
import { ActivityIndicator, AppState, Text, View } from "react-native";
import { AppScreen, PageHeader, Panel, SectionTitle, StatusPill, palette } from "@afcon360/mobile-ui";
import { useFocusEffect } from "expo-router";
import { authClient } from "../../src/services/api";

type WalletData = { exists: boolean; balance?: string | number; currency?: string; is_frozen?: boolean };
export default function Wallet() {
  const [wallet, setWallet] = useState<WalletData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const response = await authClient.request<{ status: string; data: WalletData }>("/api/wallet/me");
      setWallet(response.data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Wallet information is unavailable.");
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
    <PageHeader eyebrow="Wallet" title="Your money, clearly managed." description="Balances and payment status are returned by the AFCON360 Wallet ledger. No balance is calculated or stored in this app." />
    <Panel>
      <SectionTitle>Wallet balance</SectionTitle>
      {loading ? <ActivityIndicator color={palette.green} /> : null}
      {error ? <Text style={{ color: "#9A3A2F" }}>{error}</Text> : null}
      {!loading && !error && wallet ? (
        <>
          <StatusPill tone={wallet.is_frozen ? "gold" : "green"}>{wallet.is_frozen ? "Wallet restricted" : wallet.exists ? "Wallet active" : "Wallet not created"}</StatusPill>
          <Text style={{ color: palette.ink, fontSize: 28, fontWeight: "900" }}>{wallet.exists ? wallet.balance : "—"} {wallet.currency ?? ""}</Text>
          <Text style={{ color: palette.muted, fontSize: 12 }}>Live response from AFCON360 Wallet</Text>
        </>
      ) : null}
    </Panel>
  </AppScreen>;
}
