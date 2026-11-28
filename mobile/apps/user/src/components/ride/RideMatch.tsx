import React from "react";
import { ActivityIndicator, Pressable, Text, View, StyleSheet } from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import {
  PamojaActionButton as ActionButton,
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
} from "../PamojaScreen";

type RideMatchProps = {
  submitting: boolean;
  requestError: string | null;
  verificationRequired: boolean;
  onRetry: () => void;
  onChangeRide: () => void;
};

export function RideMatch({
  submitting,
  requestError,
  verificationRequired,
  onRetry,
  onChangeRide,
}: RideMatchProps) {
  // The request either ends in a reference (the screen is replaced by the
  // tracking page) or in a decision the rider must see. A rejection is not a
  // "still matching" state: the spinner used to keep turning behind the error
  // text, so a refused request looked like one still in progress.
  const failed = !!requestError && !submitting;

  return (
    <Panel>
      <View style={styles.matchingPanel}>
        {submitting ? (
          <ActivityIndicator color={colors.brand.green} size="large" />
        ) : (
          <View style={styles.stoppedBadge}>
            <Text style={styles.stoppedBadgeText}>!</Text>
          </View>
        )}

        <SectionTitle>
          {submitting ? "Sending your ride request…" : "Ride request not completed"}
        </SectionTitle>

        {failed && <Text style={styles.errorText}>{requestError}</Text>}

        {failed && verificationRequired && (
          <View style={styles.guidance}>
            <Text style={styles.guidanceText}>
              Nothing was charged and no fare was reserved. No driver search has started.
            </Text>
            <Text style={styles.guidanceText}>
              This server will keep refusing the request until this exact account is verified.
              Complete identity verification on the Pamoja website you are signed in to, then
              return here and try again.
            </Text>
          </View>
        )}

        {failed && (
          <View style={styles.actions}>
            {/* A blind "Try again" against a decided refusal is what made the
                rider think a match was still running. Once verification is the
                blocker, the button says what it actually re-checks. */}
            <ActionButton
              label={verificationRequired ? "I have verified — try again" : "Try again"}
              onPress={onRetry}
            />
            <Pressable
              accessibilityRole="button"
              onPress={onChangeRide}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            >
              <Text style={styles.secondaryAction}>Change ride or payment</Text>
            </Pressable>
          </View>
        )}
      </View>
    </Panel>
  );
}

const styles = StyleSheet.create({
  matchingPanel: { alignItems: "center", paddingVertical: spacing.xxl, gap: spacing.md },
  stoppedBadge: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 2,
    borderColor: colors.status.error,
    alignItems: "center",
    justifyContent: "center",
  },
  stoppedBadgeText: {
    color: colors.status.error,
    fontSize: 22,
    fontWeight: "800",
    lineHeight: 26,
  },
  errorText: {
    color: colors.status.error,
    fontSize: typography.caption.fontSize,
    lineHeight: typography.caption.lineHeight,
    textAlign: "center",
    marginTop: spacing.sm,
  },
  guidance: {
    alignSelf: "stretch",
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
  },
  guidanceText: {
    color: colors.text.ink,
    fontSize: typography.caption.fontSize,
    lineHeight: typography.caption.lineHeight,
  },
  actions: { alignSelf: "stretch", gap: spacing.md, marginTop: spacing.sm },
  secondaryAction: {
    color: colors.brand.green,
    fontSize: typography.caption.fontSize,
    fontWeight: "700",
    textAlign: "center",
    paddingVertical: spacing.sm,
  },
});

export default RideMatch;
