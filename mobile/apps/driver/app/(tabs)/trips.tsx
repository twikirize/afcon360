import React from "react";
import { AppScreen, PageHeader, Panel, EmptyState } from "@afcon360/mobile-ui";
export default function Trips() {
  return <AppScreen><PageHeader eyebrow="Trips" title="Your assigned work." description="Only server-confirmed assignments and trip states will be shown here." /><Panel><EmptyState title="No trip data loaded" description="Driver authentication and transport read APIs must be connected before trip history or active assignments can appear." /></Panel></AppScreen>;
}
