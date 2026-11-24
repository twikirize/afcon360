import React from 'react';
import { View, Text, StyleSheet, Image } from 'react-native';
import { colors, radii, spacing, typography } from '../../theme';

type HeroBannerProps = {
  title?: string;
  subtitle?: string;
  illustration?: React.ReactNode;
  style?: ViewStyle;
};

import { ViewStyle } from 'react-native';

export function HeroBanner({
  title = 'Your world,\ntogether.',
  subtitle = 'One app. More to explore.',
  illustration,
  style,
}: HeroBannerProps) {
  return (
    <View style={[styles.container, style]}>
      <View style={styles.content}>
        <Text style={[typography.heroTitle, styles.title, { color: colors.brand.primary }]}>{title}</Text>
        <Text style={[typography.cardSubtitle, styles.subtitle, { color: colors.text.secondary }]}>{subtitle}</Text>
      </View>
      <View style={styles.illustrationContainer}>
        {illustration || (
          <View style={styles.defaultIllustration}>
            <View style={styles.sunHalo}>
              <View style={styles.sunDot} />
            </View>
            <View style={styles.skyline}>
              <View style={[styles.tower, { height: 40 }]} />
              <View style={[styles.tower, { height: 58, backgroundColor: '#5D9A74' }]} />
              <View style={[styles.tower, { height: 34 }]} />
              <View style={[styles.tower, { height: 50, backgroundColor: '#498762' }]} />
            </View>
            <View style={styles.travelerRow}>
              <View style={styles.travelerCircle}>
                <View style={styles.peopleGlyph}>
                  <View style={styles.peopleHeadLeft} />
                  <View style={styles.peopleHeadRight} />
                  <View style={styles.peopleBodyLeft} />
                  <View style={styles.peopleBodyRight} />
                </View>
              </View>
            </View>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.brand.primaryLight,
    borderRadius: radii.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.lg,
    minHeight: 140,
    overflow: 'hidden',
  },
  content: {
    flex: 1,
    paddingRight: spacing.md,
    gap: spacing.sm,
  },
  title: {
    fontFamily: 'PlusJakartaSans_700Bold',
  },
  subtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
  },
  illustrationContainer: {
    width: 100,
    height: 100,
    alignItems: 'center',
    justifyContent: 'flex-end',
  },
  defaultIllustration: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'flex-end',
  },
  sunHalo: {
    position: 'absolute',
    top: 0,
    left: 20,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: 'rgba(245,183,0,0.24)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sunDot: {
    width: 11,
    height: 11,
    borderRadius: 5.5,
    backgroundColor: '#EA8426',
  },
  skyline: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 5,
    opacity: 0.35,
    marginBottom: 8,
  },
  tower: {
    width: 12,
    backgroundColor: colors.brand.primary,
    borderTopLeftRadius: 3,
    borderTopRightRadius: 3,
  },
  travelerRow: {
    alignItems: 'center',
  },
  travelerCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#1E5B39',
    alignItems: 'center',
    justifyContent: 'center',
  },
  peopleGlyph: {
    width: 36,
    height: 30,
    position: 'relative',
  },
  peopleHeadLeft: {
    position: 'absolute',
    left: 6,
    top: 1,
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.surface,
  },
  peopleHeadRight: {
    position: 'absolute',
    right: 5,
    top: 1,
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.surface,
  },
  peopleBodyLeft: {
    position: 'absolute',
    left: 1,
    bottom: 1,
    width: 21,
    height: 13,
    borderTopLeftRadius: 14,
    borderTopRightRadius: 14,
    backgroundColor: colors.surface,
  },
  peopleBodyRight: {
    position: 'absolute',
    right: 1,
    bottom: 1,
    width: 21,
    height: 13,
    borderTopLeftRadius: 14,
    borderTopRightRadius: 14,
    backgroundColor: colors.surface,
  },
});