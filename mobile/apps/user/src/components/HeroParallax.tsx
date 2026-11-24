import React, { useEffect, useMemo } from 'react';
import { View, Text, StyleSheet, Image, Pressable } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withRepeat,
  withDelay,
  interpolate,
  Extrapolation,
  type SharedValue,
} from 'react-native-reanimated';
import { colors, typography, radii, shadows } from '../theme/tokens';
import type { FeedItem } from '../types/feed';
import { feedTypeLabel, imageUri } from '../utils/feedUtils';

type HeroParallaxProps = {
  scrollY?: SharedValue<number>;
  featured?: FeedItem | null;
  baseUrl?: string;
  onFeaturedPress?: () => void;
  onExplore?: () => void;
};

const styles = StyleSheet.create({
  hero: {
    minHeight: 260,
    borderRadius: 28,
    padding: 22,
    overflow: 'hidden',
    backgroundColor: colors.brand.dark,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.10)',
    ...shadows.hero,
  },
  heroImage: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  heroScrim: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(15,35,24,0.68)',
  },
  orbLarge: {
    position: 'absolute',
    width: 280,
    height: 280,
    borderRadius: 140,
    backgroundColor: 'rgba(41,150,91,0.14)',
    top: -120,
    right: -100,
  },
  orbSmall: {
    position: 'absolute',
    width: 180,
    height: 180,
    borderRadius: 90,
    borderWidth: 1,
    borderColor: 'rgba(255,204,0,0.20)',
    bottom: -84,
    right: -24,
  },
  copy: {
    flex: 1,
    justifyContent: 'center',
    gap: 9,
    zIndex: 1,
    maxWidth: '100%',
  },
  eyebrowPill: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.18)',
  },
  eyebrowDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: colors.brand.gold,
  },
  eyebrowText: {
    color: 'rgba(255,255,255,0.9)',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.8,
  },
  tagRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  badge: {
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 6,
    backgroundColor: colors.brand.gold,
  },
  badgeText: {
    color: colors.brand.dark,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.5,
  },
  promoBadge: {
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 6,
    backgroundColor: '#FF8A3D',
  },
  promoBadgeText: {
    color: '#FFFFFF',
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.5,
  },
  title: {
    color: colors.surface.white,
    fontSize: 32,
    lineHeight: 38,
    fontWeight: '900',
    letterSpacing: -0.9,
  },
  titleGold: {
    color: colors.brand.gold,
  },
  subtitle: {
    maxWidth: 280,
    color: 'rgba(255,255,255,0.80)',
    fontSize: 13,
    lineHeight: 19,
  },
  featuredAction: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 13,
    paddingVertical: 8,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.22)',
    backgroundColor: 'rgba(255,255,255,0.12)',
  },
  featuredCopy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  featuredLabel: {
    color: 'rgba(255,255,255,0.78)',
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.9,
  },
  featuredTitle: {
    color: colors.surface.white,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '800',
  },
  featuredArrow: {
    color: colors.brand.gold,
    fontSize: 25,
    lineHeight: 28,
    fontWeight: '700',
  },
  cta: {
    alignSelf: 'flex-start',
    minHeight: 44,
    marginTop: 4,
    paddingHorizontal: 16,
    borderRadius: 12,
    backgroundColor: colors.brand.gold,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  ctaPressed: {
    opacity: 0.85,
  },
  ctaText: {
    color: colors.brand.dark,
    fontSize: 11,
    fontWeight: '900',
  },
  ctaArrow: {
    color: colors.brand.dark,
    fontSize: 18,
    lineHeight: 20,
    fontWeight: '800',
  },
});

