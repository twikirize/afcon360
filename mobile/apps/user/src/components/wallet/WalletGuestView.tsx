import React from "react";
import { Text, View } from "react-native";
import { useRouter } from "expo-router";
import { ActionButton, AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, palette } from "@afcon360/mobile-ui";

/**
 * The signed-out wallet surface. It mirrors the website's public wallet page
 * (templates/wallet/wallet_home.html): what the wallet is for, how it works and
 * the three questions people ask before creating one. Nothing here calls the
 * wallet API, so a guest never sees an authorisation error.
 */
const BENEFITS = [
  { symbol: "⚡", title: "Fast payments", description: "Pay for tickets and packages without waiting." },
  { symbol: "🔒", title: "Secure transactions", description: "Your payment history is encrypted and protected." },
  { symbol: "💸", title: "Flexible payouts", description: "Receive agent payouts and refunds once activated." },
  { symbol: "➕", title: "Easy top-ups", description: "Add funds with the payment methods you already use." },
  { symbol: "📋", title: "Everything in one place", description: "Track spending and transactions without leaving the app." },
];

const STEPS = [
  { step: "1", title: "Create an account", description: "Sign up or sign in to your Pamoja identity." },
  { step: "2", title: "Activate your wallet", description: "Enable wallet features from your profile." },
  { step: "3", title: "Top up your balance", description: "Add funds using your preferred payment method." },
  { step: "4", title: "Use your wallet", description: "Pay for tickets and review your history." },
];

const QUESTIONS = [
  { question: "Is the wallet secure?", answer: "Yes. Funds and data are protected with encryption and current best practice." },
  { question: "How do I top up?", answer: "Use a card, a bank transfer, or another supported payment option." },
  { question: "Can I get refunds?", answer: "Refunds and agent payouts are available once your wallet is activated." },
  { question: "Do I need to sign in to browse?", answer: "No. You can read everything here; sign in or register only when you want to use the wallet." },
];

export function WalletGuestView() {
  const router = useRouter();

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Pamoja Wallet"
        title="Power your payments with our wallet."
        description="Quick, secure and easy payments for tickets, packages and more — all in one place."
      />

      <Panel>
        <ActionButton label="Create an account" onPress={() => router.push("/register")} />
        <ActionButton label="Sign in" onPress={() => router.push("/(tabs)/account" as never)} />
      </Panel>

      <Panel>
        <SectionTitle>Why use the wallet?</SectionTitle>
        {BENEFITS.map((benefit) => (
          <ServiceTile key={benefit.title} symbol={benefit.symbol} title={benefit.title} description={benefit.description} />
        ))}
      </Panel>

      <Panel>
        <SectionTitle>How it works</SectionTitle>
        {STEPS.map((entry) => (
          <View key={entry.step} style={{ flexDirection: "row", gap: 12, paddingVertical: 8 }}>
            <View style={{ width: 26, height: 26, borderRadius: 13, backgroundColor: palette.green, alignItems: "center", justifyContent: "center" }}>
              <Text style={{ color: "#FFFFFF", fontSize: 12, fontWeight: "800" }}>{entry.step}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "700" }}>{entry.title}</Text>
              <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>{entry.description}</Text>
            </View>
          </View>
        ))}
      </Panel>

      <Panel>
        <SectionTitle>Frequently asked questions</SectionTitle>
        {QUESTIONS.map((entry) => (
          <View key={entry.question} style={{ paddingVertical: 8 }}>
            <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "700" }}>{entry.question}</Text>
            <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>{entry.answer}</Text>
          </View>
        ))}
      </Panel>

      <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18, textAlign: "center" }}>
        Your wallet appears here as soon as you sign in.
      </Text>
    </AppScreen>
  );
}

export default WalletGuestView;
