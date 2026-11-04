import React from "react";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, ActionButton, StatusPill } from "@afcon360/mobile-ui";
export default function UserHome() {
  const router = useRouter();
  return <AppScreen>
    <PageHeader eyebrow="Pamoja · AFCON360" title="Your journey, together." description="One place for getting around, finding stays and discovering experiences across East Africa." />
    <Panel>
      <StatusPill tone="gold">Native app foundation</StatusPill>
      <SectionTitle>What would you like to do?</SectionTitle>
      <ServiceTile title="Book a ride" description="Choose a route and review your fare before requesting." symbol="🚗" />
      <ServiceTile title="Find a place to stay" description="Explore accommodation and manage reservations." symbol="🛏️" />
      <ServiceTile title="Discover experiences" description="Find tours, events and things to do." symbol="🧭" />
      <ServiceTile title="Manage your money" description="View wallet activity after secure account connection." symbol="◈" />
      <ActionButton label="Explore AFCON360 services" onPress={() => router.push("/(tabs)/explore")} />
    </Panel>
    <Panel><SectionTitle>Your account and activity</SectionTitle><ServiceTile title="No account data displayed yet" description="Native sign-in and API session contracts are being connected. This app will not invent balances, bookings or personal details." symbol="🔒" /></Panel>
  </AppScreen>;
}
