import React from "react";
import type { ComponentProps } from "react";
import { Text, View } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { ActionButton, AppScreen, Panel, SectionTitle, palette } from "@afcon360/mobile-ui";

type IonName = ComponentProps<typeof Ionicons>["name"];

/**
 * The signed-out wallet surface, carried across from the website's public page
 * (templates/wallet/wallet_home.html, served by wallet.wallet_home and
 * wallet.home without a login). The copy below is the template's copy
 * verbatim: nothing is paraphrased, so an edit to the Jinja page is a small
 * diff here rather than a second sentence to maintain.
 *
 * Nothing on this screen calls the wallet API, so a guest never meets an
 * authorisation error. Signing in is required only to use the wallet.
 */
const BENEFITS: { icon: IonName; title: string; description: string }[] = [
  { icon: "flash", title: "Fast Payments", description: "Instantly pay for tickets and packages without delays." },
  { icon: "shield-checkmark", title: "Secure Transactions", description: "Your payment history is encrypted and safe." },
  { icon: "cash", title: "Flexible Payouts", description: "Receive agent payouts and refunds when activated." },
  { icon: "add-circle", title: "Easy Top-Ups", description: "Add funds with multiple payment methods." },
  { icon: "list", title: "Manage Everything", description: "Track your spending and transactions seamlessly." },
];

const STEPS: { title: string; description: string }[] = [
  { title: "Create an account", description: "Sign up or log in to your dashboard." },
  { title: "Activate your wallet", description: "Enable wallet features from your profile." },
  { title: "Top up balance", description: "Add funds using your preferred payment method." },
  { title: "Use your wallet", description: "Pay for tickets, view transaction history, and more." },
];

const QUESTIONS: { question: string; answer: string }[] = [
  { question: "Is the wallet secure?", answer: "Yes, we use encryption and best practices to ensure your funds and data are safe." },
  { question: "How do I top up my wallet?", answer: "You can add money via credit card, bank transfer, or other supported payment options." },
  { question: "Can I get refunds through the wallet?", answer: "Refunds and agent payouts are available once your wallet is activated." },
  { question: "Do I need to log in to view wallet features?", answer: "No, you can browse all features here. But to use the wallet, please log in or register." },
];

export function WalletGuestView() {
  const router = useRouter();
  const goToRegister = () => router.push("/register");
  const goToSignIn = () => router.push("/(tabs)/account" as never);

  return (
    <AppScreen
      footer={
        // Native upgrade: the website repeats these actions in a footer that
        // scrolls out of reach. Here they stay on screen for the whole page.
        <View style={{ flexDirection: "row", gap: 12 }}>
          <View style={{ flex: 1 }}>
            <ActionButton label="Get Started" onPress={goToRegister} />
          </View>
          <View style={{ flex: 1 }}>
            <ActionButton label="Sign In" variant="secondary" onPress={goToSignIn} />
          </View>
        </View>
      }
    >
      <View style={{ alignItems: "center", gap: 12, paddingTop: 8 }}>
        <View
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: palette.greenSoft, alignItems: "center", justifyContent: "center" }}
        >
          <Ionicons name="wallet" size={32} color={palette.green} />
        </View>
        <Text accessibilityRole="header" style={{ color: palette.ink, fontSize: 28, fontWeight: "800", lineHeight: 34, textAlign: "center", letterSpacing: -0.6 }}>
          Power Your Payments with Our Wallet
        </Text>
        <Text style={{ color: palette.muted, fontSize: 15, lineHeight: 22, textAlign: "center" }}>
          Quick, secure, and easy payments for tickets, packages, and more — all in one place.
        </Text>
        <View style={{ flexDirection: "row", gap: 12, alignSelf: "stretch", marginTop: 4 }}>
          <View style={{ flex: 1 }}>
            <ActionButton label="Get Started" onPress={goToRegister} />
          </View>
          <View style={{ flex: 1 }}>
            <ActionButton label="Sign In" variant="secondary" onPress={goToSignIn} />
          </View>
        </View>
      </View>

      <Panel>
        <SectionTitle>Why use our Wallet?</SectionTitle>
        {BENEFITS.map((benefit) => (
          <View key={benefit.title} style={{ flexDirection: "row", gap: 13, paddingVertical: 7 }}>
            <View
              accessibilityElementsHidden
              importantForAccessibility="no-hide-descendants"
              style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: palette.greenSoft, alignItems: "center", justifyContent: "center" }}
            >
              <Ionicons name={benefit.icon} size={20} color={palette.green} />
            </View>
            <View style={{ flex: 1, gap: 3 }}>
              <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "800" }}>{benefit.title}</Text>
              <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>{benefit.description}</Text>
            </View>
          </View>
        ))}
      </Panel>

      <Panel>
        <SectionTitle>How It Works</SectionTitle>
        {STEPS.map((step, index) => (
          <View key={step.title} style={{ flexDirection: "row", gap: 12, paddingVertical: 8 }}>
            <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: palette.green, alignItems: "center", justifyContent: "center" }}>
              <Text style={{ color: "#FFFFFF", fontSize: 13, fontWeight: "800" }}>{index + 1}</Text>
            </View>
            <View style={{ flex: 1, gap: 3 }}>
              <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "700" }}>{step.title}</Text>
              <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>{step.description}</Text>
            </View>
          </View>
        ))}
      </Panel>

      <Panel>
        <SectionTitle>Frequently Asked Questions</SectionTitle>
        {QUESTIONS.map((entry) => (
          <View key={entry.question} style={{ gap: 3, paddingVertical: 7 }}>
            <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "800" }}>{entry.question}</Text>
            <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>{entry.answer}</Text>
          </View>
        ))}
      </Panel>

      <Text style={{ color: palette.muted, fontSize: 14, lineHeight: 21, textAlign: "center", paddingVertical: 8 }}>
        Ready to get started?{" "}
        <Text accessibilityRole="link" onPress={goToRegister} style={{ color: palette.green, fontWeight: "800" }}>
          Create an account
        </Text>{" "}
        or{" "}
        <Text accessibilityRole="link" onPress={goToSignIn} style={{ color: palette.green, fontWeight: "800" }}>
          log in
        </Text>
      </Text>
    </AppScreen>
  );
}

export default WalletGuestView;