import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { palette as basePalette } from "@afcon360/mobile-ui";
import {
  PamojaScreen as AppScreen,
  PamojaPageHeader as PageHeader,
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
  PamojaActionButton as ActionButton,
} from "../../src/components/PamojaScreen";
import { ServiceHeroAccent } from "../../src/components/ServiceHeroAccent";

const palette = {
  ...basePalette,
  canvas: "#F5F6F2",
  surface: "#FFFFFF",
  ink: "#122419",
  muted: "#6C766E",
  green: "#0E5B36",
  greenDark: "#093E24",
  greenSoft: "#E8F4EC",
  border: "#E6EAE4",
  warningSoft: "#FFF4D5",
};

const SITE = "https://www.pamoja.space";

export default function Adventure() {
  return (
    <AppScreen>
      <PageHeader
        eyebrow="Adventure"
        title="Tours, safaris & experiences"
        description="Curated adventures across East Africa — coming soon to the native app."
      />

      <ServiceHeroAccent serviceKey="adventure" title="Coming soon" subtitle="Tours, safaris & experiences" />

      <Panel>
        <SectionTitle>Coming Soon</SectionTitle>
        <Text style={{ color: palette.muted, lineHeight: 22, fontSize: 14 }}>
          Our Adventure module (tours, safaris, and local experiences) is currently available on the Pamoja website.
          Native booking, itinerary management, and Wallet integration are under development.
        </Text>
      </Panel>

      <Panel>
        <SectionTitle>Explore on the Website</SectionTitle>
        <Text style={{ color: palette.muted, lineHeight: 20, fontSize: 13, marginBottom: 12 }}>
          Browse available experiences, view itineraries, and book directly on Pamoja.
        </Text>
        <ActionButton
          label="Open Adventures on Pamoja"
          onPress={() => void WebBrowser.openBrowserAsync(`${SITE}/tourism`)}
        />
      </Panel>

      <Panel>
        <SectionTitle>What's Planned</SectionTitle>
        <View style={styles.featureList}>
          {[
            "Browse tours, safaris & cultural experiences with rich media",
            "View detailed itineraries, inclusions & group sizes",
            "Check real-time availability & get instant price quotes",
            "Book & pay securely with your Pamoja Wallet",
            "Manage bookings, vouchers & guide contact in My Adventures",
            "Offline access to confirmations & day-of details",
          ].map((item, index) => (
            <View key={index} style={styles.featureRow}>
              <View style={styles.featureDot} />
              <Text style={styles.featureText}>{item}</Text>
            </View>
          ))}
        </View>
      </Panel>

      <Panel>
        <SectionTitle>Stay Updated</SectionTitle>
        <Text style={{ color: palette.muted, lineHeight: 20, fontSize: 13 }}>
          We'll notify you in-app when native Adventures launches. In the meantime, Transport, Stays, Events, and Wallet are fully available.
        </Text>
      </Panel>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  featureList: { gap: 10 },
  featureRow: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  featureDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: "#0E5B36",
    marginTop: 7,
    flexShrink: 0,
  },
  featureText: { flex: 1, color: "#122419", fontSize: 13, lineHeight: 19 },
});