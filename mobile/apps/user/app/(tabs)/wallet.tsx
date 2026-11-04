import React from "react";
import { AppScreen, PageHeader, Panel, EmptyState, StatusPill } from "@afcon360/mobile-ui";
export default function Wallet() {
  return <AppScreen><PageHeader eyebrow="Wallet" title="Your money, clearly managed." description="The AFCON360 wallet remains the single owner of balances, payments and ledger movements." /><Panel><StatusPill tone="gold">Secure connection required</StatusPill><EmptyState title="No balance has been loaded" description="Only a balance returned by the authenticated wallet API will be displayed. No sample balance or local wallet ledger is used." /></Panel></AppScreen>;
}
