import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import {
  PamojaActionButton as ActionButton,
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
} from "../PamojaScreen";
import { VehicleCard } from "./VehicleCard";
import type { Quote } from "./types";

type RideChooseProps = {
  quotes: Quote[];
  selectedQuote: Quote | null;
  distanceKm: number | null;
  loadingQuotes: boolean;
  quoteError: string | null;
  onQuoteSelect: (quote: Quote) => void;
  onContinue: () => void;
  onBack: () => void;
};

export function RideChoose({
  quotes,
  selectedQuote,
  distanceKm,
  loadingQuotes,
  quoteError,
  onQuoteSelect,
  onContinue,
  onBack,
}: RideChooseProps) {
  return (
    <Panel>
      <SectionTitle>Choose a vehicle class</SectionTitle>
      <Text style={styles.helperText}>
        {distanceKm != null ? "About " + Number(distanceKm).toFixed(1) + " km · " : ""}
        Fare estimates only. Driver matching has not started.
      </Text>
      {loadingQuotes && <ActivityIndicator color={colors.brand.green} size="large" style={styles.centered} />}
      {quoteError && <Text style={styles.errorText}>{quoteError}</Text>}
      {quotes.map(quote => (
        <VehicleCard
          key={quote.vehicle_class}
          quote={quote}
          selected={selectedQuote?.vehicle_class === quote.vehicle_class}
          onPress={() => onQuoteSelect(quote)}
        />
      ))}
      {!loadingQuotes && !quoteError && quotes.length === 0 && (
        <Text style={styles.helperText}>No fare options are available yet for this route.</Text>
      )}
      <Text style={styles.helperText}>These are signed server quotes, not driver availability or a reservation. You will review and accept the fare before any driver is contacted.</Text>
      <ActionButton
        label="Review Booking"
        disabled={!selectedQuote || loadingQuotes}
        onPress={onContinue}
      />
      <Pressable onPress={onBack} style={styles.secondaryButton} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
        <Text style={styles.secondaryButtonText}>Edit trip details</Text>
      </Pressable>
    </Panel>
  );
}

const styles = StyleSheet.create({
  centered: { alignSelf: "center", marginVertical: spacing.lg },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, marginTop: spacing.xs },
  errorText: { color: colors.status.error, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, marginTop: spacing.sm },
  secondaryButton: { alignSelf: "center", marginTop: spacing.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg },
  secondaryButtonText: { color: colors.brand.green, fontSize: 13, fontWeight: "800" },
});

export default RideChoose;