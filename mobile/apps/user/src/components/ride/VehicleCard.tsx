import React from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import { colors, spacing, radii, typography, shadows } from "../theme/tokens";
import { formatMoney } from "./utils";
import type { Quote } from "./types";

type VehicleCardProps = {
  quote: Quote;
  selected: boolean;
  onPress: () => void;
};

export function VehicleCard({ quote, selected, onPress }: VehicleCardProps) {
  const cur = quote.display_currency ?? quote.currency;
  const amount = quote.display_amount ?? quote.fare_total;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.vehicleCard,
        selected && styles.vehicleSelected,
      ]}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <View style={styles.vehicleHeader}>
        <View style={styles.vehicleIcon}><Text style={styles.vehicleIconText}>🚘</Text></View>
        <View style={styles.vehicleCopy}>
          <Text style={styles.vehicleName}>{quote.display_name}</Text>
          <Text style={styles.helperText}>{quote.vehicle_class.replace(/_/g, " ")}</Text>
        </View>
        <Text style={styles.vehiclePrice}>{formatMoney(Number(amount), cur)}</Text>
      </View>
      <Text style={styles.vehicleSub}>
        {quote.display_is_approximate
          ? "Indicative home-currency display · fare is " + formatMoney(quote.fare_total, quote.currency)
          : "Authoritative fare · " + quote.currency}
      </Text>
      {selected && <Text style={styles.selectedTag}>Selected</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  vehicleCard: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.md,
    backgroundColor: colors.surface.white,
    ...shadows.card,
  },
  vehicleSelected: {
    borderColor: colors.brand.green,
    borderWidth: 2,
    backgroundColor: colors.brand.greenSoft,
  },
  vehicleHeader: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginBottom: spacing.xs },
  vehicleIcon: { width: 44, height: 44, borderRadius: radii.md, backgroundColor: colors.brand.greenSoft, alignItems: "center", justifyContent: "center" },
  vehicleIconText: { fontSize: 20 },
  vehicleCopy: { flex: 1, gap: 2 },
  vehicleName: { color: colors.text.ink, fontSize: 15, fontWeight: "900" },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight },
  vehiclePrice: { color: colors.text.ink, fontSize: 18, fontWeight: "900" },
  vehicleSub: { color: colors.text.muted, fontSize: 11, lineHeight: 15, marginTop: spacing.xs },
  selectedTag: { color: colors.brand.green, fontSize: 11, fontWeight: "900", marginTop: spacing.xs, alignSelf: "flex-start" },
});

export default VehicleCard;