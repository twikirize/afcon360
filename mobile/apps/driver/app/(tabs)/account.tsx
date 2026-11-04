import React from "react";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, StatusPill } from "@afcon360/mobile-ui";
export default function DriverAccount() {
  return <AppScreen><PageHeader eyebrow="Driver account" title="Ready for the road." description="Your approval, documents, vehicle and operating permissions remain owned by AFCON360." /><Panel><StatusPill tone="gold">Native sign-in not connected</StatusPill><SectionTitle>Driver readiness</SectionTitle><ServiceTile title="Identity and compliance" description="Driver approval and verification status must be revalidated by the server." symbol="✓" /><ServiceTile title="Vehicle assignment" description="Assigned vehicles and eligibility are supplied by Transport." symbol="🚙" /><ServiceTile title="Support and safety" description="Safety and incident workflows will use approved regional support services." symbol="🛟" /></Panel></AppScreen>;
}
