import React from "react";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile } from "@afcon360/mobile-ui";
export default function Explore() {
  return <AppScreen>
    <PageHeader eyebrow="Explore" title="Make more of the journey." description="AFCON360 brings connected travel services together. Availability and booking actions will appear when the mobile API is ready." />
    <Panel><SectionTitle>Transport</SectionTitle><ServiceTile title="Rides" description="On-demand and scheduled transport, with fare details before confirmation." symbol="🚘" /></Panel>
    <Panel><SectionTitle>Accommodation</SectionTitle><ServiceTile title="Stays" description="Discover properties, review room availability and manage reservations." symbol="🏨" /></Panel>
    <Panel><SectionTitle>Tourism and events</SectionTitle><ServiceTile title="Tours and experiences" description="Explore places and packages offered by local providers." symbol="🧭" /><ServiceTile title="Events" description="Discover events and keep registrations together." symbol="🎟️" /></Panel>
  </AppScreen>;
}
