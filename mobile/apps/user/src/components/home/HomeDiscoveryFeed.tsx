import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

type FeedItem = {
  feed_id: string;
  type: string;
  title?: string;
  body?: string;
  image_url?: string;
  link_url?: string;
  author_name?: string;
  source_module?: string;
  created_at?: string | null;
  is_pinned?: boolean;
  metadata?: Record<string, unknown>;
};

type FeedResponse = {
  items?: FeedItem[];
  page?: number;
  has_more?: boolean;
  seed?: string;
  error?: string;
};

type FeedCategory = 'All' | 'Transport' | 'Stays' | 'Events' | 'Adventure' | 'Offers';

const CATEGORIES: FeedCategory[] = [
  'All',
  'Transport',
  'Stays',
  'Events',
  'Adventure',
  'Offers',
];

function categoryFor(item: FeedItem): Exclude<FeedCategory, 'All'> | 'Community' | 'Pamoja' {
  const source = (item.source_module || '').toLowerCase();

  if (item.type === 'ad') return 'Offers';
  if (item.type === 'event' || source.includes('event')) return 'Events';
  if (item.type === 'property' || source.includes('accommodation') || source === 'stays') return 'Stays';
  if (item.type === 'transport' || source.includes('transport')) return 'Transport';
  if (source.includes('adventure') || source.includes('tourism') || source.includes('travel')) return 'Adventure';
  if (source.includes('offer') || source.includes('promotion') || source.includes('marketing')) return 'Offers';
  if (item.type === 'system_update') return 'Pamoja';
  return 'Community';
}

function iconFor(category: string): keyof typeof MaterialIcons.glyphMap {
  switch (category) {
    case 'Transport': return 'directions-car';
    case 'Stays': return 'hotel';
    case 'Events': return 'event';
    case 'Adventure': return 'explore';
    case 'Offers': return 'local-offer';
    case 'Pamoja': return 'campaign';
    default: return 'dynamic-feed';
  }
}

