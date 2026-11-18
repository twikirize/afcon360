import React from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import type { RideServiceType, RideVip } from "./types";

type ServiceTypeSelectorProps = {
  serviceType: RideServiceType;
  vip: RideVip;
  onSelect: (serviceType: RideServiceType, vip: RideVip) => void;
};

const SERVICE_OPTIONS = [
  { serviceType: "on_demand", vip: false, icon: "◷", name: "Quick Ride" },
  { serviceType: "airport_departure", vip: false, icon: "✈", name: "Airport Transfer" },
  { serviceType: "on_demand", vip: true, icon: "★", name: "VIP Service" },
] as const;

export function ServiceTypeSelector({ serviceType, vip, onSelect }: ServiceTypeSelectorProps) {
  return (
    <View style={styles.serviceRow}>
      {SERVICE_OPTIONS.map((option) => {
        const isSelected = serviceType === option.serviceType && vip === option.vip;
        const isAirport = option.serviceType === "airport_departure";
        return (
          <Pressable
            key={option.serviceType + ":" + option.vip}
            onPress={() => onSelect(option.serviceType, option.vip)}
            style={[
              styles.serviceChoice,
              isSelected && (isAirport ? styles.serviceAirportSelected : styles.serviceSelected),
              isSelected && !isAirport && option.vip && styles.serviceVipSelected,
            ]}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={styles.serviceIcon}>{option.icon}</Text>
            <Text style={styles.serviceName}>{option.name}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  serviceRow: { flexDirection: "row", gap: spacing.sm },
  serviceChoice: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface.white,
  },
  serviceSelected: {
    borderColor: colors.brand.green,
    backgroundColor: colors.brand.greenSoft,
  },
  serviceAirportSelected: {
    borderColor: colors.brand.green,
    backgroundColor: colors.brand.greenSoft,
  },
  serviceVipSelected: {
    borderColor: colors.brand.gold,
    backgroundColor: colors.brand.goldSoft,
  },
  serviceIcon: { fontSize: 18 },
  serviceName: { color: colors.text.ink, fontSize: 13, fontWeight: "800" },
});

export default ServiceTypeSelector;