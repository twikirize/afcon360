import React, { useEffect } from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withDelay,
} from "react-native-reanimated";
import { colors, typography, spacing, radii, shadows } from "../theme/tokens";

type ServiceKey = "events" | "stays" | "rides" | "tourism";

type Service = {
  key: ServiceKey;
  label: string;
  hint: string;
  icon: string;
  isWeb?: boolean;
  bgColor: string;
  borderColor: string;
  iconBg: string;
  accessibilityLabel: string;
};

const SERVICES: Service[] = [
  {
    key: "events",
    label: "Events & Tickets",
    hint: "Discover · Register",
    icon: "\u{1F3DF}\u{FE0F}",
    bgColor: "#FFF8E6",
    borderColor: "#F0E3BD",
    iconBg: "#FCE9B5",
    accessibilityLabel: "Events and tickets",
  },
  {
    key: "stays",
    label: "Stays",
    hint: "Find a place",
    icon: "\u{1F3E8}",
    bgColor: "#EAF3EB",
    borderColor: "#D6E5D8",
    iconBg: "#D7E8D9",
    accessibilityLabel: "Stays and accommodation",
  },
  {
    key: "rides",
    label: "Mobility",
    hint: "Move with ease",
    icon: "\u{1F698}",
    bgColor: "#EAF0FA",
    borderColor: "#D9E3F3",
    iconBg: "#D8E4F6",
    accessibilityLabel: "Mobility and rides",
  },
  {
    key: "tourism",
    label: "Adventure",
    hint: "Tourism \u00B7 Safaris",
    icon: "\u{1F30D}",
    isWeb: true,
    bgColor: "#F0F3E5",
    borderColor: "#E0E7C9",
    iconBg: "#E1E9C9",
    accessibilityLabel: "Adventure and tourism on website",
  },
];

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    rowGap: spacing.md,
  },
  tileWrap: {
    width: "48.6%",
  },
  tile: {
    minHeight: 146,
    borderRadius: radii.xl,
    padding: spacing.lg,
    borderWidth: 1,
    gap: spacing.xs,
    overflow: "hidden",
    ...shadows.card,
  },
  tileAccent: {
    position: "absolute",
    width: 116,
    height: 116,
    borderRadius: 58,
    right: -56,
    top: -62,
    backgroundColor: "rgba(255,255,255,0.38)",
  },
  tileTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  iconWrapper: {
    width: 48,
    height: 48,
    borderRadius: radii.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  iconText: {
    fontSize: 25,
  },
  arrowBadge: {
    width: 27,
    height: 27,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.60)",
    borderWidth: 1,
    borderColor: "rgba(23,61,40,0.07)",
  },
  arrowText: {
    color: colors.brand.dark,
    fontSize: 16,
    lineHeight: 19,
    fontWeight: "900",
  },
  title: {
    color: colors.brand.dark,
    fontSize: 15,
    lineHeight: 19,
    fontWeight: "900",
    letterSpacing: -0.2,
  },
  hint: {
    color: colors.text.muted,
    fontSize: typography.caption.fontSize,
    lineHeight: 16,
    fontWeight: "700",
  },
  webHint: {
    alignSelf: "flex-start",
    marginTop: 2,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: radii.sm,
    backgroundColor: "rgba(23,61,40,0.08)",
  },
  webHintText: {
    color: colors.brand.emerald,
    fontSize: typography.overline.fontSize,
    fontWeight: "900",
    letterSpacing: 0.5,
  },
});

type ServiceTileProps = {
  service: Service;
  index: number;
  onPress: (key: ServiceKey) => void;
};

const ServiceTile = ({ service, index, onPress }: ServiceTileProps) => {
  const entrance = useSharedValue(0);
  const pressScale = useSharedValue(1);

  useEffect(() => {
    entrance.value = withDelay(index * 80, withSpring(1, { damping: 20, stiffness: 150 }));
  }, [index]);

  const entranceStyle = useAnimatedStyle(() => ({
    opacity: entrance.value,
    transform: [
      { translateY: (1 - entrance.value) * 20 },
      { scale: entrance.value },
    ],
  }));

  const pressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pressScale.value }],
  }));

  return (
    <Animated.View style={[styles.tileWrap, entranceStyle]}>
      <Animated.View style={pressStyle}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={service.accessibilityLabel}
          onPress={() => onPress(service.key)}
          onPressIn={() => { pressScale.value = withSpring(0.96, { damping: 20 }); }}
          onPressOut={() => { pressScale.value = withSpring(1, { damping: 20 }); }}
          style={({ pressed }) => [
            styles.tile,
            { backgroundColor: service.bgColor, borderColor: service.borderColor },
            pressed && { opacity: 0.85 },
          ]}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <View pointerEvents="none" style={styles.tileAccent} />
          <View style={styles.tileTopRow}>
            <View style={[styles.iconWrapper, { backgroundColor: service.iconBg }]}>
              <Text style={styles.iconText}>{service.icon}</Text>
            </View>
            <View style={styles.arrowBadge}>
              <Text style={styles.arrowText}>{"\u2197"}</Text>
            </View>
          </View>
          <Text style={styles.title}>{service.label}</Text>
          {service.isWeb ? (
            <View style={styles.webHint}>
              <Text style={styles.webHintText}>{service.hint + " \u2197"}</Text>
            </View>
          ) : (
            <Text style={styles.hint}>{service.hint}</Text>
          )}
        </Pressable>
      </Animated.View>
    </Animated.View>
  );
};

export const ServiceGrid = ({ onServicePress }: { onServicePress: (key: string) => void }) => (
  <View style={styles.container}>
    {SERVICES.map((service, index) => (
      <ServiceTile
        key={service.key}
        service={service}
        index={index}
        onPress={onServicePress}
      />
    ))}
  </View>
);

export default ServiceGrid;