function formatDate(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

interface HomeDiscoveryFeedProps {
  baseUrl: string;
  refreshKey?: number;
}

export const HomeDiscoveryFeed = ({ baseUrl, refreshKey = 0 }: HomeDiscoveryFeedProps) => {
  const router = useRouter();
  const [items, setItems] = useState<FeedItem[]>([]);
  const [category, setCategory] = useState<FeedCategory>('All');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const requestInFlight = useRef(false);
  const seed = useRef(String(Date.now()));

  const loadPage = useCallback(async (nextPage: number, replace: boolean) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    if (replace) {
      setLoading(true);
      setError('');
    } else {
      setLoadingMore(true);
    }

    try {
      const origin = baseUrl.replace(/\/$/, '');
      const query = new URLSearchParams({
        page: String(nextPage),
        per_page: '10',
        layout: 'mixed',
        seed: seed.current,
      });
      const response = await fetch(origin + '/api/home/feed?' + query.toString());
      if (!response.ok) throw new Error('Feed request failed. Please try again.');

      const result = (await response.json()) as FeedResponse;
      const nextItems = Array.isArray(result.items) ? result.items : [];
      if (result.error && nextItems.length === 0) {
        throw new Error(result.error);
      }

      setItems((current) => {
        if (replace) return nextItems;
        const known = new Set(current.map((item) => item.feed_id));
        return [...current, ...nextItems.filter((item) => !known.has(item.feed_id))];
      });
      setPage(result.page || nextPage);
      setHasMore(Boolean(result.has_more));
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Pamoja updates.');
    } finally {
      requestInFlight.current = false;
      setLoading(false);
      setLoadingMore(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    seed.current = String(Date.now());
    setItems([]);
    setPage(1);
    setHasMore(false);
    void loadPage(1, true);
  }, [loadPage, refreshKey]);

  const visibleItems = items.filter((item) => {
    if (category === 'All') return true;
    return categoryFor(item) === category;
  });

  const openItem = async (item: FeedItem) => {
    const itemCategory = categoryFor(item);
    const destination =
      itemCategory === 'Transport' ? '/(service)/ride' :
      itemCategory === 'Stays' ? '/(service)/stays' :
      itemCategory === 'Events' ? '/(service)/events' :
      itemCategory === 'Adventure' ? '/(service)/adventure' :
      null;

    if (destination) {
      router.push(destination as any);
      return;
    }

    const link = item.link_url || '';
    if (/^https?:\/\//i.test(link)) {
      try { await Linking.openURL(link); } catch { /* Keep the feed usable if a link cannot open. */ }
    } else if (link.startsWith('/')) {
      try { await Linking.openURL(baseUrl.replace(/\/$/, '') + link); } catch { /* No-op. */ }
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.heading}>
        <View style={styles.headingText}>
          <Text style={styles.title}>Discover on Pamoja</Text>
          <Text style={styles.subtitle}>What's happening across your world.</Text>
        </View>
        <MaterialIcons name="dynamic-feed" size={27} color={homeDesign.primaryGreen} />
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filters}
      >
        {CATEGORIES.map((item) => {
          const selected = category === item;
          return (
            <Pressable
              key={item}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              onPress={() => setCategory(item)}
              style={[styles.filter, selected && styles.filterSelected]}
            >
              <Text style={[styles.filterText, selected && styles.filterTextSelected]}>
                {item}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {loading ? (
        <View style={styles.stateBox}>
          <ActivityIndicator color={homeDesign.primaryGreen} />
          <Text style={styles.stateText}>Loading the latest from Pamoja…</Text>
        </View>
      ) : error && items.length === 0 ? (
        <View style={styles.stateBox}>
          <MaterialIcons name="cloud-off" size={28} color={homeDesign.textGray} />
          <Text style={styles.stateText}>{error}</Text>
          <Pressable onPress={() => void loadPage(1, true)} style={styles.retryButton}>
            <Text style={styles.retryText}>Try again</Text>
          </Pressable>
        </View>
      ) : visibleItems.length === 0 ? (
        <View style={styles.stateBox}>
          <MaterialIcons name="travel-explore" size={29} color={homeDesign.textGray} />
          <Text style={styles.stateText}>
            {items.length === 0
              ? 'New experiences and updates will appear here as they are published.'
              : 'Nothing in this category yet. Try another filter.'}
          </Text>
        </View>
      ) : (
        <View style={styles.list}>
          {visibleItems.map((item) => {
            const itemCategory = categoryFor(item);
            const sponsored = item.type === 'ad';
            const date = formatDate(item.created_at);
            return (
              <Pressable
                key={item.feed_id}
                accessibilityRole="button"
                onPress={() => void openItem(item)}
                style={styles.card}
              >
                <View style={styles.media}>
                  {item.image_url ? (
                    <Image source={{ uri: item.image_url }} style={styles.image} resizeMode="cover" />
                  ) : (
                    <View style={styles.imageFallback}>
                      <MaterialIcons name={iconFor(itemCategory)} size={34} color="#F5D56A" />
                    </View>
                  )}
                </View>
                <View style={styles.cardContent}>
                  <View style={styles.metaRow}>
                    <Text style={styles.categoryLabel}>{sponsored ? 'SPONSORED' : itemCategory.toUpperCase()}</Text>
                    {date ? <Text style={styles.date}>{date}</Text> : null}
                  </View>
                  <Text style={styles.cardTitle} numberOfLines={2}>
                    {item.title || item.author_name || 'Discover more on Pamoja'}
                  </Text>
                  {!!item.body && (
                    <Text style={styles.cardBody} numberOfLines={2}>{item.body}</Text>
                  )}
                  <View style={styles.cardFooter}>
                    <Text style={styles.author} numberOfLines={1}>
                      {item.author_name || 'Pamoja'}
                    </Text>
                    <View style={styles.openLink}>
                      <Text style={styles.openText}>Explore</Text>
                      <MaterialIcons name="arrow-forward" size={15} color={homeDesign.primaryGreen} />
                    </View>
                  </View>
                </View>
              </Pressable>
            );
          })}
        </View>
      )}

      {!loading && !error && hasMore ? (
        <Pressable
          accessibilityRole="button"
          onPress={() => void loadPage(page + 1, false)}
          disabled={loadingMore}
          style={styles.loadMore}
        >
          {loadingMore
            ? <ActivityIndicator color={homeDesign.primaryGreen} />
            : <Text style={styles.loadMoreText}>Load more updates</Text>}
        </Pressable>
      ) : null}
      {!!error && items.length > 0 ? (
        <Text style={styles.inlineError}>{error}</Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { marginTop: 9, marginBottom: 24 },
  heading: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 15,
  },
  headingText: { flex: 1 },
  title: {
    color: homeDesign.textDark,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '900',
    letterSpacing: -0.8,
    fontFamily: 'serif',
  },
  subtitle: { color: homeDesign.textGray, fontSize: 12, marginTop: 4 },
  filters: { gap: 8, paddingBottom: 15, paddingRight: 8 },
  filter: {
    borderRadius: 22,
    paddingHorizontal: 15,
    paddingVertical: 9,
    backgroundColor: '#F0EBDD',
    borderWidth: 1,
    borderColor: '#E6DDCA',
  },
  filterSelected: { backgroundColor: homeDesign.primaryGreen, borderColor: homeDesign.primaryGreen },
  filterText: { color: homeDesign.primaryGreen, fontSize: 12, fontWeight: '700' },
  filterTextSelected: { color: '#FFFFFF' },
  list: { gap: 12 },
  card: {
    flexDirection: 'row',
    minHeight: 142,
    padding: 10,
    borderRadius: 20,
    backgroundColor: '#FFFEFA',
    borderWidth: 1,
    borderColor: homeDesign.borderColor,
    shadowColor: '#173D28',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  media: {
    width: 106,
    height: 120,
    borderRadius: 14,
    overflow: 'hidden',
    backgroundColor: homeDesign.primaryGreen,
  },
  image: { width: '100%', height: '100%' },
  imageFallback: {
    flex: 1,
    minHeight: 120,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: homeDesign.primaryGreen,
  },
  cardContent: { flex: 1, paddingLeft: 12, justifyContent: 'center' },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  categoryLabel: { color: '#98751E', fontSize: 9, fontWeight: '900', letterSpacing: 0.7 },
  date: { color: homeDesign.textGray, fontSize: 10 },
  cardTitle: { color: homeDesign.textDark, fontSize: 15, lineHeight: 20, fontWeight: '900' },
  cardBody: { color: homeDesign.textGray, fontSize: 11, lineHeight: 15, marginTop: 4 },
  cardFooter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 },
  author: { color: homeDesign.textGray, fontSize: 10, flex: 1, marginRight: 6 },
  openLink: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  openText: { color: homeDesign.primaryGreen, fontSize: 11, fontWeight: '900' },
  stateBox: {
    minHeight: 125,
    borderRadius: 18,
    backgroundColor: '#FFFEFA',
    borderWidth: 1,
    borderColor: homeDesign.borderColor,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
    gap: 9,
  },
  stateText: { color: homeDesign.textGray, fontSize: 12, lineHeight: 18, textAlign: 'center' },
  retryButton: { backgroundColor: homeDesign.primaryGreen, borderRadius: 18, paddingHorizontal: 18, paddingVertical: 9 },
  retryText: { color: '#FFFFFF', fontSize: 12, fontWeight: '800' },
  loadMore: {
    marginTop: 14,
    minHeight: 43,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: homeDesign.primaryGreen,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F8F3E9',
  },
  loadMoreText: { color: homeDesign.primaryGreen, fontSize: 12, fontWeight: '900' },
  inlineError: { color: '#9A342D', fontSize: 11, marginTop: 8 },
});

export default HomeDiscoveryFeed;
