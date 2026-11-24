import React from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withDelay,
} from "react-native-reanimated";
import { colors, typography, spacing, radii, shadows } from "../theme/tokens";

export type ServiceKey = "rides" | "stays" | "events" | "adventure" | "wallet" | "tourism";

export type ServiceEntryProps = {
  serviceKey: ServiceKey;
  onPress: () => void;
  index?: number;
  variant?: "card" | "banner";
};

const SERVICE_CONFIG: Record<ServiceKey, {
  label: string;
  hint: string;
  icon: string;
  bgColor: string;
  borderColor: string;
  iconBg: string;
  accessibilityLabel: string;
}> = {
  rides: {
    label: "Transport",
    hint: "Rides & transfers",
    icon: "🚌",
    bgColor: "#EAF0FA",
    borderColor: "#D9E3F3",
    iconBg: "#D8E4F6",
    accessibilityLabel: "Book a ride",
  },
  stays: {
    label: "Stays",
    hint: "Find a place",
    icon: "🛏️",
    bgColor: "#EAF3EB",
    borderColor: "#D6E5D8",
    iconBg: "#D7E8D9",
    accessibilityLabel: "Book accommodation",
  },
  events: {
    label: "Events & Tickets",
    hint: "Discover & register",
    icon: "🎟️",
    bgColor: "#FFF8E6",
    borderColor: "#F0E3BD",
    iconBg: "#FCE9B5",
    accessibilityLabel: "Browse events",
  },
  adventure: {
    label: "Adventure",
    hint: "Tours · Safaris · Experiences",
    icon: "🧭",
    bgColor: "#F0F3E5",
    borderColor: "#E0E7C9",
    iconBg: "#E1E9C9",
    accessibilityLabel: "Explore adventures",
  },
  wallet: {
    label: "Wallet",
    hint: "Pay & send",
    icon: "💰",
    bgColor: "#E8F4EC",
    borderColor: "#D6EBDD",
    iconBg: "#CDEBD0",
    accessibilityLabel: "Open wallet",
  },
  tourism: {
    label: "Tourism",
    hint: "Explore on web",
    icon: "🌍",
    bgColor: "#F5F0E8",
    borderColor: "#E8DCC8",
    iconBg: "#E8DCC8",
    accessibilityLabel: "Open tourism on website",
  },
};

