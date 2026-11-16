import React, { ReactNode } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

type Tone = "green" | "gold" | "neutral";

export function PamojaScreen({ children }: { children: ReactNode }) {
  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function PamojaPageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description?: string;
}) {
  return (
    <View style={styles.header}>
      <View style={styles.headerGlow} />
      <Text style={styles.eyebrow}>{eyebrow.toUpperCase()}</Text>
      <Text accessibilityRole="header" style={styles.title}>{title}</Text>
      {description ? <Text style={styles.description}>{description}</Text> : null}
    </View>
  );
}

export function PamojaPanel({
  children,
  style,
}: {
  children: ReactNode;
  style?: ViewStyle;
}) {
  return <View style={[styles.panel, style]}>{children}</View>;
}

export function PamojaSectionTitle({ children }: { children: ReactNode }) {
  return <Text accessibilityRole="header" style={styles.sectionTitle}>{children}</Text>;
}

export function PamojaStatusPill({
  children,
  tone = "green",
}: {
  children: ReactNode;
  tone?: Tone;
}) {
  const toneStyle = tone === "gold"
    ? styles.pillGold
    : tone === "neutral"
      ? styles.pillNeutral
      : styles.pillGreen;
  const textStyle = tone === "gold"
    ? styles.pillTextGold
    : tone === "neutral"
      ? styles.pillTextNeutral
      : styles.pillTextGreen;
  return (
    <View style={[styles.pill, toneStyle]}>
      <Text style={[styles.pillText, textStyle]}>{children}</Text>
    </View>
  );
}

export function PamojaActionButton({
  label,
  onPress,
  disabled = false,
}: {
  label: string;
  onPress?: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled || !onPress}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        (disabled || !onPress) && styles.buttonDisabled,
        pressed && styles.buttonPressed,
      ]}
    >
      <Text style={styles.buttonText}>{label}</Text>
    </Pressable>
  );
}

export function PamojaEmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyMark}>
        <Text style={styles.emptyMarkText}>✦</Text>
      </View>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyDescription}>{description}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#F5F6F2" },
  content: { paddingHorizontal: 18, paddingTop: 12, paddingBottom: 36, gap: 16 },
  header: {
    position: "relative",
    overflow: "hidden",
    backgroundColor: "#093E24",
    borderRadius: 20,
    paddingHorizontal: 19,
    paddingVertical: 19,
    gap: 7,
  },
  headerGlow: {
    position: "absolute",
    top: -64,
    right: -42,
    width: 170,
    height: 170,
    borderRadius: 85,
    backgroundColor: "rgba(214,235,221,0.13)",
  },
  eyebrow: { color: "#F5B700", fontSize: 9, fontWeight: "900", letterSpacing: 1.35 },
  title: { color: "#FFFFFF", fontFamily: "serif", fontSize: 27, lineHeight: 33, fontWeight: "700" },
  description: { color: "rgba(255,255,255,0.82)", fontSize: 12, lineHeight: 18, maxWidth: 340 },
  panel: {
    backgroundColor: "#FFFFFF",
    borderColor: "#E6EAE4",
    borderWidth: 1,
    borderRadius: 18,
    padding: 16,
    gap: 12,
  },
  sectionTitle: { color: "#122419", fontFamily: "serif", fontSize: 18, fontWeight: "700" },
  pill: { alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999 },
  pillGreen: { backgroundColor: "#E8F4EC" },
  pillGold: { backgroundColor: "#FFF4D5" },
  pillNeutral: { backgroundColor: "#F0F3F0" },
  pillText: { fontSize: 10, fontWeight: "900", letterSpacing: 0.2 },
  pillTextGreen: { color: "#0E5B36" },
  pillTextGold: { color: "#80611A" },
  pillTextNeutral: { color: "#59675E" },
  button: {
    minHeight: 48,
    backgroundColor: "#0E5B36",
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 18,
  },
  buttonDisabled: { backgroundColor: "#9AA9A0", opacity: 0.65 },
  buttonPressed: { opacity: 0.82 },
  buttonText: { color: "#FFFFFF", fontSize: 13, fontWeight: "900" },
  empty: { alignItems: "center", paddingHorizontal: 22, paddingVertical: 24, gap: 9 },
  emptyMark: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#E8F4EC", alignItems: "center", justifyContent: "center" },
  emptyMarkText: { color: "#0E5B36", fontSize: 22, fontWeight: "900" },
  emptyTitle: { color: "#122419", fontSize: 15, fontWeight: "900", textAlign: "center" },
  emptyDescription: { color: "#6C766E", fontSize: 12, lineHeight: 18, textAlign: "center" },
});
