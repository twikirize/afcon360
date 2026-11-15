import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshControl, StyleSheet, Text, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedScrollHandler,
} from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { authClient, getSelectedApiBaseUrl } from '../../src/services/api';
import { HeroParallax } from '../../src/components/HeroParallax';
import { ServiceGrid } from '../../src/components/ServiceGrid';
import { TrendingRail, TrendingSkeleton } from '../../src/components/TrendingRail';
import { SearchBar } from '../../src/components/SearchBar';
import { SectionHeader } from '../../src/components/SectionHeader';
import { Header } from '../../src/components/Header';
import { MyEventsOverview } from '../../src/components/MyEventsOverview';
import type { FeedItem, FeedResponse, LoadMode } from '../../src/types/feed';
import { safeSameOriginUrl } from '../../src/utils/feedUtils';
import { colors } from '../../src/theme/tokens';

const SITE = 'https://www.pamoja.space';
const PAGE_SIZE = 10;

export default function UserHome() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [apiBaseUrl, setApiBaseUrl] = useState(SITE);
  const [feedItems, setFeedItems] = useState<FeedItem[]>([]);
  const [page, setPage] = useState(1);
  const [seed, setSeed] = useState('');
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [feedError, setFeedError] = useState<string | null>(null);
  const requestInFlight = useRef(false);

  const scrollY = useSharedValue(0);
  const onScroll = useAnimatedScrollHandler({
    onScroll: (event) => {
      scrollY.value = event.contentOffset.y;
    },
  });

  useEffect(() => {
    let mounted = true;
    void getSelectedApiBaseUrl().then((url) => {
      if (mounted) setApiBaseUrl(url);
    }).catch(() => {
      if (mounted) setApiBaseUrl(SITE);
    });
    return () => { mounted = false; };
  }, []);

  const mergeFeedItems = useCallback((existing: FeedItem[], incoming: FeedItem[]): FeedItem[] => {
    const merged = new Map<string, FeedItem>();
    for (const item of existing) merged.set(item.feed_id, item);
    for (const item of incoming) merged.set(item.feed_id, item);
    return Array.from(merged.values());
  }, []);

  const loadFeedPage = useCallback(async (nextPage: number, nextSeed: string | null, mode: LoadMode) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    if (mode === 'initial') setLoading(true);
    if (mode === 'refresh') setRefreshing(true);
    if (mode === 'more') setLoadingMore(true);
    setFeedError(null);

    try {
      const params = new URLSearchParams({
        page: String(nextPage),
        per_page: String(PAGE_SIZE),
        layout: 'mixed',
      });
      if (nextSeed) params.set('seed', nextSeed);
      const response = await authClient.request<FeedResponse>('/api/home/feed?' + params.toString());
      const incoming = Array.isArray(response.items) ? response.items : [];
      if (response.error) setFeedError(response.error);
      setFeedItems((current) => mode === 'more' ? mergeFeedItems(current, incoming) : incoming);
      setPage(typeof response.page === 'number' ? response.page : nextPage);
      setSeed(response.seed || nextSeed || '');
      setHasMore(Boolean(response.has_more));
    } catch (error) {
      setFeedError(error instanceof Error ? error.message : 'Pamoja highlights are temporarily unavailable.');
      if (mode !== 'more') {
        setFeedItems([]);
        setHasMore(false);
      }
    } finally {
      requestInFlight.current = false;
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, [mergeFeedItems]);

  useEffect(() => {
    void loadFeedPage(1, null, 'initial');
  }, [loadFeedPage]);

  // Website handoffs always use Pamoja's canonical public origin. The selected
  // API origin may be a laptop/private test server and must never receive web links.
  const openWebsite = useCallback((path: string) => {
    const target = safeSameOriginUrl(path, SITE);
    if (target) void WebBrowser.openBrowserAsync(target);
  }, []);

  const openEventSearch = useCallback((query = '') => {
    router.push({
      pathname: '/(service)/events',
      params: query ? { query } : {},
    } as never);
  }, [router]);

  const openService = useCallback((service: string) => {
    switch (service) {
      case 'rides':
        router.push('/(service)/ride' as never);
        break;
      case 'stays':
        router.push('/(service)/stays' as never);
        break;
      case 'events':
        openEventSearch();
        break;
      case 'wallet':
        router.push('/(tabs)/wallet' as never);
        break;
      case 'tourism':
        openWebsite('/tourism');
        break;
      default:
        router.push('/(tabs)/explore' as never);
    }
  }, [openEventSearch, openWebsite, router]);

  const openTrendingItem = useCallback((item: FeedItem) => {
    if (item.type === 'event') {
      openEventSearch(item.title || '');
      return;
    }
    if (item.type === 'property') {
      openService('stays');
      return;
    }
    if (item.type === 'transport') {
      openService('rides');
      return;
    }
    if (item.link_url) {
      openWebsite(item.link_url);
      return;
    }
    router.push('/(tabs)/explore' as never);
  }, [openEventSearch, openService, openWebsite, router]);

  const trendingItems = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return feedItems;
    return feedItems.filter((item) => [
      item.title,
      item.body,
      item.author_name,
      item.source_module,
      item.metadata?.module_label,
      item.metadata?.city,
      item.metadata?.country,
    ].some((value) => typeof value === 'string' && value.toLowerCase().includes(term)));
  }, [feedItems, search]);

  const featuredItem = useMemo(() => {
    const pinned = feedItems.find((item) => item.is_pinned);
    if (pinned) return pinned;
    return feedItems.find((item) => item.type === 'ad') ?? null;
  }, [feedItems]);

  const handleSearchSubmit = useCallback((text: string) => {
    const term = text.trim();
    if (term && !recentSearches.includes(term)) {
      setRecentSearches((prev) => [term, ...prev.slice(0, 4)]);
    }
  }, [recentSearches]);

  const handleRecentPress = useCallback((text: string) => {
    setSearch(text);
  }, []);

  const handleClearRecent = useCallback(() => {
    setRecentSearches([]);
  }, []);

  const onRefresh = useCallback(() => {
    setSearch('');
    void loadFeedPage(1, null, 'refresh');
  }, [loadFeedPage]);

  const onLoadMore = useCallback(() => {
    if (!hasMore || loading || loadingMore || !seed) return;
    void loadFeedPage(page + 1, seed, 'more');
  }, [hasMore, loading, loadingMore, loadFeedPage, page, seed]);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <Animated.ScrollView
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.brand.green}
            colors={[colors.brand.green]}
          />
        }
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps='handled'
      >
        <View style={styles.pageContent}>
          <Header />

          <MyEventsOverview
            onOpenEvents={() => openEventSearch()}
            onOpenWebsite={openWebsite}
          />

          <SearchBar
            value={search}
            onChangeText={setSearch}
            onSubmit={handleSearchSubmit}
            placeholder='Search highlights'
            recentSearches={recentSearches}
            onRecentPress={handleRecentPress}
            onClearRecent={handleClearRecent}
          />

          <HeroParallax
            scrollY={scrollY}
            featured={featuredItem}
            baseUrl={apiBaseUrl}
            onFeaturedPress={() => featuredItem && openTrendingItem(featuredItem)}
            onExplore={() => router.push('/(tabs)/explore' as never)}
          />

          <SectionHeader
            title='Explore services'
            subtitle='ALL IN ONE PLACE'
            index={0}
          />

          <ServiceGrid onServicePress={openService} />

          <SectionHeader
            title='Trending'
            subtitle='Highlights, offers & updates'
            index={1}
            live
          />

          {loading && feedItems.length === 0 ? (
            <TrendingSkeleton count={3} />
          ) : feedError && feedItems.length === 0 ? (
            <View style={styles.errorState}>
              <Text style={styles.errorTitle}>Highlights unavailable</Text>
              <Text style={styles.errorBody}>{feedError}</Text>
              <Text
                accessibilityRole='button'
                onPress={() => void loadFeedPage(1, null, 'refresh')}
                style={styles.retryButtonText}
              >
                Try again
              </Text>
            </View>
          ) : (
            <TrendingRail
              data={trendingItems}
              baseUrl={apiBaseUrl}
              onPress={openTrendingItem}
              loadingMore={loadingMore}
              onEndReached={onLoadMore}
              searchActive={Boolean(search.trim())}
            />
          )}

          {feedError && feedItems.length > 0 ? (
            <View style={styles.inlineError}>
              <Text style={styles.inlineErrorText}>{feedError}</Text>
              <Text
                accessibilityRole='button'
                onPress={() => void loadFeedPage(page + 1, seed || null, 'more')}
                style={styles.inlineRetry}
              >
                Retry
              </Text>
            </View>
          ) : null}
        </View>
      </Animated.ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface.canvas },
  scrollContent: { paddingBottom: 28 },
  pageContent: { paddingHorizontal: 16, paddingTop: 8, gap: 20 },
  errorState: { padding: 16, borderRadius: 16, backgroundColor: colors.status.errorBg, gap: 10 },
  errorTitle: { color: colors.status.error, fontSize: 14, fontWeight: '900' },
  errorBody: { color: '#8D4943', fontSize: 12, lineHeight: 17 },
  retryButtonText: {
    alignSelf: 'flex-start',
    backgroundColor: '#A33F37',
    color: colors.surface.white,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 10,
    overflow: 'hidden',
    fontSize: 12,
    fontWeight: '900',
  },
  inlineError: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.status.errorBg,
    padding: 12,
    borderRadius: 12,
  },
  inlineErrorText: { flex: 1, color: colors.status.error, fontSize: 11, fontWeight: '700' },
  inlineRetry: { color: colors.status.error, fontSize: 12, fontWeight: '900', padding: 6 },
});
