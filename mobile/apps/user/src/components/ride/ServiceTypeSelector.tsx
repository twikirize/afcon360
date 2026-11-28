import React from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import { colors, spacing, radii } from "../../theme/tokens";
import type { RideServiceType, RideVip } from "./types";

type ServiceTypeSelectorProps = {
  serviceType: RideServiceType;
  vip: RideVip;
  onSelect: (serviceType: RideServiceType, vip: RideVip) => void;
};

// Short labels, exactly like the web's .svc-label at 360dp. "Airport
// Transfer" wrapped to two lines and pushed "VIP Service" out of the row;
// three words that fit on one line solve it without shrinking the type.
const SERVICE_OPTIONS = [
  {
    key: "quick",
    serviceType: "on_demand",
    vip: false,
    icon: "◷",
    name: "Quick",
    accessibilityLabel: "Quick ride",
  },
  {
    key: "airport",
    serviceType: "airport_departure",
    vip: false,
    icon: "✈",
    name: "Airport",
    accessibilityLabel: "Airport transfer",
  },
  {
    key: "vip",
    serviceType: "on_demand",
    vip: true,
    icon: "★",
    name: "VIP",
    accessibilityLabel: "VIP service",
  },
] as const;

export function ServiceTypeSelector({ serviceType, vip, onSelect }: ServiceTypeSelectorProps) {
  return (
    <View style={styles.serviceRow}>
      {SERVICE_OPTIONS.map((option) => {
        const isSelected = serviceType === option.serviceType && vip === option.vip;
        return (
          <Pressable
            key={option.key}
            accessibilityRole="button"
            accessibilityState={{ selected: isSelected }}
            accessibilityLabel={option.accessibilityLabel}
            onPress={() => onSelect(option.serviceType, option.vip)}
            style={[
              styles.serviceChoice,
              isSelected && (option.vip ? styles.serviceVipSelected : styles.serviceSelected),
            ]}
            hitSlop={{ top: 6, bottom: 6, left: 4, right: 4 }}
          >
            <Text style={styles.serviceIcon}>{option.icon}</Text>
            <Text
              style={styles.serviceName}
              numberOfLines={1}
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
  serviceRow: { flexDirection: "row", gap: spacing.xs },
  serviceChoice: {
    // Equal thirds with a 44dp minimum touch target. flexBasis 0 is what
    // forces each label to fit its share instead of overrunning the row.
    flex: 1,
    flexBasis: 0,
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    paddingVertical: spacing.sm,
    paddingHorizontal: 4,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface.white,
  },
  serviceSelected: {
    borderColor: colors.brand.green,
    backgroundColor: colors.brand.greenSoft,
  },
  serviceVipSelected: {
    borderColor: colors.brand.gold,
    backgroundColor: colors.brand.goldSoft,
  },
  serviceIcon: { fontSize: 16 },
  serviceName: {
    color: colors.text.ink,
    fontSize: 12,
    fontWeight: "800",
    flexShrink: 1,
  },
});

export default ServiceTypeSelector;
