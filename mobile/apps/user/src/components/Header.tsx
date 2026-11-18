import React, { useEffect } from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withDelay,
} from "react-native-reanimated";
import { useRouter } from "expo-router";
import { colors, typography, spacing, radii, shadows } from "../theme/tokens";
import { useAuth } from "../auth/AuthProvider";

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  brandLockup: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  brandMark: {
    width: 44,
    height: 44,
    borderRadius: radii.md,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brand.dark,
    ...shadows.card,
  },
  brandMarkText: {
    color: colors.brand.gold,
    fontSize: 26,
    lineHeight: 32,
    fontWeight: "900",
  },
  brandCopy: {
    gap: spacing.xs,
  },
  brandName: {
    color: colors.brand.dark,
    fontSize: typography.title.fontSize,
    lineHeight: typography.title.lineHeight,
    fontWeight: "900",
    letterSpacing: -0.6,
  },
  brandRegion: {
    color: colors.text.muted,
    fontSize: typography.overline.fontSize,
    fontWeight: "900",
    letterSpacing: 1.1,
  },
  profileButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#E4EEE5",
    borderWidth: 1,
    borderColor: "#D2E1D4",
    ...shadows.card,
  },
  profileInitials: {
    color: colors.brand.dark,
    fontSize: typography.caption.fontSize,
    fontWeight: "900",
  },
});

export const Header = () => {
  const router = useRouter();
  const { user } = useAuth();

  const brandEntrance = useSharedValue(0);
  const profileEntrance = useSharedValue(0);

  useEffect(() => {
    brandEntrance.value = withDelay(100, withSpring(1, { damping: 20, stiffness: 150 }));
    profileEntrance.value = withDelay(200, withSpring(1, { damping: 20, stiffness: 150 }));
  }, []);

  const brandStyle = useAnimatedStyle(() => ({
    opacity: brandEntrance.value,
    transform: [{ translateX: (1 - brandEntrance.value) * -20 }],
  }));

  const profileStyle = useAnimatedStyle(() => ({
    opacity: profileEntrance.value,
    transform: [{ translateX: (1 - profileEntrance.value) * 20 }],
  }));

  const profileName = user?.display_name || user?.username || "Pamoja user";
  const profileInitials = profileName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join("")
    .toUpperCase() || "P";

  const isSignedIn = Boolean(user);
  const authLabel = isSignedIn ? "Open Account" : "Sign in or get started";
  const authDestination = isSignedIn ? "/(tabs)/account" : "/login";

  return (
    <View style={styles.container}>
      <Animated.View style={brandStyle}>
        <View style={styles.brandLockup}>
          <View style={styles.brandMark}>
            <Text style={styles.brandMarkText}>P</Text>
          </View>
          <View style={styles.brandCopy}>
            <Text style={styles.brandName}>Pamoja</Text>
            <Text style={styles.brandRegion}>EAST AFRICA & BEYOND</Text>
          </View>
        </View>
      </Animated.View>
      <Animated.View style={profileStyle}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={authLabel}
          onPress={() => router.push(authDestination as never)}
          style={({ pressed }) => [
            styles.profileButton,
            pressed && { opacity: 0.8, transform: [{ scale: 0.95 }] },
          ]}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          {isSignedIn ? (
            <Text style={styles.profileInitials}>{profileInitials}</Text>
          ) : (
            <Text style={styles.profileInitials}>👤</Text>
          )}
        </Pressable>
      </Animated.View>
    </View>
  );
};

export default Header;