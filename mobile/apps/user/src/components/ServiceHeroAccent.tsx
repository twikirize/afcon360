import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { getServiceConfig } from "./ServiceEntry";
import { colors, spacing, radii } from "../theme/tokens";

type ServiceHeroAccentProps = {
  serviceKey: "rides" | "stays" | "events" | "adventure" | "wallet" | "tourism";
  title?: string;
  subtitle?: string;
};

export function ServiceHeroAccent({ serviceKey, title, subtitle }: ServiceHeroAccentProps) {
  const config = getServiceConfig(serviceKey);
  if (!config) return null;

  const accentColors: Record<string, { gradient: string; iconBg: string }> = {
    rides: { gradient: "linear-gradient(135deg, #EAF0FA 0%, #D8E4F6 100%)", iconBg: "#D8E4F6" },
    stays: { gradient: "linear-gradient(135deg, #EAF3EB 0%, #D7E8D9 100%)", iconBg: "#D7E8D9" },
    events: { gradient: "linear-gradient(135deg, #FFF8E6 0%, #FCE9B5 100%)", iconBg: "#FCE9B5" },
    adventure: { gradient: "linear-gradient(135deg, #F0F3E5 0%, #E1E9C9 100%)", iconBg: "#E1E9C9" },
    wallet: { gradient: "linear-gradient(135deg, #E8F4EC 0%, #CDEBD0 100%)", iconBg: "#CDEBD0" },
    tourism: { gradient: "linear-gradient(135deg, #F5F0E8 0%, #E8DCC8 100%)", iconBg: "#E8DCC8" },
  };

  const accent = accentColors[serviceKey] || accentColors.rides;

  return (
    <View style={[styles.container, { backgroundColor: config.bgColor }]}>
      <View style={styles.iconWrapper}>
        <View style={[styles.iconBg, { backgroundColor: accent.iconBg }]}>
          <Text style={styles.iconText}>{config.icon}</Text>
        </View>
      </View>
      <View style={styles.textWrapper}>
        {title ? <Text style={styles.title}>{title}</Text> : <Text style={styles.title}>{config.label}</Text>}
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : <Text style={styles.subtitle}>{config.hint}</Text>}
      </View>
      <View style={styles.arrow} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radii.xl,
    borderWidth: 1,
    borderColor: "#E6EAE4",
    marginBottom: spacing.md,
  },
  iconWrapper: {
    width: 56,
    height: 56,
    borderRadius: radii.xl,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#FFFFFF",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  iconBg: {
    width: 44,
    height: 44,
    borderRadius: radii.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  iconText: { fontSize: 26 },
  textWrapper: { flex: 1, gap: 2 },
  title: { color: colors.brand.dark, fontSize: 18, fontWeight: "900", letterSpacing: -0.3 },
  subtitle: { color: colors.text.muted, fontSize: 12, fontWeight: "600" },
  arrow: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.60)",
    borderWidth: 1,
    borderColor: "rgba(23,61,40,0.07)",
    alignItems: "center",
    justifyContent: "center",
  },
});