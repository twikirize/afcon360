import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { getSelectedApiBaseUrl } from '../../src/services/api';
import { useAuth } from '../../src/auth/AuthProvider';
import { userOfflineRepository } from '../../src/offline/repositories';
import { TrendingRail, TrendingSkeleton } from '../../src/components/TrendingRail';
import { SectionHeader } from '../../src/components/SectionHeader';
import { MyEventsOverview } from '../../src/components/MyEventsOverview';
import { GeminiHomeTop } from '../../src/components/GeminiHomeTop';
import type { FeedItem, LoadMode } from '../../src/types/feed';
import { safeSameOriginUrl } from '../../src/utils/feedUtils';
import { colors } from '../../src/theme/tokens';

const SITE = 'https://www.pamoja.space';

export default function UserHome() {
  const router = useRouter();
  const { user, isOffline, lastVerifiedAt, offlineStorageError, retryRestoreSession } = useAuth();
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
  const [cachedFeedAt, setCachedFeedAt] = useState<number | null>(null);
  const requestInFlight = useRef(false);

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

    let cachedEntry = null as Awaited<ReturnType<typeof userOfflineRepository.readHomeFeed>> | null;
    if (nextPage === 1 && user?.public_id) {
      try {
        cachedEntry = await userOfflineRepository.readHomeFeed(user.public_id);
        if (cachedEntry) {
          const saved = cachedEntry.value;
          setFeedItems(Array.isArray(saved.items) ? saved.items : []);
          setPage(typeof saved.page === 'number' ? saved.page : 1);
          setSeed(saved.seed || '');
          setHasMore(false);
          setCachedFeedAt(cachedEntry.storedAt);
          if (mode === 'initial') setLoading(false);
        }
      } catch {
        cachedEntry = null;
      }
    }

    if (isOffline) {
      setHasMore(false);
      setFeedError(cachedEntry
        ? 'Offline mode. Showing your saved Pamoja highlights.'
        : 'Pamoja highlights have not been saved on this device yet. Reconnect to load them.');
      requestInFlight.current = false;
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
      return;
    }

    if (cachedEntry?.isFresh && mode === 'initial') {
      requestInFlight.current = false;
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
      setFeedError(null);
      return;
    }

    try {
      const response = await userOfflineRepository.refreshHomeFeed(
        user?.public_id ?? null,
        nextPage,
        nextSeed
      );
      const incoming = Array.isArray(response.items) ? response.items : [];
      if (response.error) setFeedError(response.error);
      setFeedItems((current) => mode === 'more' ? mergeFeedItems(current, incoming) : incoming);
      setPage(typeof response.page === 'number' ? response.page : nextPage);
      setSeed(response.seed || nextSeed || '');
      setHasMore(Boolean(response.has_more));
      setCachedFeedAt(null);
    } catch (error) {
      if (cachedEntry && nextPage === 1) {
        const saved = cachedEntry.value;
        setFeedItems(Array.isArray(saved.items) ? saved.items : []);
        setPage(typeof saved.page === 'number' ? saved.page : 1);
        setSeed(saved.seed || '');
        setHasMore(false);
        setCachedFeedAt(cachedEntry.storedAt);
        setFeedError('Connection unavailable. Showing your saved Pamoja highlights.');
      } else {
        setFeedError(error instanceof Error ? error.message : 'Pamoja highlights are temporarily unavailable.');
        if (mode !== 'more') setHasMore(false);
      }
    } finally {
      requestInFlight.current = false;
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, [isOffline, mergeFeedItems, user?.public_id]);

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
      case 'adventure':
        router.push('/(service)/adventure' as never);
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

  const handleSearchSubmit = useCallback((text: string) => {
    const term = text.trim();
    if (!term) return;
    setRecentSearches((prev) => prev.includes(term) ? prev : [term, ...prev.slice(0, 4)]);
    openEventSearch(term);
  }, [openEventSearch]);

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
      <ScrollView
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
          {(isOffline || offlineStorageError) ? (
            <View style={styles.offlineNotice}>
              <View style={styles.offlineNoticeCopy}>
                <Text style={styles.offlineNoticeTitle}>
                  {isOffline ? 'Offline mode' : 'Offline cache unavailable'}
                </Text>
                <Text style={styles.offlineNoticeBody}>
                  {cachedFeedAt
                    ? 'Saved highlights from ' + new Date(cachedFeedAt).toLocaleString()
                    : lastVerifiedAt
                      ? 'Account last verified ' + new Date(lastVerifiedAt).toLocaleString()
                      : (offlineStorageError || 'Reconnect to refresh your information.')}
                </Text>
              </View>
              <Pressable onPress={() => void retryRestoreSession()} accessibilityRole='button'>
                <Text style={styles.offlineNoticeAction}>Retry</Text>
              </Pressable>
            </View>
          ) : null}
          <GeminiHomeTop
            search={search}
            onSearchChange={setSearch}
            onSearchSubmit={handleSearchSubmit}
            recentSearches={recentSearches}
            onRecentPress={handleRecentPress}
            onClearRecent={handleClearRecent}
            onServicePress={openService}
            onOpenActivity={() => router.push('/(tabs)/activity' as never)}
            onOpenAccount={() => router.push('/(tabs)/account' as never)}
          />

          <MyEventsOverview
            onOpenEvents={() => openEventSearch()}
            onOpenWebsite={openWebsite}
          />

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
      </ScrollView>
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
  offlineNotice: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: 12, borderRadius: 14, backgroundColor: '#FFF4D5', borderWidth: 1, borderColor: '#F0D99A' },
  offlineNoticeCopy: { flex: 1, gap: 3 },
  offlineNoticeTitle: { color: '#755316', fontSize: 12, fontWeight: '900' },
  offlineNoticeBody: { color: '#755316', fontSize: 11, lineHeight: 15 },
  offlineNoticeAction: { color: '#5B4312', fontSize: 12, fontWeight: '900', padding: 8 },
});
