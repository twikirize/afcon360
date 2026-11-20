import React, { useEffect } from 'react';
import { View, Text, Pressable, Image, StyleSheet, ActivityIndicator, FlatList } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withRepeat,
  withDelay,
} from 'react-native-reanimated';
import { colors, typography, spacing, radii, shadows } from '../theme/tokens';
import type { FeedItem, FeedMetadata } from '../types/feed';
import { imageUri, feedTypeLabel, feedTypeIcon } from '../utils/feedUtils';

type TrendingRailProps = {
  data: FeedItem[];
  baseUrl: string;
  onPress: (item: FeedItem) => void;
  loadingMore?: boolean;
  onEndReached?: () => void;
  searchActive?: boolean;
};

function feedMeta(item: FeedItem): string | null {
  const metadata = item.metadata as FeedMetadata | undefined;
  if (!metadata) return null;

  if (item.type === 'property') {
    return [metadata.property_type, metadata.city, metadata.country]
      .filter((v): v is string => typeof v === 'string' && v.length > 0)
      .join(' · ') || null;
  }
  if (item.type === 'transport') {
    return [metadata.route_type, metadata.primary_zone]
      .filter((v): v is string => typeof v === 'string' && v.length > 0)
      .join(' · ') || null;
  }
  if (item.type === 'event') {
    return [metadata.city, metadata.country]
      .filter((v): v is string => typeof v === 'string' && v.length > 0)
      .join(', ') || null;
  }
  if (item.type === 'system_update' && typeof metadata.module_label === 'string') {
    return metadata.module_label;
  }
  return null;
}

