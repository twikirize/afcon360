import React from "react";
import { useRouter } from "expo-router";
import { ActionButton, AppScreen, PageHeader, Panel, SectionTitle, ServiceTile } from "@afcon360/mobile-ui";

export default function Explore() {
  const router = useRouter();
  return <AppScreen>
    <PageHeader eyebrow="Explore" title="Make more of the journey." description="Book transport, accommodation, events and adventures natively in the app." />
    <Panel>
      <SectionTitle>Transport</SectionTitle>
      <ServiceTile title="Rides" description="On-demand transport with resolved locations, signed fares and server-certified payment options." symbol="🚘" />
      <ActionButton label="Book a ride" onPress={() => router.push("/(service)/ride" as never)} />
    </Panel>
    <Panel>
      <SectionTitle>Accommodation</SectionTitle>
      <ServiceTile title="Stays" description="Discover properties and manage accommodation reservations." symbol="🏨" />
      <ActionButton label="Find and book a stay" onPress={() => router.push("/(service)/stays" as never)} />
    </Panel>
    <Panel>
      <SectionTitle>Adventure & Events</SectionTitle>
      <ServiceTile title="Tours & Experiences" description="Explore packages, safaris and local providers." symbol="🧭" />
      <ActionButton label="Browse adventures" onPress={() => router.push("/(service)/adventure" as never)} />
      <ServiceTile title="Events" description="Discover events and registrations." symbol="🎟️" />
      <ActionButton label="Discover events and tickets" onPress={() => router.push("/(service)/events" as never)} />
    </Panel>
  </AppScreen>;
}