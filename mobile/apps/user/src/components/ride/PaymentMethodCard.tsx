import React from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import { colors, spacing, radii, typography, shadows } from "../theme/tokens";
import type { PaymentMethod } from "./types";

type PaymentMethodCardProps = {
  method: PaymentMethod;
  selected: boolean;
  onPress: () => void;
  ready: boolean;
};

export function PaymentMethodCard({ method, selected, onPress, ready }: PaymentMethodCardProps) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected, disabled: !ready }}
      disabled={!ready}
      onPress={onPress}
      style={[
        styles.paymentChoice,
        selected && styles.paymentSelected,
        !ready && styles.disabled,
      ]}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <View style={[styles.radio, selected && styles.radioSelected]} />
      <View style={styles.paymentCopy}>
        <Text style={styles.paymentName}>{method.label}</Text>
        <Text style={styles.helperText}>
          {ready ? "Ready for this fare" : method.status_message ?? method.status.replace(/_/g, " ")}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  paymentChoice: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.white,
    ...shadows.card,
  },
  paymentSelected: {
    borderColor: colors.brand.green,
    borderWidth: 2,
    backgroundColor: colors.brand.greenSoft,
  },
  disabled: {
    opacity: 0.5,
    backgroundColor: colors.surface.canvas,
  },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface.white,
  },
  radioSelected: {
    borderColor: colors.brand.green,
    backgroundColor: colors.brand.green,
  },
  paymentCopy: { flex: 1, gap: 2 },
  paymentName: { color: colors.text.ink, fontSize: 15, fontWeight: "800" },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight },
});

export default PaymentMethodCard;