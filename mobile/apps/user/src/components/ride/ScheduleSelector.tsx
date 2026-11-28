import React from "react";
import { Pressable, Text, View, StyleSheet, TextInput } from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
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
      <Text style={styles.label}>When do you need a ride?</Text>
      <View style={styles.scheduleRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ selected: schedule === "now" }}
          onPress={() => { onScheduleChange("now"); resetCommitment(); }}
          style={[styles.scheduleChoice, schedule === "now" && styles.scheduleSelected]}
          hitSlop={{ top: 7, bottom: 7, left: 7, right: 7 }}
        >
          <Text style={[styles.scheduleText, schedule === "now" && styles.scheduleTextSelected]}>◷  Now</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ selected: schedule === "later" }}
          onPress={() => { onScheduleChange("later"); resetCommitment(); }}
          style={[styles.scheduleChoice, schedule === "later" && styles.scheduleSelected]}
          hitSlop={{ top: 7, bottom: 7, left: 7, right: 7 }}
        >
          <Text style={[styles.scheduleText, schedule === "later" && styles.scheduleTextSelected]}>▦  Later</Text>
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
          <Text style={styles.helperText}>
            Enter the pickup location's local time. AFCON360 resolves its timezone and enforces the 15-minute minimum lead time on the server.
          </Text>
        </>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  label: { color: "#101C16", fontWeight: "800", fontSize: 16, lineHeight: 21, marginTop: spacing.sm, marginBottom: 2 },
  scheduleRow: { flexDirection: "row", gap: spacing.sm },
  scheduleChoice: {
    flex: 1,
    minHeight: 43,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: "#E8EBE8",
    backgroundColor: "#F0F1F0",
  },
  scheduleSelected: { borderColor: "#0E9F5B", backgroundColor: "#0E9F5B" },
  scheduleText: { color: colors.text.ink, fontSize: 13, fontWeight: "800" },
  scheduleTextSelected: { color: "#FFFFFF" },
  input: {
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    color: colors.text.ink,
    fontSize: 15,
    marginTop: spacing.sm,
  },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, marginTop: spacing.xs },
});

export default ScheduleSelector;
