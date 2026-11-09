import React from "react";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { ActionButton, AppScreen, PageHeader, Panel, SectionTitle, ServiceTile } from "@afcon360/mobile-ui";

const SITE = "https://www.pamoja.space";

export default function Explore() {
  const router = useRouter();
  return <AppScreen>
    <PageHeader eyebrow="Explore" title="Make more of the journey." description="Book transport and accommodation natively. Events and free tickets are available natively; tours and experiences still open the AFCON360 website." />
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
      <SectionTitle>Tourism and events</SectionTitle>
      <ServiceTile title="Tours and experiences" description="Explore packages and local providers." symbol="🧭" />
      <ActionButton label="Explore tourism on website" onPress={() => WebBrowser.openBrowserAsync(SITE + "/tourism")} />
      <ServiceTile title="Events" description="Discover events and registrations." symbol="🎟️" />
      <ActionButton label="Discover events and tickets" onPress={() => router.push("/(service)/events" as never)} />
    </Panel>
  </AppScreen>;
}
