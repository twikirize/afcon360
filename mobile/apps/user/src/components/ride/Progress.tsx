import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import type { Stage } from "./types";

const styles = StyleSheet.create({
  progress: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginBottom: spacing.lg,
  },
  progressStep: {
    flex: 1,
    alignItems: "center",
    gap: spacing.xs,
  },
  progressNumber: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.surface.canvas,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  progressDone: {
    backgroundColor: colors.brand.green,
    borderColor: colors.brand.green,
  },
  progressActive: {
    backgroundColor: colors.brand.greenSoft,
    borderColor: colors.brand.green,
  },
  progressNumberText: {
    color: colors.text.muted,
    fontSize: 14,
    fontWeight: "900",
  },
  progressNumberTextActive: {
    color: colors.surface.white,
  },
  progressLabel: {
    color: colors.text.muted,
    fontSize: typography.caption.fontSize,
    fontWeight: "700",
    textAlign: "center",
  },
  progressLabelActive: {
    color: colors.brand.green,
  },
  progressLine: {
    flex: 1,
    height: 2,
    backgroundColor: colors.border,
    marginHorizontal: spacing.xs,
  },
  progressLineDone: {
    backgroundColor: colors.brand.green,
  },
});

const STAGES: { key: Stage; label: string }[] = [
  { key: "where", label: "Where" },
  { key: "choose", label: "Choose" },
  { key: "confirm", label: "Confirm" },
  { key: "match", label: "Match" }
];

export function Progress({ stage }: { stage: Stage }) {
  const current = STAGES.findIndex(item => item.key === stage);

  return (
    <View style={styles.progress}>
      {STAGES.map((item, index) => (
        <React.Fragment key={item.key}>
          <View style={styles.progressStep}>
            <View style={[
              styles.progressNumber,
              index < current && styles.progressDone,
              index === current && styles.progressActive,
            ]}>
              <Text style={[
                styles.progressNumberText,
                index <= current && styles.progressNumberTextActive,
              ]}>{index < current ? "✓" : String(index + 1)}</Text>
            </View>
            <Text style={[
              styles.progressLabel,
              index <= current && styles.progressLabelActive,
            ]}>
              {item.label}
            </Text>
          </View>
          {index < STAGES.length - 1 ? (
            <View style={[styles.progressLine, index < current && styles.progressLineDone]} />
          ) : null}
        </React.Fragment>
      ))}
    </View>
  );
}

export default Progress;