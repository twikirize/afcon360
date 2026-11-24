import React from "react";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { ActionButton, AppScreen, PageHeader, Panel, SectionTitle } from "@afcon360/mobile-ui";
import { ServiceGrid } from "../../src/components/ServiceGrid";

const SITE = "https://www.pamoja.space";

export default function Explore() {
  const router = useRouter();

  const openService = (service: string) => {
    switch (service) {
      case "rides":
        router.push("/(service)/ride" as never);
        break;
      case "stays":
        router.push("/(service)/stays" as never);
        break;
      case "events":
        router.push("/(service)/events" as never);
        break;
      case "adventure":
        router.push("/(service)/adventure" as never);
        break;
      default:
        break;
    }
  };

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Explore"
        title="Make more of the journey."
        description="Book transport, accommodation, events and adventures natively in the app."
      />
      <ServiceGrid onServicePress={openService} />
      <Panel>
        <SectionTitle>Partner with Pamoja</SectionTitle>
        <ActionButton
          label="Become a partner on website"
          onPress={() => void WebBrowser.openBrowserAsync(`${SITE}/onboarding/choose`)}
        />
      </Panel>
    </AppScreen>
  );
}