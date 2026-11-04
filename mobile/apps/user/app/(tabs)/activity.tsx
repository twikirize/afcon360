import React from "react";
import { AppScreen, PageHeader, Panel, EmptyState } from "@afcon360/mobile-ui";
export default function Activity() {
  return <AppScreen><PageHeader eyebrow="Your activity" title="All your plans in one place." description="Rides, accommodation reservations and event activity will be shown here from their owning AFCON360 services." /><Panel><EmptyState title="Your activity will appear here" description="Sign-in and read-only booking APIs must be connected before this screen can show live records." /></Panel></AppScreen>;
}