const styles = StyleSheet.create({
  card: {
    minHeight: 146,
    borderRadius: radii.xl,
    padding: spacing.lg,
    borderWidth: 1,
    gap: spacing.xs,
    overflow: "hidden",
    ...shadows.card,
  },
  cardAccent: {
    position: "absolute",
    width: 116,
    height: 116,
    borderRadius: 58,
    right: -56,
    top: -62,
    backgroundColor: "rgba(255,255,255,0.38)",
  },
  cardTopRow: {
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
  banner: {
    backgroundColor: "#0E5B36",
    borderRadius: 18,
    padding: 15,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  bannerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    flex: 1,
  },
  walletIconBox: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: "rgba(255,255,255,0.16)",
    alignItems: "center",
    justifyContent: "center",
  },
  walletShape: {
    width: 26,
    height: 20,
    borderWidth: 2,
    borderColor: "#FFFFFF",
    borderRadius: 4,
    position: "relative",
  },
  walletFlap: {
    position: "absolute",
    right: -2,
    top: 4,
    width: 12,
    height: 9,
    borderWidth: 2,
    borderColor: "#FFFFFF",
    borderRadius: 3,
    backgroundColor: "#0E5B36",
    alignItems: "center",
    justifyContent: "center",
  },
  walletDot: {
    width: 3,
    height: 3,
    borderRadius: 2,
    backgroundColor: "#FFFFFF",
  },
  bannerCopy: { flex: 1 },
  walletTitle: { fontSize: 16, fontWeight: "700", color: "#FFFFFF", marginBottom: 2 },
  walletSubtitle: { fontSize: 12, color: "rgba(255,255,255,0.82)" },
  walletChevron: { color: "#FFFFFF", fontSize: 24, marginLeft: 8 },
  mintIcon: { backgroundColor: "#E8F4EC" },
  serviceIconCircle: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  bookingsCard: { backgroundColor: "#FFFFFF", borderRadius: 18, borderWidth: 1, borderColor: "#E6EAE4", padding: 14, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  bookingsIcon: { fontSize: 18, color: "#0E5B36" },
  bookingsTitle: { fontSize: 15, fontWeight: "700", color: "#141915", marginBottom: 2 },
  bookingsSubtitle: { fontSize: 11, color: "#6C766E" },
  bookingsChevron: { color: "#6C766E", fontSize: 22 },
});

function ServiceCard({
  config,
  index = 0,
  onPress,
}: {
  config: typeof SERVICE_CONFIG[keyof typeof SERVICE_CONFIG];
  index?: number;
  onPress: () => void;
}) {
  const entrance = useSharedValue(0);
  const pressScale = useSharedValue(1);

  React.useEffect(() => {
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
    <Animated.View style={entranceStyle}>
      <Animated.View style={pressStyle}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={config.accessibilityLabel}
          onPress={onPress}
          onPressIn={() => { pressScale.value = withSpring(0.96, { damping: 20 }); }}
          onPressOut={() => { pressScale.value = withSpring(1, { damping: 20 }); }}
          style={({ pressed }) => [
            styles.card,
            { backgroundColor: config.bgColor, borderColor: config.borderColor },
            pressed && { opacity: 0.85 },
          ]}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <View pointerEvents="none" style={styles.cardAccent} />
          <View style={styles.cardTopRow}>
            <View style={[styles.iconWrapper, { backgroundColor: config.iconBg }]}>
              <Text style={styles.iconText}>{config.icon}</Text>
            </View>
            <View style={styles.arrowBadge}>
              <Text style={styles.arrowText}>{"\u2197"}</Text>
            </View>
          </View>
          <Text style={styles.title}>{config.label}</Text>
          <Text style={styles.hint}>{config.hint}</Text>
        </Pressable>
      </Animated.View>
    </Animated.View>
  );
}

function WalletBanner({ onPress }: { onPress: () => void }) {
  const pressScale = useSharedValue(1);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Open Pamoja wallet"
      onPress={onPress}
      onPressIn={() => { pressScale.value = withSpring(0.98, { damping: 20 }); }}
      onPressOut={() => { pressScale.value = withSpring(1, { damping: 20 }); }}
      style={({ pressed }) => [styles.banner, pressed && { opacity: 0.85 }]}
    >
      <View style={styles.bannerLeft}>
        <View style={styles.walletIconBox}>
          <View style={styles.walletShape}>
            <View style={styles.walletFlap}>
              <View style={styles.walletDot} />
            </View>
          </View>
        </View>
        <View style={styles.bannerCopy}>
          <Text style={styles.walletTitle}>Your Pamoja wallet</Text>
          <Text style={styles.walletSubtitle}>Payments, all in one place</Text>
        </View>
      </View>
      <Text style={styles.walletChevron}>›</Text>
    </Pressable>
  );
}

function BookingsBanner({ onPress }: { onPress: () => void }) {
  const pressScale = useSharedValue(1);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Open your accommodation bookings"
      onPress={onPress}
      onPressIn={() => { pressScale.value = withSpring(0.98, { damping: 20 }); }}
      onPressOut={() => { pressScale.value = withSpring(1, { damping: 20 }); }}
      style={({ pressed }) => [styles.bookingsCard, pressed && { opacity: 0.85 }]}
    >
      <View style={styles.bannerLeft}>
        <View style={[styles.serviceIconCircle, styles.mintIcon]}>
          <Text style={styles.bookingsIcon}>▦</Text>
        </View>
        <View style={styles.bannerCopy}>
          <Text style={styles.bookingsTitle}>My bookings</Text>
          <Text style={styles.bookingsSubtitle}>Manage your accommodation bookings</Text>
        </View>
      </View>
      <Text style={styles.bookingsChevron}>›</Text>
    </Pressable>
  );
}

export function ServiceEntry({
  serviceKey,
  onPress,
  index = 0,
  variant = "card",
}: ServiceEntryProps) {
  const config = SERVICE_CONFIG[serviceKey];

  if (variant === "banner") {
    if (serviceKey === "wallet") return <WalletBanner onPress={onPress} />;
    if (serviceKey === "stays") return <BookingsBanner onPress={onPress} />;
  }

  return <ServiceCard config={config} index={index} onPress={onPress} />;
}

export function getServiceConfig(key: ServiceKey) {
  return SERVICE_CONFIG[key];
}