const styles = StyleSheet.create({
  rail: {
    gap: spacing.md,
    paddingRight: spacing.xs,
  },
  card: {
    width: 286,
    minHeight: 122,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
  },
  cardAd: {
    borderColor: '#F0D98F',
    backgroundColor: '#FFFBF0',
  },
  visual: {
    width: 94,
    height: 98,
    borderRadius: radii.md,
    overflow: 'hidden',
    backgroundColor: '#E9F0E9',
    flexShrink: 0,
  },
  image: {
    width: '100%',
    height: '100%',
  },
  fallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#E8F0E8',
  },
  fallbackIcon: {
    fontSize: 32,
  },
  pinnedMark: {
    position: 'absolute',
    left: spacing.xs,
    top: spacing.xs,
    backgroundColor: colors.brand.gold,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    zIndex: 1,
  },
  pinnedText: {
    color: colors.brand.dark,
    fontSize: typography.overline.fontSize,
    fontWeight: '900',
  },
  copy: {
    flex: 1,
    justifyContent: 'center',
    gap: spacing.xs,
    minWidth: 0,
  },
  tagRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    flexWrap: 'wrap',
  },
  tag: {
    color: colors.brand.emerald,
    fontSize: typography.overline.fontSize,
    fontWeight: '900',
    letterSpacing: 0.7,
  },
  sponsoredMark: {
    color: '#815E12',
    backgroundColor: colors.brand.goldSoft,
    fontSize: typography.overline.fontSize,
    fontWeight: '900',
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  websiteMark: {
    color: colors.brand.emerald,
    backgroundColor: '#E8F3EA',
    fontSize: typography.overline.fontSize,
    fontWeight: '900',
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  promoMark: {
    color: '#B8450A',
    backgroundColor: '#FFF3E0',
    fontSize: typography.overline.fontSize,
    fontWeight: '900',
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  title: {
    color: colors.text.ink,
    fontSize: typography.body.fontSize,
    lineHeight: typography.body.lineHeight,
    fontWeight: '900',
  },
  meta: {
    color: colors.text.muted,
    fontSize: typography.caption.fontSize,
    lineHeight: typography.caption.lineHeight,
  },
  body: {
    color: '#68766D',
    fontSize: typography.caption.fontSize,
    lineHeight: typography.caption.lineHeight,
  },
  arrow: {
    color: colors.brand.emerald,
    fontSize: 24,
    fontWeight: '700',
    marginLeft: spacing.xs,
  },
  skeleton: {
    width: 286,
    minHeight: 122,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
  },
  skeletonVisual: {
    width: 94,
    height: 98,
    borderRadius: radii.md,
    backgroundColor: '#E8F0E8',
  },
  skeletonCopy: {
    flex: 1,
    gap: spacing.sm,
  },
  skeletonTag: {
    width: 60,
    height: 10,
    borderRadius: radii.sm,
    backgroundColor: '#E8F0E8',
  },
  skeletonLine: {
    height: 12,
    borderRadius: radii.sm,
    backgroundColor: '#E8F0E8',
  },
  moreLoading: {
    width: 42,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyState: {
    minHeight: 122,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.xs,
  },
  emptyIcon: {
    color: colors.brand.emerald,
    fontSize: 24,
  },
  emptyTitle: {
    color: colors.text.ink,
    fontSize: typography.body.fontSize,
    fontWeight: '900',
    textAlign: 'center',
  },
  emptyBody: {
    color: colors.text.muted,
    fontSize: typography.caption.fontSize,
    lineHeight: typography.caption.lineHeight,
    textAlign: 'center',
  },
});

const SkeletonCard = () => {
  const pulse = useSharedValue(0.55);

  useEffect(() => {
    pulse.value = withRepeat(withTiming(1, { duration: 900 }), -1, true);
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({ opacity: pulse.value }));

  return (
    <Animated.View style={[styles.skeleton, animatedStyle]}>
      <View style={styles.skeletonVisual} />
      <View style={styles.skeletonCopy}>
        <View style={styles.skeletonTag} />
        <View style={[styles.skeletonLine, { width: '90%' }]} />
        <View style={[styles.skeletonLine, { width: '65%' }]} />
      </View>
    </Animated.View>
  );
};

const TrendCard = ({
  item,
  baseUrl,
  onPress,
  index,
}: {
  item: FeedItem;
  baseUrl: string;
  onPress: () => void;
  index: number;
}) => {
  const image = imageUri(item.image_url, baseUrl);
  const meta = feedMeta(item);
  const isAd = item.type === 'ad';
  const isPromo = item.metadata?.promo === true || item.metadata?.is_promo === true;
  const isWeb = Boolean(item.link_url) && !['event', 'property', 'transport'].includes(item.type);

  const entrance = useSharedValue(0);
  const pressScale = useSharedValue(1);

  useEffect(() => {
    entrance.value = withDelay(index * 60, withSpring(1, { damping: 20, stiffness: 150 }));
  }, [index]);

  const entranceStyle = useAnimatedStyle(() => ({
    opacity: entrance.value,
    transform: [
      { translateY: (1 - entrance.value) * 16 },
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
          accessibilityRole='button'
          accessibilityLabel={'Open ' + (item.title || feedTypeLabel(item.type).toLowerCase()) + ' on Pamoja'}
          onPress={onPress}
          onPressIn={() => { pressScale.value = withSpring(0.97, { damping: 20 }); }}
          onPressOut={() => { pressScale.value = withSpring(1, { damping: 20 }); }}
          style={({ pressed }) => [
            styles.card,
            isAd && styles.cardAd,
            pressed && { opacity: 0.85 },
          ]}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <View style={styles.visual}>
            {image ? (
              <Image source={{ uri: image }} style={styles.image} resizeMode='cover' />
            ) : (
              <View style={styles.fallback}>
                <Text style={styles.fallbackIcon}>{feedTypeIcon(item.type)}</Text>
              </View>
            )}
            {item.is_pinned ? (
              <View style={styles.pinnedMark}>
                <Text style={styles.pinnedText}>PINNED</Text>
              </View>
            ) : null}
          </View>
          <View style={styles.copy}>
            <View style={styles.tagRow}>
              <Text style={styles.tag}>{feedTypeLabel(item.type)}</Text>
              {isAd ? <Text style={styles.sponsoredMark}>AD</Text> : null}
              {isPromo && !isAd ? <Text style={styles.promoMark}>PROMO</Text> : null}
              {isWeb && !isAd && !isPromo ? <Text style={styles.websiteMark}>WEB</Text> : null}
            </View>
            <Text numberOfLines={2} style={styles.title}>
              {item.title || 'Discover more on Pamoja'}
            </Text>
            {meta ? <Text numberOfLines={1} style={styles.meta}>{meta}</Text> : null}
            {item.body ? <Text numberOfLines={2} style={styles.body}>{item.body}</Text> : null}
          </View>
          <Text style={styles.arrow}>{'\u203A'}</Text>
        </Pressable>
      </Animated.View>
    </Animated.View>
  );
};

export const TrendingRail = ({
  data,
  baseUrl,
  onPress,
  loadingMore,
  onEndReached,
  searchActive,
}: TrendingRailProps) => {
  if (data.length === 0) {
    return (
      <View style={styles.emptyState}>
        <Text style={styles.emptyIcon}>{searchActive ? '\u2315' : '\u2728'}</Text>
        <Text style={styles.emptyTitle}>
          {searchActive ? 'No matching highlights' : 'Fresh highlights are on the way'}
        </Text>
        <Text style={styles.emptyBody}>
          {searchActive
            ? 'Try another word or clear your search.'
            : 'New events, stays, mobility offers and Pamoja updates will appear here.'}
        </Text>
      </View>
    );
  }

  return (
    <FlatList
      horizontal
      data={data}
      keyExtractor={(item) => item.feed_id}
      renderItem={({ item, index }) => (
        <TrendCard
          item={item}
          baseUrl={baseUrl}
          onPress={() => onPress(item)}
          index={index}
        />
      )}
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.rail}
      onEndReached={onEndReached}
      onEndReachedThreshold={0.6}
      ListFooterComponent={
        loadingMore ? (
          <View style={styles.moreLoading}>
            <ActivityIndicator color={colors.brand.emerald} />
          </View>
        ) : undefined
      }
    />
  );
};

export const TrendingSkeleton = ({ count = 3 }: { count?: number }) => (
  <FlatList
    horizontal
    data={Array.from({ length: count }, (_, i) => i)}
    keyExtractor={(i) => String(i)}
    renderItem={() => <SkeletonCard />}
    showsHorizontalScrollIndicator={false}
    scrollEnabled={false}
    contentContainerStyle={styles.rail}
  />
);

export default TrendingRail;
