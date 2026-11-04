import React from "react";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, StatusPill } from "@afcon360/mobile-ui";
export default function DriverHome() {
  return <AppScreen>
    <PageHeader eyebrow="AFCON360 Driver" title="Your driving workspace." description="A focused phone-first workspace for availability, ride offers and active trips." />
    <Panel><StatusPill tone="gold">Driver account connection pending</StatusPill><SectionTitle>Availability</SectionTitle><ServiceTile title="Not online" description="Online/offline controls activate only after the authenticated driver session and go-live API are connected." symbol="●" /></Panel>
    <Panel><SectionTitle>Ride requests</SectionTitle><ServiceTile title="No live offers loaded" description="Offers come from the transport dispatch service. This screen never creates sample requests." symbol="🔔" /></Panel>
    <Panel><SectionTitle>Trip operations</SectionTitle><ServiceTile title="Your next action" description="Assigned trips, pickup details and trip status will appear from the authoritative transport API." symbol="🧭" /><ServiceTile title="Location permission" description="Foreground location access is configured. Background tracking remains off until the driver workflow, privacy notice and store requirements are approved." symbol="📍" /></Panel>
  </AppScreen>;
}
