import React from "react";
import { ActivityIndicator, Text, View, StyleSheet } from "react-native";
import { colors, spacing, radii, typography } from "../theme/tokens";
import {
  PamojaActionButton as ActionButton,
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
  PamojaStatusPill as StatusPill,
} from "../PamojaScreen";
import { PaymentMethodCard } from "./PaymentMethodCard";
import { formatMoney } from "./utils";
import type { Quote, PaymentMethod } from "./types";

type RideConfirmProps = {
  pickup: { label: string } | null;
  dropoff: { label: string } | null;
  selectedQuote: Quote | null;
  schedule: "now" | "later";
  scheduledAt: string;
  vip: boolean;
  serviceType: "on_demand" | "airport_departure";
  paymentMethods: PaymentMethod[];
  paymentMethod: string;
  loadingPayments: boolean;
  paymentError: string | null;
  onPaymentMethodSelect: (code: string) => void;
  onConfirm: () => void;
  onBackToChoose: () => void;
  onBackToWhere: () => void;
};

export function RideConfirm({
  pickup,
  dropoff,
  selectedQuote,
  schedule,
  scheduledAt,
  vip,
  serviceType,
  paymentMethods,
  paymentMethod,
  loadingPayments,
  paymentError,
  onPaymentMethodSelect,
  onConfirm,
  onBackToChoose,
  onBackToWhere,
}: RideConfirmProps) {
  const fmtSchedule = schedule === "later" ? scheduledAt.replace("T", " ") : "Leaving now";
  const displayCurrency = selectedQuote?.display_currency ?? selectedQuote?.currency ?? "USD";
  const displayAmount = selectedQuote?.display_amount ?? selectedQuote?.fare_total ?? 0;
  const displayApprox = selectedQuote?.display_is_approximate === true;
  const breakdown = selectedQuote?.fare_breakdown;

  const displayBreakdown = (amount: unknown) => {
    const numeric = Number(amount ?? 0);
    const rate = Number(selectedQuote?.display_rate ?? 1);
    return formatMoney(numeric * (Number.isFinite(rate) && rate > 0 ? rate : 1), displayCurrency);
  };

  return (
    <Panel>
      <SectionTitle>Confirm your ride</SectionTitle>
      <StatusPill tone={schedule === "later" ? "gold" : "green"}>
        {schedule === "later" ? "Pickup scheduled" : "Leaving now"}
      </StatusPill>
      <Text style={styles.helperText}>{fmtSchedule}</Text>
      <View style={styles.summary}>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Pickup</Text>
          <Text style={styles.summaryValue}>{pickup?.label ?? "—"}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Destination</Text>
          <Text style={styles.summaryValue}>{dropoff?.label ?? "—"}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Service</Text>
          <Text style={styles.summaryValue}>{vip ? "VIP Service" : serviceType === "airport_departure" ? "Airport Transfer" : "Quick Ride"}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Ride</Text>
          <Text style={styles.summaryValue}>{selectedQuote?.display_name ?? "—"}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Fare display</Text>
          <Text style={styles.summaryValue}>{formatMoney(Number(displayAmount), displayCurrency)}{displayApprox ? " (approx.)" : ""}</Text>
        </View>
        {displayApprox && (
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Authoritative fare</Text>
            <Text style={styles.summaryValue}>{formatMoney(selectedQuote?.fare_total ?? 0, selectedQuote?.currency ?? "USD")}</Text>
          </View>
        )}
      </View>

      {breakdown ? (
        <View style={styles.fareBreakdown}>
          <Text style={styles.label}>Fare breakdown</Text>
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Base fare</Text>
            <Text style={styles.summaryValue}>{displayBreakdown(breakdown.base_fare)}</Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Distance {distanceKm != null ? "(" + distanceKm.toFixed(1) + " km)" : ""}</Text>
            <Text style={styles.summaryValue}>{displayBreakdown(breakdown.distance_charge)}</Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Class multiplier</Text>
            <Text style={styles.summaryValue}>× {Number(breakdown.class_multiplier ?? 1).toFixed(2)}</Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Surge multiplier</Text>
            <Text style={styles.summaryValue}>× {Number(breakdown.surge_multiplier ?? 1).toFixed(2)}</Text>
          </View>
          <View style={[styles.summaryRow, styles.totalRow]}>
            <Text style={styles.totalLabel}>Wallet invoice fare</Text>
            <Text style={styles.totalValue}>{formatMoney(selectedQuote?.fare_total ?? 0, selectedQuote?.currency ?? "USD")}</Text>
          </View>
        </View>
      ) : (
        <View style={styles.summary}>
          <Text style={styles.totalLabel}>Wallet invoice fare</Text>
          <Text style={styles.totalValue}>{formatMoney(selectedQuote?.fare_total ?? 0, selectedQuote?.currency ?? "USD")}</Text>
        </View>
      )}

      <Text style={styles.label}>How would you like to pay?</Text>
      {loadingPayments && <ActivityIndicator color={colors.brand.green} style={styles.centered} />}
      {paymentError && <Text style={styles.errorText}>{paymentError}</Text>}
      {paymentMethods.map(method => {
        const ready = method.status === "ready";
        const selected = paymentMethod === method.code;
        return (
          <PaymentMethodCard
            key={method.code}
            method={method}
            selected={selected}
            ready={ready}
            onPress={() => onPaymentMethodSelect(method.code)}
          />
        );
      })}
      {!loadingPayments && paymentMethods.length === 0 && !paymentError && (
        <Text style={styles.helperText}>No payment methods were returned for this fare.</Text>
      )}
      <Text style={styles.helperText}>No driver search has started yet. Confirming accepts the signed fare. You are not charged at this step; payment follows the selected Wallet method and Transport's payment rules.</Text>
      <ActionButton
        label="Confirm Fare & Request Ride"
        disabled={!paymentMethod || loadingPayments}
        onPress={onConfirm}
      />
      <Pressable onPress={onBackToChoose} style={styles.secondaryButton} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
        <Text style={styles.secondaryButtonText}>Edit vehicle choice</Text>
      </Pressable>
      <Pressable onPress={onBackToWhere} style={styles.secondaryButton} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
        <Text style={styles.secondaryButtonText}>Edit trip details</Text>
      </Pressable>
    </Panel>
  );
}

const styles = StyleSheet.create({
  centered: { alignSelf: "center", marginVertical: spacing.md },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, marginTop: spacing.xs },
  errorText: { color: colors.status.error, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, marginTop: spacing.sm },
  label: { color: colors.text.ink, fontWeight: "700", fontSize: 13, marginTop: spacing.lg },
  summary: { gap: spacing.sm, marginTop: spacing.md },
  summaryRow: { flexDirection: "row", justifyContent: "space-between", gap: spacing.md },
  summaryLabel: { color: colors.text.muted, fontSize: 13, fontWeight: "700" },
  summaryValue: { color: colors.text.ink, fontSize: 13, fontWeight: "800", textAlign: "right", flex: 1 },
  fareBreakdown: { marginTop: spacing.lg, padding: spacing.md, backgroundColor: colors.surface.canvas, borderRadius: radii.lg, gap: spacing.sm },
  totalRow: { marginTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm },
  totalLabel: { color: colors.text.ink, fontSize: 14, fontWeight: "900" },
  totalValue: { color: colors.brand.green, fontSize: 16, fontWeight: "900", textAlign: "right" },
  secondaryButton: { alignSelf: "center", marginTop: spacing.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg },
  secondaryButtonText: { color: colors.brand.green, fontSize: 13, fontWeight: "800" },
});

export default RideConfirm;