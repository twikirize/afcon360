import React from "react";
import { AppScreen, PageHeader, Panel, EmptyState, StatusPill } from "@afcon360/mobile-ui";
export default function Earnings() {
  return <AppScreen><PageHeader eyebrow="Earnings" title="Know what you have earned." description="Driver earnings will be presented from canonical transport and wallet records, not calculated locally." /><Panel><StatusPill tone="gold">Live data not connected</StatusPill><EmptyState title="No earnings loaded" description="No balance, payout or trip amount is displayed until an authorized backend response is available." /></Panel></AppScreen>;
}
