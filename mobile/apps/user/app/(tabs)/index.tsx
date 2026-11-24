import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedScrollHandler,
} from "react-native-reanimated";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { getSelectedApiBaseUrl } from "../../src/services/api";
import { userOfflineRepository } from "../../src/offline/repositories";
import { HeroParallax } from "../../src/components/HeroParallax";
import { ServiceGrid } from "../../src/components/ServiceGrid";
import { TrendingRail, TrendingSkeleton } from "../../src/components/TrendingRail";
import { SearchBar } from "../../src/components/SearchBar";
import { SectionHeader } from "../../src/components/SectionHeader";
import { Header } from "../../src/components/Header";
import { useAuth } from "../../src/auth/AuthProvider";
import type { FeedItem, LoadMode, NativeEventRegistration } from "../../src/types/feed";
import { safeSameOriginUrl } from "../../src/utils/feedUtils";
import { colors, spacing, radii, shadows } from "../../src/theme/tokens";

const SITE = "https://www.pamoja.space";
export default function UserHome() {
  const router = useRouter();
  const { user, isOffline, lastVerifiedAt, offlineStorageError, retryRestoreSession } = useAuth();
  const [search, setSearch] = useState("");
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [apiBaseUrl, setApiBaseUrl] = useState(SITE);
  const [feedItems, setFeedItems] = useState<FeedItem[]>([]);
  const [page, setPage] = useState(1);
  const [seed, setSeed] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [feedError, setFeedError] = useState<string | null>(null);
  const [cachedFeedAt, setCachedFeedAt] = useState<number | null>(null);
  const [registrations, setRegistrations] = useState<NativeEventRegistration[]>([]);
  const [registrationsLoading, setRegistrationsLoading] = useState(true);
  const [registrationsError, setRegistrationsError] = useState<string | null>(null);
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


  const loadRegistrations = useCallback(async () => {
    if (!user?.public_id) {
      setRegistrations([]);
      setRegistrationsError("Sign in to view your event registrations.");
      setRegistrationsLoading(false);
      return;
    }

    setRegistrationsLoading(true);
    setRegistrationsError(null);
    let cachedEntry = null as Awaited<ReturnType<typeof userOfflineRepository.readEventRegistrations>> | null;

    try {
      cachedEntry = await userOfflineRepository.readEventRegistrations(user.public_id);
      if (cachedEntry) setRegistrations(cachedEntry.value.items ?? []);
    } catch {
      cachedEntry = null;
    }

    if (isOffline) {
      setRegistrationsError(cachedEntry
        ? null
        : "Event registrations are not available offline on this device yet.");
      setRegistrationsLoading(false);
      return;
    }

    if (cachedEntry?.isFresh) {
      setRegistrationsLoading(false);
      return;
    }

    try {
      const result = await userOfflineRepository.refreshEventRegistrations(user.public_id);
      setRegistrations(result.items ?? []);
      setRegistrationsError(null);
    } catch (error) {
      if (cachedEntry) {
        setRegistrations(cachedEntry.value.items ?? []);
        setRegistrationsError(null);
      } else {
        setRegistrationsError(error instanceof Error
          ? error.message
          : "Your event registrations are temporarily unavailable.");
      }
    } finally {
      setRegistrationsLoading(false);
    }
  }, [isOffline, user?.public_id]);
  useEffect(() => {
    void loadRegistrations();
  }, [loadRegistrations]);

  // Website handoffs must always resolve to Pamoja's public origin.
  // The selected API URL may point to a laptop/private preview server.
  const openWebsite = useCallback((path: string) => {
    const target = safeSameOriginUrl(path, SITE);
    if (target) void WebBrowser.openBrowserAsync(target);
  }, []);

  const openEventSearch = useCallback((query = "") => {
    router.push({
      pathname: '/(service)/events',
      params: query ? { query } : {},
    } as never);
  }, [router]);

  const openService = useCallback((service: string) => {
    switch (service) {
      case "rides":
        router.push('/(service)/ride' as never);
        break;
      case "stays":
        router.push('/(service)/stays' as never);
        break;
      case "events":
        openEventSearch();
        break;
      case "wallet":
        router.push('/(tabs)/wallet' as never);
        break;
      case "tourism":
        openWebsite("/tourism");
        break;
      default:
        router.push('/(tabs)/explore' as never);
    }
  }, [openEventSearch, openWebsite, router]);

  const openTrendingItem = useCallback((item: FeedItem) => {
    if (item.type === "event") {
      openEventSearch(item.title || "");
      return;
    }
    if (item.type === "property") {
      openService("stays");
      return;
    }
    if (item.type === "transport") {
      openService("rides");
      return;
    }
    if (item.type === "adventure" || item.metadata?.module_label?.toLowerCase().includes("tourism") || item.metadata?.module_label?.toLowerCase().includes("adventure")) {
      openWebsite("/tourism");
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
    ].some((value) => typeof value === "string" && value.toLowerCase().includes(term)));
  }, [feedItems, search]);

  const featuredItem = useMemo(() => {
    const pinned = feedItems.find((item) => item.is_pinned);
    if (pinned) return pinned;
    return feedItems.find((item) => item.type === "ad") ?? null;
  }, [feedItems]);

  const upcomingRegistrations = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return registrations
      .filter((reg) => reg.status !== "cancelled" && (reg.event.start_date ?? "9999-12-31").slice(0, 10) >= today)
      .slice()
      .sort((a, b) => (a.event.start_date ?? "").localeCompare(b.event.start_date ?? ""));
  }, [registrations]);

  const pastRegistrations = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return registrations
      .filter((reg) => (reg.event.start_date ?? "").slice(0, 10) < today)
      .slice()
      .sort((a, b) => (b.event.start_date ?? "").localeCompare(a.event.start_date ?? ""));
  }, [registrations]);

  const activeTicketCount = registrations.filter((reg) => {
    const today = new Date().toISOString().slice(0, 10);
    return reg.status !== "cancelled" && (reg.event.start_date ?? "9999-12-31").slice(0, 10) >= today;
  }).length;

  const nextEvent = upcomingRegistrations[0] ?? null;

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
    setSearch("");
    void Promise.all([loadFeedPage(1, null, "refresh"), loadRegistrations()]);
  }, [loadFeedPage, loadRegistrations]);

  const onLoadMore = useCallback(() => {
    if (!hasMore || loading || loadingMore || !seed) return;
    void loadFeedPage(page + 1, seed, "more");
  }, [hasMore, loading, loadingMore, loadFeedPage, page, seed]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
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
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.pageContent}>
          <Header />
          {(isOffline || offlineStorageError) ? (
            <View style={{ backgroundColor: "#E8F4EC", borderRadius: 14, padding: 12, gap: 4 }}>
              <Text style={{ color: colors.brand.dark, fontSize: 12, fontWeight: "900" }}>
                {isOffline ? "Offline mode" : "Offline cache unavailable"}
              </Text>
              <Text style={{ color: colors.text.muted, fontSize: 11, lineHeight: 16 }}>
                {cachedFeedAt
                  ? "Saved highlights from " + new Date(cachedFeedAt).toLocaleString()
                  : lastVerifiedAt
                    ? "Account last verified " + new Date(lastVerifiedAt).toLocaleString()
                    : (offlineStorageError || "Reconnect to refresh your Pamoja information.")}
              </Text>
              <Pressable accessibilityRole="button" onPress={() => void retryRestoreSession()}>
                <Text style={{ color: colors.brand.dark, fontSize: 12, fontWeight: "900" }}>Retry connection</Text>
              </Pressable>
            </View>
          ) : null}

          <HeroParallax
            scrollY={scrollY}
            featured={featuredItem}
            baseUrl={apiBaseUrl}
            onFeaturedPress={() => featuredItem && openTrendingItem(featuredItem)}
            onExplore={() => router.push('/(tabs)/explore' as never)}
          />

          <SearchBar
            value={search}
            onChangeText={setSearch}
            onSubmit={handleSearchSubmit}
            placeholder="Search events, stays, rides and more"
            recentSearches={recentSearches}
            onRecentPress={handleRecentPress}
            onClearRecent={handleClearRecent}
          />

          <SectionHeader
            title="Explore services"
            subtitle="ALL IN ONE PLACE"
            index={0}
          />

          <ServiceGrid onServicePress={openService} />

          {user && (
            <>
              <SectionHeader
                title="My Events"
                subtitle={registrations.length > 0 ? `${registrations.length} registration${registrations.length !== 1 ? "s" : ""}` : "No registrations yet"}
                index={1}
              />

              <MyEventsSection
                registrations={registrations}
                loading={registrationsLoading}
                error={registrationsError}
                onRefresh={loadRegistrations}
                onBrowseEvents={() => openService("events")}
              />
            </>
          )}

          <SectionHeader
            title="Trending"
            subtitle="Highlights, offers & updates"
            index={user ? 2 : 1}
            live
          />

          {loading && feedItems.length === 0 ? (
            <TrendingSkeleton count={3} />
          ) : feedError && feedItems.length === 0 ? (
            <View style={styles.errorState}>
              <Text style={styles.errorTitle}>Highlights unavailable</Text>
              <Text style={styles.errorBody}>{feedError}</Text>
              <Text
                accessibilityRole="button"
                onPress={() => void loadFeedPage(1, null, "refresh")}
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
                accessibilityRole="button"
                onPress={() => void loadFeedPage(page + 1, seed || null, "more")}
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

const MyEventsSection = ({
  registrations,
  loading,
  error,
  onRefresh,
  onBrowseEvents,
}: {
  registrations: NativeEventRegistration[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onBrowseEvents: () => void;
  
}) => {
  if (loading) {
    return (
      <View style={styles.myEventsSkeleton}>
        <View style={styles.skeletonCard} />
        <View style={styles.skeletonCard} />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.errorCard}>
        <Text style={styles.errorCardTitle}>Unable to load your events</Text>
        <Text style={styles.errorCardText}>{error}</Text>
        <Text accessibilityRole="button" onPress={onRefresh} style={styles.retryText}>
          Try again
        </Text>
      </View>
    );
  }

  if (registrations.length === 0) {
    return (
      <View style={styles.emptyCard}>
        <Text style={styles.emptyIcon}>📅</Text>
        <Text style={styles.emptyTitle}>No event registrations yet</Text>
        <Text style={styles.emptyText}>When you register for an event, your tickets will appear here.</Text>
        <Text accessibilityRole="button" onPress={onBrowseEvents} style={styles.browseButton}>
          Discover events
        </Text>
      </View>
    );
  }

  const upcoming = registrations
    .filter((reg) => reg.status !== "cancelled" && (reg.event.start_date ?? "9999-12-31").slice(0, 10) >= new Date().toISOString().slice(0, 10))
    .slice()
    .sort((a, b) => (a.event.start_date ?? "").localeCompare(b.event.start_date ?? ""))
    .slice(0, 3);

  const past = registrations
    .filter((reg) => (reg.event.start_date ?? "").slice(0, 10) < new Date().toISOString().slice(0, 10))
    .slice(0, 2);

  return (
    <View style={styles.myEventsContainer}>
      {upcoming.length > 0 && (
        <View style={styles.myEventsGroup}>
          <View style={styles.groupHeader}>
            <Text style={styles.groupTitle}>Upcoming</Text>
            <Text style={styles.groupCount}>{upcoming.length} event{upcoming.length !== 1 ? "s" : ""}</Text>
          </View>
          {upcoming.map((reg) => (
            <MyEventCard key={reg.registration_reference} registration={reg} onPress={onBrowseEvents} />
          ))}
        </View>
      )}

      {past.length > 0 && (
        <View style={[styles.myEventsGroup, { marginTop: spacing.lg }]}>
          <View style={styles.groupHeader}>
            <Text style={styles.groupTitle}>Past</Text>
            <Text style={styles.groupCount}>{past.length} event{past.length !== 1 ? "s" : ""}</Text>
          </View>
          {past.map((reg) => (
            <MyEventCard key={reg.registration_reference} registration={reg} onPress={onBrowseEvents} past />
          ))}
        </View>
      )}

      <View style={styles.myEventsFooter}>
        <Text accessibilityRole="button" onPress={onBrowseEvents} style={styles.browseAllButton}>
          View all my events →
        </Text>
      </View>
    </View>
  );
};

const MyEventCard = ({
  registration,
  onPress,
  past = false,
}: {
  registration: NativeEventRegistration;
  onPress: () => void;
  past?: boolean;
}) => {
  const eventDate = registration.event.start_date ? new Date(registration.event.start_date) : null;
  const dateStr = eventDate ? eventDate.toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "TBA";
  const monthStr = eventDate ? eventDate.toLocaleDateString(undefined, { month: "short" }).toUpperCase() : "";
  const dayStr = eventDate ? eventDate.getDate().toString().padStart(2, "0") : "";
  const location = [registration.event.city, registration.event.country].filter(Boolean).join(", ") || "Location TBA";

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`View ${registration.event.name ?? "event"} registration`}
      onPress={onPress}
      style={({ pressed }: { pressed: boolean }) => [styles.eventCard, pressed && styles.eventCardPressed, past && styles.eventCardPast]}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <View style={styles.eventCardDate}>
        <Text style={styles.eventCardMonth}>{monthStr}</Text>
        <Text style={styles.eventCardDay}>{dayStr}</Text>
      </View>
      <View style={styles.eventCardContent}>
        <View style={styles.eventCardHeader}>
          <Text style={[styles.eventCardName, past && styles.eventCardNamePast]}>{registration.event.name ?? "Event"}</Text>
          {past && <Text style={styles.pastBadge}>Past</Text>}
        </View>
        <Text style={styles.eventCardLocation}>📍 {location}</Text>
        <Text style={styles.eventCardDateStr}>📅 {dateStr}</Text>
        <Text style={styles.eventCardTicket}>{registration.ticket_type} · {registration.registration_reference}</Text>
        <View style={styles.eventCardStatus}>
          <Text style={[styles.statusBadge, past && styles.statusBadgePast]}>{registration.status}</Text>
        </View>
      </View>
      <Text style={styles.chevron}>›</Text>
    </Pressable>
  );
};

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface.canvas },
  scrollContent: { paddingBottom: 28 },
  pageContent: { paddingHorizontal: 18, paddingTop: 10, gap: 22 },
  errorState: { padding: 16, borderRadius: radii.lg, backgroundColor: colors.status.errorBg, gap: 10 },
  errorTitle: { color: colors.status.error, fontSize: 14, fontWeight: "900" },
  errorBody: { color: "#8D4943", fontSize: 12, lineHeight: 17 },
  retryButtonText: {
    alignSelf: "flex-start",
    backgroundColor: "#A33F37",
    color: colors.surface.white,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 10,
    overflow: "hidden",
    fontSize: 12,
    fontWeight: "900",
  },
  inlineError: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.status.errorBg,
    padding: 12,
    borderRadius: 12,
  },
  inlineErrorText: { flex: 1, color: colors.status.error, fontSize: 11, fontWeight: "700" },
  inlineRetry: { color: colors.status.error, fontSize: 12, fontWeight: "900", padding: 6 },

  // MyEventsSection
  myEventsSkeleton: { gap: 12 },
  skeletonCard: {
    height: 110,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.canvas,
  },
  errorCard: {
    padding: spacing.lg,
    borderRadius: radii.lg,
    backgroundColor: colors.status.errorBg,
    gap: 10,
    alignItems: "center",
  },
  errorCardTitle: { color: colors.status.error, fontSize: 14, fontWeight: "900" },
  errorCardText: { color: "#8D4943", fontSize: 12, lineHeight: 17, textAlign: "center" },
  retryText: {
    color: colors.brand.green,
    fontSize: 12,
    fontWeight: "900",
  },
  emptyCard: {
    padding: spacing.xl,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.canvas,
    gap: 10,
    alignItems: "center",
  },
  emptyIcon: { fontSize: 36 },
  emptyTitle: { color: colors.text.ink, fontSize: 16, fontWeight: "900" },
  emptyText: { color: colors.text.muted, fontSize: 12, lineHeight: 17, textAlign: "center" },
  browseButton: {
    color: colors.brand.green,
    fontSize: 12,
    fontWeight: "900",
    marginTop: spacing.sm,
  },

  myEventsContainer: { gap: 16 },
  myEventsGroup: { gap: 10 },
  groupHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  groupTitle: { color: colors.text.ink, fontSize: 14, fontWeight: "900" },
  groupCount: { color: colors.text.muted, fontSize: 12 },

  eventCard: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    backgroundColor: colors.surface.white,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.md,
    ...shadows.card,
  },
  eventCardPressed: { opacity: 0.85 },
  eventCardPast: { opacity: 0.7, backgroundColor: colors.surface.canvas },
  eventCardDate: {
    width: 56,
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
    paddingVertical: spacing.xs,
    borderRightWidth: 1,
    borderRightColor: colors.border,
  },
  eventCardMonth: { color: colors.brand.green, fontSize: 10, fontWeight: "900", letterSpacing: 0.5 },
  eventCardDay: { color: colors.text.ink, fontSize: 24, fontWeight: "900", lineHeight: 28 },
  eventCardContent: { flex: 1, gap: 4 },
  eventCardHeader: { flexDirection: "row", alignItems: "center", gap: 8 },
  eventCardName: { color: colors.text.ink, fontSize: 13, fontWeight: "800", flex: 1 },
  eventCardNamePast: { color: colors.text.muted, textDecorationLine: "line-through" },
  pastBadge: {
    fontSize: 8,
    fontWeight: "900",
    color: colors.text.muted,
    backgroundColor: colors.border,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  eventCardLocation: { color: colors.text.muted, fontSize: 11 },
  eventCardDateStr: { color: colors.text.muted, fontSize: 11 },
  eventCardTicket: { color: colors.text.muted, fontSize: 10, fontWeight: "700" },
  eventCardStatus: { marginTop: 4 },
  statusBadge: {
    fontSize: 9,
    fontWeight: "900",
    color: colors.brand.green,
    backgroundColor: "#E4F3E8",
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
  },
  statusBadgePast: { color: colors.text.muted, backgroundColor: colors.border },
  chevron: { color: colors.text.muted, fontSize: 20, fontWeight: "700" },

  myEventsFooter: { marginTop: spacing.sm, alignItems: "flex-start" },
  browseAllButton: {
    color: colors.brand.green,
    fontSize: 12,
    fontWeight: "900",
  },
});