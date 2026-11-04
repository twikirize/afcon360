import React from "react";
import { AppScreen, PageHeader, Panel, SectionTitle, ServiceTile, StatusPill } from "@afcon360/mobile-ui";
export default function Account() {
  return <AppScreen><PageHeader eyebrow="Account" title="Your AFCON360 identity." description="Your account, roles and verification state are owned by AFCON360 identity services." /><Panel><StatusPill tone="gold">Native sign-in not connected</StatusPill><SectionTitle>Secure access</SectionTitle><ServiceTile title="Sign-in and account recovery" description="Mobile session endpoints must be implemented and security-tested before credentials can be submitted here." symbol="🔐" /><ServiceTile title="Identity and verification" description="KYC status and profile details will be fetched from existing identity and KYC services." symbol="✓" /></Panel></AppScreen>;
}
