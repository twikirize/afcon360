import React from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import { spacing, radii } from "../../theme/tokens";
import type { RideServiceType, RideVip } from "./types";

type ServiceTypeSelectorProps = {
  serviceType: RideServiceType;
  vip: RideVip;
  onSelect: (serviceType: RideServiceType, vip: RideVip) => void;
};

const SERVICE_OPTIONS = [
  { key: "quick", serviceType: "on_demand", vip: false, icon: "⚡", name: "Quick", accessibilityLabel: "Quick ride" },
  { key: "airport", serviceType: "airport_departure", vip: false, icon: "✈", name: "Airport", accessibilityLabel: "Airport transfer" },
  { key: "vip", serviceType: "on_demand", vip: true, icon: "☆", name: "VIP", accessibilityLabel: "VIP service" },
] as const;

/** Equal-width, single-line choices that remain tappable on 360dp phones. */
export function ServiceTypeSelector({ serviceType, vip, onSelect }: ServiceTypeSelectorProps) {
  return (
    <View style={styles.serviceRow}>
      {SERVICE_OPTIONS.map(option => {
        const selected = serviceType === option.serviceType && vip === option.vip;
        return (
          <Pressable
            key={option.key}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            accessibilityLabel={option.accessibilityLabel}
            onPress={() => onSelect(option.serviceType, option.vip)}
            style={[styles.choice, selected && styles.choiceSelected]}
            hitSlop={{ top: 5, bottom: 5, left: 3, right: 3 }}
          >
            <Text style={[styles.icon, selected && styles.selectedText]}>{option.icon}</Text>
            <Text
              style={[styles.name, selected && styles.selectedText]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.85}
              maxFontSizeMultiplier={1.1}
            >
              {option.name}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  serviceRow: { flexDirection: "row", gap: spacing.sm },
  choice: {
    flex: 1,
    flexBasis: 0,
    minWidth: 0,
    minHeight: 46,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
    paddingHorizontal: 4,
    paddingVertical: 7,
    borderRadius: radii.lg,
    backgroundColor: "#F0F1F0",
    borderWidth: 1,
    borderColor: "#E8EBE8",
  },
  choiceSelected: { backgroundColor: "#0E9F5B", borderColor: "#0E9F5B" },
  icon: { color: "#26332B", fontSize: 15 },
  name: { color: "#26332B", fontSize: 12, fontWeight: "800", flexShrink: 1 },
  selectedText: { color: "#FFFFFF" },
});

export default ServiceTypeSelector;
