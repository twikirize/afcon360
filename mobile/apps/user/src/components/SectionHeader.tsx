import React, { useEffect } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withRepeat,
  withDelay,
} from 'react-native-reanimated';
import { colors, typography, spacing, radii } from '../theme/tokens';

type SectionHeaderProps = {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  index?: number;
  live?: boolean;
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  titleGroup: {
    gap: 2,
  },
  title: {
    color: colors.text.ink,
    fontSize: typography.headline.fontSize,
    lineHeight: typography.headline.lineHeight,
    fontWeight: '900',
    letterSpacing: -0.3,
  },
  subtitle: {
    color: colors.text.muted,
    fontSize: typography.caption.fontSize,
    lineHeight: typography.caption.lineHeight,
    fontWeight: '600',
  },
  pulseContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radii.pill,
    backgroundColor: '#E8F3EA',
  },
  pulseDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.brand.emerald,
  },
  pulseText: {
    color: colors.brand.emerald,
    fontSize: typography.overline.fontSize,
    fontWeight: '900',
    letterSpacing: 0.6,
  },
});

const LivePulse = () => {
  const opacity = useSharedValue(1);

  useEffect(() => {
    opacity.value = withRepeat(withTiming(0.35, { duration: 1100 }), -1, true);
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <View style={styles.pulseContainer}>
      <Animated.View style={[styles.pulseDot, animatedStyle]} />
      <Text style={styles.pulseText}>LIVE</Text>
    </View>
  );
};

export const SectionHeader = ({
  title,
  subtitle,
  action,
  index = 0,
  live = false,
}: SectionHeaderProps) => {
  const entrance = useSharedValue(0);

  useEffect(() => {
    entrance.value = withDelay(
      Math.min(index, 4) * 100,
      withSpring(1, { damping: 20, stiffness: 150 })
    );
  }, [index]);

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: entrance.value,
    transform: [{ translateY: (1 - entrance.value) * 12 }],
  }));

  return (
    <Animated.View style={[styles.container, animatedStyle]}>
      <View style={styles.titleGroup}>
        <Text accessibilityRole='header' style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
      {action ? <View>{action}</View> : live ? <LivePulse /> : <View />}
    </Animated.View>
  );
};

export default SectionHeader;