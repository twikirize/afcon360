import React from "react";
import { Pressable, Text, View, StyleSheet, TextInput } from "react-native";
import { colors, spacing, radii, typography } from "../theme/tokens";
import { validLocalSchedule } from "./utils";
import type { RideSchedule } from "./types";

type ScheduleSelectorProps = {
  schedule: RideSchedule;
  scheduledAt: string;
  onScheduleChange: (schedule: RideSchedule) => void;
  onScheduledAtChange: (value: string) => void;
  resetCommitment: () => void;
};

export function ScheduleSelector({ schedule, scheduledAt, onScheduleChange, onScheduledAtChange, resetCommitment }: ScheduleSelectorProps) {
  return (
    <>
      <Text style={styles.label}>When do you need the ride?</Text>
      <View style={styles.scheduleRow}>
        <Pressable
          onPress={() => { onScheduleChange("now"); resetCommitment(); }}
          style={[styles.scheduleChoice, schedule === "now" && styles.scheduleSelected]}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Text style={styles.scheduleText}>⚡  Now</Text>
        </Pressable>
        <Pressable
          onPress={() => { onScheduleChange("later"); resetCommitment(); }}
          style={[styles.scheduleChoice, schedule === "later" && styles.scheduleSelected]}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Text style={styles.scheduleText}>▦  Later</Text>
        </Pressable>
      </View>
      {schedule === "later" ? (
        <>
          <TextInput
            value={scheduledAt}
            onChangeText={onScheduledAtChange}
            style={styles.input}
            placeholder="YYYY-MM-DDTHH:mm"
            placeholderTextColor={colors.text.muted}
            accessibilityLabel="Scheduled local pickup date and time"
            autoCapitalize="none"
          />
          <Text style={styles.helperText}>Enter the pickup location's local time. AFCON360 resolves its timezone and enforces the 15-minute minimum lead time on the server.</Text>
        </>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  label: { color: colors.text.ink, fontWeight: "700", fontSize: 13, marginTop: spacing.lg },
  scheduleRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  scheduleChoice: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: spacing.md,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface.white,
  },
  scheduleSelected: {
    borderColor: colors.brand.green,
    backgroundColor: colors.brand.greenSoft,
  },
  scheduleText: { color: colors.text.ink, fontSize: 13, fontWeight: "800" },
  input: {
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    color: colors.text.ink,
    fontSize: 15,
    marginTop: spacing.md,
  },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, marginTop: spacing.xs },
});

export default ScheduleSelector;