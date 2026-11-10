import React from "react";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, ActionButton, StatusPill } from "@afcon360/mobile-ui";
import { useAuth } from "../../src/auth/AuthProvider";

export default function UserHome() {
  const router = useRouter();
  const { user } = useAuth();
  return <AppScreen>
    <PageHeader eyebrow="Pamoja · AFCON360" title="Your journey, together." description={user?.display_name ? "Welcome, " + user.display_name + ". Your East African journey starts here." : "One place for getting around, finding stays and discovering experiences across East Africa."} />
    <Panel>
      <StatusPill>Signed in securely</StatusPill>
      <SectionTitle>What would you like to do?</SectionTitle>
      <ServiceTile title="Book a ride" description="Choose verified locations, compare signed fares and confirm a payment method before requesting." symbol="🚗" />
      <ActionButton label="Book a ride" onPress={() => router.push("/(service)/ride" as never)} />
      <ServiceTile title="Find a place to stay" description="Search accommodation, review an AFCON360 quote and manage reservations from your Wallet." symbol="🛏️" />
      <ServiceTile title="Discover experiences" description="Find tours, events and things to do across the region." symbol="🧭" />
      <ActionButton label="Explore AFCON360 services" onPress={() => router.push("/(tabs)/explore")} />
    </Panel>
    <Panel>
      <SectionTitle>Your account and activity</SectionTitle>
      <ServiceTile title="Your ride history" description="See request references, matching progress and committed driver assignments." symbol="↗" />
      <ActionButton label="View your activity" onPress={() => router.push("/(tabs)/activity")} />
    </Panel>
  </AppScreen>;
}