export const HeroParallax = ({
  scrollY,
  featured,
  baseUrl,
  onFeaturedPress,
  onExplore,
}: HeroParallaxProps) => {
  const titleY = useSharedValue(40);
  const titleOpacity = useSharedValue(0);
  const subtitleOpacity = useSharedValue(0);
  const subtitleY = useSharedValue(16);
  const badgeOpacity = useSharedValue(0);
  const badgeY = useSharedValue(12);
  const orbLargeScale = useSharedValue(0);
  const orbSmallScale = useSharedValue(0);

  useEffect(() => {
    titleY.value = withSpring(0, { damping: 18, stiffness: 120 });
    titleOpacity.value = withDelay(40, withSpring(1, { damping: 18, stiffness: 120 }));

    badgeOpacity.value = withDelay(160, withSpring(1, { damping: 18 }));
    badgeY.value = withDelay(160, withSpring(0, { damping: 18 }));

    subtitleOpacity.value = withDelay(240, withSpring(1, { damping: 18 }));
    subtitleY.value = withDelay(240, withSpring(0, { damping: 18 }));

    orbLargeScale.value = withSpring(1, { damping: 20, stiffness: 90 });
    orbLargeScale.value = withDelay(1200, withRepeat(withTiming(0.92, { duration: 3500 }), -1, true));

    orbSmallScale.value = withDelay(200, withSpring(1, { damping: 20, stiffness: 90 }));
    orbSmallScale.value = withDelay(1400, withRepeat(withTiming(0.9, { duration: 4200 }), -1, true));
  }, []);

  const orbLargeStyle = useAnimatedStyle(() => {
    const shift = scrollY ? interpolate(scrollY.value, [0, 240], [0, 36], Extrapolation.CLAMP) : 0;
    return { transform: [{ translateY: shift }, { scale: orbLargeScale.value }] };
  });

  const orbSmallStyle = useAnimatedStyle(() => {
    const shift = scrollY ? interpolate(scrollY.value, [0, 240], [0, 22], Extrapolation.CLAMP) : 0;
    return { transform: [{ translateY: -shift }, { scale: orbSmallScale.value }] };
  });

  const titleStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: titleY.value }],
    opacity: titleOpacity.value,
  }));

  const badgeStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: badgeY.value }],
    opacity: badgeOpacity.value,
  }));

  const subtitleStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: subtitleY.value }],
    opacity: subtitleOpacity.value,
  }));

  const featuredImage = useMemo(() => {
    if (!featured || !baseUrl) return null;
    return imageUri(featured.image_url, baseUrl);
  }, [featured, baseUrl]);

  const isPromo = featured?.metadata?.promo === true || featured?.metadata?.is_promo === true;
  const isAd = featured?.type === 'ad';

  return (
    <View style={styles.hero}>
      {featuredImage ? (
        <>
          <Image source={{ uri: featuredImage }} style={styles.heroImage} resizeMode='cover' />
          <View style={styles.heroScrim} />
        </>
      ) : (
        <>
          <Animated.View style={[styles.orbLarge, orbLargeStyle]} />
          <Animated.View style={[styles.orbSmall, orbSmallStyle]} />
        </>
      )}

      <View style={styles.copy}>
        <Animated.View style={badgeStyle}>
          <View style={styles.eyebrowPill}>
            <View style={styles.eyebrowDot} />
            <Text style={styles.eyebrowText}>{'PAMOJA · EAST AFRICA & BEYOND'}</Text>
          </View>
        </Animated.View>

        <Animated.Text style={[styles.title, titleStyle]}>
          Your Africa.{'\n'}
          <Text style={styles.titleGold}>Your journey.</Text>
        </Animated.Text>

        <Animated.Text style={[styles.subtitle, subtitleStyle]}>
          {'Stays, rides, events, adventures and more — together on Pamoja.'}
        </Animated.Text>

        {featured ? (
          <Pressable
            accessibilityRole='button'
            accessibilityLabel={'Open ' + (featured.title || 'featured highlight')}
            onPress={onFeaturedPress}
            style={({ pressed }) => [styles.featuredAction, pressed && styles.ctaPressed]}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <View style={styles.featuredCopy}>
              <View style={styles.tagRow}>
                <Text style={styles.featuredLabel}>{feedTypeLabel(featured.type)}</Text>
                {isAd ? <Text style={styles.promoBadgeText}>SPONSORED</Text> : isPromo ? <Text style={styles.promoBadgeText}>PROMO</Text> : null}
              </View>
              <Text numberOfLines={1} style={styles.featuredTitle}>
                {featured.title || 'Discover more on Pamoja'}
              </Text>
            </View>
            <Text style={styles.featuredArrow}>{'\u203A'}</Text>
          </Pressable>
        ) : (
          <Pressable
            accessibilityRole='button'
            accessibilityLabel='Explore Pamoja services'
            onPress={onExplore}
            style={({ pressed }) => [styles.cta, pressed && styles.ctaPressed]}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={styles.ctaText}>Explore Pamoja</Text>
            <Text style={styles.ctaArrow}>{'\u203A'}</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
};

export default HeroParallax;