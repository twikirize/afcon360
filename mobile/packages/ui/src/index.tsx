import React, { ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View, ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

export const palette = {
  canvas: "#F4F7F5", surface: "#FFFFFF", ink: "#14231D", muted: "#68776F",
  green: "#087A4B", greenDark: "#075C39", greenSoft: "#E5F3EB",
  border: "#DFE8E1", warningSoft: "#FFF4D9"
};

export function AppScreen({ children }: { children: ReactNode }) {
  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description?: string }) {
  return (
    <View style={styles.header}>
      <Text style={styles.eyebrow}>{eyebrow.toUpperCase()}</Text>
      <Text accessibilityRole="header" style={styles.title}>{title}</Text>
      {description ? <Text style={styles.description}>{description}</Text> : null}
    </View>
  );
}

export function Panel({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.panel, style]}>{children}</View>;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text accessibilityRole="header" style={styles.sectionTitle}>{children}</Text>;
}

export function StatusPill({ children, tone = "green" }: { children: ReactNode; tone?: "green" | "gold" | "neutral" }) {
  const backgroundColor = tone === "gold" ? palette.warningSoft : tone === "neutral" ? "#EDF1EF" : palette.greenSoft;
  return <View style={[styles.pill, { backgroundColor }]}><Text style={styles.pillText}>{children}</Text></View>;
}

export function ActionButton({ label, onPress, disabled = false }: { label: string; onPress?: () => void; disabled?: boolean }) {
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled || !onPress}
      onPress={onPress} style={({ pressed }) => [styles.button, (disabled || !onPress) && styles.disabled, pressed && styles.pressed]}>
      <Text style={styles.buttonText}>{label}</Text>
    </Pressable>
  );
}

export function ServiceTile({ title, description, symbol }: { title: string; description: string; symbol: string }) {
  return (
    <View style={styles.tile}>
      <View style={styles.symbol}><Text style={styles.symbolText}>{symbol}</Text></View>
      <View style={styles.copy}><Text style={styles.tileTitle}>{title}</Text><Text style={styles.tileDescription}>{description}</Text></View>
    </View>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyMark}><Text style={styles.emptyMarkText}>360</Text></View>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyDescription}>{description}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.canvas },
  content: { padding: 20, paddingBottom: 36, gap: 18 },
  header: { gap: 7, paddingTop: 6 },
  eyebrow: { color: palette.green, fontSize: 11, fontWeight: "800", letterSpacing: 1.6 },
  title: { color: palette.ink, fontSize: 29, fontWeight: "800", letterSpacing: -0.8 },
  description: { color: palette.muted, fontSize: 14, lineHeight: 21 },
  panel: { backgroundColor: palette.surface, borderColor: palette.border, borderWidth: 1, borderRadius: 19, padding: 17, gap: 10 },
  sectionTitle: { color: palette.ink, fontSize: 17, fontWeight: "800" },
  pill: { alignSelf: "flex-start", paddingHorizontal: 11, paddingVertical: 7, borderRadius: 99 },
  pillText: { color: palette.greenDark, fontSize: 11, fontWeight: "800" },
  button: { minHeight: 50, backgroundColor: palette.green, borderRadius: 14, alignItems: "center", justifyContent: "center", paddingHorizontal: 18 },
  disabled: { backgroundColor: "#9AA9A0" },
  pressed: { opacity: 0.82 },
  buttonText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  tile: { flexDirection: "row", alignItems: "center", gap: 13, paddingVertical: 7 },
  symbol: { height: 44, width: 44, borderRadius: 14, backgroundColor: palette.greenSoft, alignItems: "center", justifyContent: "center" },
  symbolText: { fontSize: 20 },
  copy: { flex: 1, gap: 3 },
  tileTitle: { color: palette.ink, fontSize: 14, fontWeight: "800" },
  tileDescription: { color: palette.muted, fontSize: 12, lineHeight: 18 },
  empty: { alignItems: "center", padding: 25, gap: 9 },
  emptyMark: { width: 54, height: 54, borderRadius: 18, backgroundColor: palette.greenSoft, alignItems: "center", justifyContent: "center" },
  emptyMarkText: { color: palette.greenDark, fontWeight: "900", fontSize: 16 },
  emptyTitle: { color: palette.ink, fontSize: 16, fontWeight: "800", textAlign: "center" },
  emptyDescription: { color: palette.muted, fontSize: 13, lineHeight: 19, textAlign: "center" }
});
