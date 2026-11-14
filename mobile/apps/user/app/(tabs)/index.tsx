import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useAuth } from "../../src/auth/AuthProvider";
import { authClient, getSelectedApiBaseUrl } from "../../src/services/api";

const SITE = "https://www.pamoja.space";
const PAGE_SIZE = 10;
const BRAND_DARK = "#173D28";
const BRAND_GREEN = "#28633C";
const BRAND_GOLD = "#FFCC00";
const INK = "#17261D";
const MUTED = "#6D7B73";
const BORDER = "#E2E9E3";
const CANVAS = "#F4F7F4";
const WHITE = "#FFFFFF";

type FeedMetadata = {
  city?: string | null;
  country?: string | null;
  property_type?: string | null;
  price_per_night?: string | number | null;
  route_type?: string | null;
  primary_zone?: string | null;
  module_label?: string | null;
  [key: string]: unknown;
};

type FeedItem = {
  feed_id: string;
  type: "post" | "event" | "ad" | "system_update" | "property" | "transport" | string;
  title?: string | null;
  body?: string | null;
  image_url?: string | null;
  link_url?: string | null;
  author_name?: string | null;
  source_module?: string | null;
  metadata?: FeedMetadata | null;
  created_at?: string | null;
  is_pinned?: boolean;
};

type FeedResponse = {
  items?: FeedItem[];
  page?: number;
  per_page?: number;
  has_more?: boolean;
  seed?: string;
  error?: string;
};

type LoadMode = "initial" | "refresh" | "more";

function safeSameOriginUrl(path: string | null | undefined, baseUrl: string): string | null {
  if (!path || !baseUrl) return null;
  try {
    const base = new URL(baseUrl);
    const target = new URL(path, base.origin + "/");
    if (target.origin !== base.origin) return null;
    if (target.protocol !== "https:" && target.protocol !== "http:") return null;
    return target.toString();
  } catch {
    return null;
  }
}

function imageUri(path: string | null | undefined, baseUrl: string): string | null {
  if (!path) return null;
  try {
    const base = new URL(baseUrl);
    const target = new URL(path, base.origin + "/");
    if (target.protocol === "https:" && target.hostname) return target.toString();
    const host = target.hostname;
    const privatePreviewHost =
      host === "localhost" ||
      host === "127.0.0.1" ||
      /^10\./.test(host) ||
      /^192\.168\./.test(host) ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(host);
    if (target.protocol === "http:" && privatePreviewHost && target.origin === base.origin) {
      return target.toString();
    }
    return null;
  } catch {
    return null;
  }
}

function mergeFeedItems(existing: FeedItem[], incoming: FeedItem[]): FeedItem[] {
  const merged = new Map<string, FeedItem>();
  for (const item of existing) merged.set(item.feed_id, item);
  for (const item of incoming) merged.set(item.feed_id, item);
  return Array.from(merged.values());
}

function feedTypeLabel(type: string): string {
  switch (type) {
    case "event": return "EVENT";
    case "property": return "STAY";
    case "transport": return "MOBILITY";
    case "ad": return "SPONSORED";
    case "system_update": return "UPDATE";
    case "post": return "COMMUNITY";
    default: return "PAMOJA";
  }
}

function feedTypeIcon(type: string): string {
  switch (type) {
    case "event": return "🏟️";
    case "property": return "🏨";
    case "transport": return "🚘";
    case "ad": return "✨";
    case "system_update": return "🔔";
    case "post": return "💬";
    default: return "🌍";
  }
}

function feedMeta(item: FeedItem): string | null {
  const metadata = item.metadata;
  if (!metadata) return null;

  if (item.type === "property") {
    return [metadata.property_type, metadata.city, metadata.country]
      .filter((value): value is string => typeof value === "string" && value.length > 0)
      .join(" · ") || null;
  }
  if (item.type === "transport") {
    return [metadata.route_type, metadata.primary_zone]
      .filter((value): value is string => typeof value === "string" && value.length > 0)
      .join(" · ") || null;
  }
  if (item.type === "event") {
    return [metadata.city, metadata.country]
      .filter((value): value is string => typeof value === "string" && value.length > 0)
      .join(", ") || null;
  }
  if (item.type === "system_update" && typeof metadata.module_label === "string") {
    return metadata.module_label;
  }
  return null;
}

function TrendCard({
  item,
  baseUrl,
  onPress,
}: {
  item: FeedItem;
  baseUrl: string;
  onPress: () => void;
  websiteHandoff: boolean;
}) {
  const image = imageUri(item.image_url, baseUrl);
  const meta = feedMeta(item);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={"Open " + (item.title || feedTypeLabel(item.type).toLowerCase()) + " on Pamoja"}
      onPress={onPress}
      style={({ pressed }) => [styles.trendCard, pressed && styles.cardPressed]}
    >
      <View style={styles.trendVisual}>
        {image ? (
          <Image source={{ uri: image }} style={styles.trendImage} resizeMode="cover" />
        ) : (
          <View style={styles.trendFallback}>
            <Text style={styles.trendFallbackIcon}>{feedTypeIcon(item.type)}</Text>
          </View>
        )}
        {item.is_pinned ? <View style={styles.pinnedMark}><Text style={styles.pinnedMarkText}>PINNED</Text></View> : null}
      </View>
      <View style={styles.trendCopy}>
        <View style={styles.trendTagRow}>
          <Text style={styles.trendTag}>{feedTypeLabel(item.type)}</Text>
          {item.type === "ad" ? <Text style={styles.sponsoredMark}>AD</Text> : null}
          {websiteHandoff ? <Text style={styles.websiteMark}>WEB ↗</Text> : null}
        </View>
        <Text numberOfLines={2} style={styles.trendTitle}>{item.title || "Discover more on Pamoja"}</Text>
        {meta ? <Text numberOfLines={1} style={styles.trendMeta}>{meta}</Text> : null}
        {item.body ? <Text numberOfLines={2} style={styles.trendBody}>{item.body}</Text> : null}
      </View>
      <Text style={styles.trendArrow}>›</Text>
    </Pressable>
  );
}

export default function UserHome() {
  const router = useRouter();
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [apiBaseUrl, setApiBaseUrl] = useState(SITE);
  const [feedItems, setFeedItems] = useState<FeedItem[]>([]);
  const [page, setPage] = useState(1);
  const [seed, setSeed] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [feedError, setFeedError] = useState<string | null>(null);
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

  const loadFeedPage = useCallback(async (nextPage: number, nextSeed: string | null, mode: LoadMode) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    if (mode === "initial") setLoading(true);
    if (mode === "refresh") setRefreshing(true);
    if (mode === "more") setLoadingMore(true);
    setFeedError(null);

    try {
      const params = new URLSearchParams({
        page: String(nextPage),
        per_page: String(PAGE_SIZE),
        layout: "mixed",
      });
      if (nextSeed) params.set("seed", nextSeed);
      const response = await authClient.request<FeedResponse>("/api/home/feed?" + params.toString());
      const incoming = Array.isArray(response.items) ? response.items : [];
      if (response.error) setFeedError(response.error);
      setFeedItems((current) => mode === "more" ? mergeFeedItems(current, incoming) : incoming);
      setPage(typeof response.page === "number" ? response.page : nextPage);
      setSeed(response.seed || nextSeed || "");
      setHasMore(Boolean(response.has_more));
    } catch (error) {
      setFeedError(error instanceof Error ? error.message : "Pamoja highlights are temporarily unavailable.");
      if (mode !== "more") {
        setFeedItems([]);
        setHasMore(false);
      }
    } finally {
      requestInFlight.current = false;
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    void loadFeedPage(1, null, "initial");
  }, [loadFeedPage]);

  const openWebsite = useCallback((path: string) => {
    const target = safeSameOriginUrl(path, apiBaseUrl);
    if (target) void WebBrowser.openBrowserAsync(target);
  }, [apiBaseUrl]);

  const openEventSearch = useCallback((query = "") => {
    router.push({
      pathname: "/(service)/events",
      params: query ? { query } : {},
    } as never);
  }, [router]);

  const openService = useCallback((service: string) => {
    switch (service) {
      case "rides":
        router.push("/(service)/ride" as never);
        break;
      case "stays":
        router.push("/(service)/stays" as never);
        break;
      case "events":
        openEventSearch();
        break;
      case "wallet":
        router.push("/(tabs)/wallet" as never);
        break;
      case "tourism":
        openWebsite("/tourism");
        break;
      default:
        router.push("/(tabs)/explore" as never);
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
    if (item.link_url) {
      openWebsite(item.link_url);
      return;
    }
    router.push("/(tabs)/explore" as never);
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

  const profileName = user?.display_name || user?.username || "Pamoja user";
  const profileInitials = profileName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join("")
    .toUpperCase() || "P";

  const onRefresh = useCallback(() => {
    setSearch("");
    void loadFeedPage(1, null, "refresh");
  }, [loadFeedPage]);

  const onLoadMore = useCallback(() => {
    if (!hasMore || loading || loadingMore || !seed) return;
    void loadFeedPage(page + 1, seed, "more");
  }, [hasMore, loading, loadingMore, loadFeedPage, page, seed]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={BRAND_GREEN}
            colors={[BRAND_GREEN]}
          />
        }
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.pageContent}>
          <View style={styles.header}>
            <View style={styles.brandLockup}>
              <View style={styles.brandMark}><Text style={styles.brandMarkText}>P</Text></View>
              <View style={styles.brandCopy}>
                <Text style={styles.brandName}>Pamoja</Text>
                <Text style={styles.brandRegion}>EAST AFRICA & BEYOND</Text>
              </View>
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Open Account"
              onPress={() => router.push("/(tabs)/account" as never)}
              style={({ pressed }) => [styles.profileButton, pressed && styles.cardPressed]}
            >
              <Text style={styles.profileInitials}>{profileInitials}</Text>
            </Pressable>
          </View>

          <View style={styles.searchPanel}>
            <Text style={styles.searchIcon}>⌕</Text>
            <TextInput
              value={search}
              onChangeText={setSearch}
              placeholder="Search highlights"
              placeholderTextColor="#87938C"
              returnKeyType="search"
              autoCorrect={false}
              style={styles.searchInput}
              accessibilityLabel="Search Pamoja highlights"
              accessibilityHint="Filters the currently loaded trending highlights."
            />
            {search.length > 0 ? (
              <Pressable accessibilityRole="button" accessibilityLabel="Clear search" onPress={() => setSearch("")} hitSlop={8}>
                <Text style={styles.clearSearch}>×</Text>
              </Pressable>
            ) : null}
          </View>

          <View style={styles.hero}>
            <View style={styles.heroOrbLarge} />
            <View style={styles.heroOrbSmall} />
            <View style={styles.heroArtwork}>
              <Text style={styles.heroArtworkNumber}>27</Text>
              <Text style={styles.heroArtworkLabel}>AFCON</Text>
            </View>
            <View style={styles.heroCopy}>
              <View style={styles.heroEyebrowPill}>
                <View style={styles.heroEyebrowDot} />
                <Text style={styles.heroEyebrow}>AFCON 2027 · EAST AFRICA</Text>
              </View>
              <Text style={styles.heroTitle}>Your Africa.{"\n"}Your journey.</Text>
              <Text style={styles.heroSubtitle}>Discover more, move freely and experience it together with Pamoja.</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Explore Pamoja services"
                onPress={() => router.push("/(tabs)/explore" as never)}
                style={({ pressed }) => [styles.heroButton, pressed && styles.heroButtonPressed]}
              >
                <Text style={styles.heroButtonText}>Explore Pamoja</Text>
                <Text style={styles.heroButtonArrow}>›</Text>
              </Pressable>
            </View>
          </View>

          <View style={styles.sectionHeading}>
            <Text accessibilityRole="header" style={styles.sectionTitle}>Explore services</Text>
            <Text style={styles.sectionHint}>ALL IN ONE PLACE</Text>
          </View>

          <View style={styles.serviceGrid}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Events and tickets"
              onPress={() => openService("events")}
              style={({ pressed }) => [styles.serviceTile, styles.eventsTile, pressed && styles.cardPressed]}
            >
              <View style={[styles.serviceIcon, styles.eventsIcon]}><Text style={styles.serviceEmoji}>🏟️</Text></View>
              <Text style={styles.serviceTitle}>Events & Tickets</Text>
              <Text style={styles.serviceHint}>Discover · Register</Text>
            </Pressable>

            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Stays"
              onPress={() => openService("stays")}
              style={({ pressed }) => [styles.serviceTile, styles.staysTile, pressed && styles.cardPressed]}
            >
              <View style={[styles.serviceIcon, styles.staysIcon]}><Text style={styles.serviceEmoji}>🏨</Text></View>
              <Text style={styles.serviceTitle}>Stays</Text>
              <Text style={styles.serviceHint}>Find a place</Text>
            </Pressable>

            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Mobility"
              onPress={() => openService("rides")}
              style={({ pressed }) => [styles.serviceTile, styles.mobilityTile, pressed && styles.cardPressed]}
            >
              <View style={[styles.serviceIcon, styles.mobilityIcon]}><Text style={styles.serviceEmoji}>🚘</Text></View>
              <Text style={styles.serviceTitle}>Mobility</Text>
              <Text style={styles.serviceHint}>Move with ease</Text>
            </Pressable>

            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Tourism · website"
              onPress={() => openService("tourism")}
              style={({ pressed }) => [styles.serviceTile, styles.tourismTile, pressed && styles.cardPressed]}
            >
              <View style={[styles.serviceIcon, styles.tourismIcon]}><Text style={styles.serviceEmoji}>🌍</Text></View>
              <Text style={styles.serviceTitle}>Tourism</Text>
              <View style={styles.websiteHint}>
                <Text style={styles.websiteHintText}>WEBSITE ↗</Text>
              </View>
            </Pressable>
          </View>

          <View style={styles.trendingHeader}>
            <View>
              <Text accessibilityRole="header" style={styles.sectionTitle}>Trending</Text>
              <Text style={styles.trendingSubtitle}>Highlights, offers & updates</Text>
            </View>
            <View style={styles.trendingPulse}><View style={styles.trendingPulseDot} /><Text style={styles.trendingPulseText}>LIVE</Text></View>
          </View>

          {loading && feedItems.length === 0 ? (
            <View style={styles.feedState}>
              <ActivityIndicator color={BRAND_GREEN} />
              <Text style={styles.feedStateText}>Loading Pamoja highlights…</Text>
            </View>
          ) : feedError && feedItems.length === 0 ? (
            <View style={styles.errorState}>
              <Text style={styles.errorTitle}>Highlights unavailable</Text>
              <Text style={styles.errorBody}>{feedError}</Text>
              <Pressable accessibilityRole="button" onPress={() => void loadFeedPage(1, null, "refresh")} style={styles.retryButton}>
                <Text style={styles.retryButtonText}>Try again</Text>
              </Pressable>
            </View>
          ) : trendingItems.length > 0 ? (
            <FlatList
              horizontal
              data={trendingItems}
              keyExtractor={(item) => item.feed_id}
              renderItem={({ item }) => (
                <TrendCard
                  item={item}
                  baseUrl={apiBaseUrl}
                  onPress={() => openTrendingItem(item)}
                  websiteHandoff={Boolean(item.link_url) && !["event", "property", "transport"].includes(item.type)}
                />
              )}
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.trendRail}
              onEndReached={onLoadMore}
              onEndReachedThreshold={0.6}
              ListFooterComponent={loadingMore ? <View style={styles.moreLoading}><ActivityIndicator color={BRAND_GREEN} /></View> : null}
            />
          ) : (
            <View style={styles.emptyState}>
              <Text style={styles.emptyStateIcon}>{search ? "⌕" : "✨"}</Text>
              <Text style={styles.emptyStateTitle}>{search ? "No matching highlights" : "Fresh highlights are on the way"}</Text>
              <Text style={styles.emptyStateBody}>
                {search ? "Try another word or clear your search." : "New events, stays, mobility offers and Pamoja updates will appear here."}
              </Text>
            </View>
          )}
          {feedError && feedItems.length > 0 ? (
            <View style={styles.inlineError}>
              <Text style={styles.inlineErrorText}>{feedError}</Text>
              <Pressable accessibilityRole="button" onPress={() => void loadFeedPage(page + 1, seed || null, "more")}>
                <Text style={styles.inlineRetry}>Retry</Text>
              </Pressable>
            </View>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: CANVAS },
  scrollContent: { paddingBottom: 24 },
  pageContent: { paddingHorizontal: 16, paddingTop: 8, gap: 17 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  brandLockup: { flexDirection: "row", alignItems: "center", gap: 10 },
  brandMark: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: BRAND_DARK },
  brandMarkText: { color: BRAND_GOLD, fontSize: 25, lineHeight: 30, fontWeight: "900" },
  brandCopy: { gap: 2 },
  brandName: { color: BRAND_DARK, fontSize: 21, lineHeight: 24, fontWeight: "900", letterSpacing: -0.6 },
  brandRegion: { color: MUTED, fontSize: 8, fontWeight: "900", letterSpacing: 1.1 },
  profileButton: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center", backgroundColor: "#E4EEE5", borderWidth: 1, borderColor: "#D2E1D4" },
  profileInitials: { color: BRAND_DARK, fontSize: 13, fontWeight: "900" },
  searchPanel: { minHeight: 46, flexDirection: "row", alignItems: "center", gap: 9, paddingHorizontal: 13, borderRadius: 14, backgroundColor: WHITE, borderWidth: 1, borderColor: BORDER },
  searchIcon: { color: BRAND_GREEN, fontSize: 24, lineHeight: 28, fontWeight: "700" },
  searchInput: { flex: 1, minHeight: 44, color: INK, fontSize: 13, paddingVertical: 0 },
  clearSearch: { color: MUTED, fontSize: 22, lineHeight: 26, paddingHorizontal: 3 },
  hero: { minHeight: 204, borderRadius: 22, padding: 17, overflow: "hidden", backgroundColor: BRAND_DARK, flexDirection: "row", alignItems: "center" },
  heroOrbLarge: { position: "absolute", width: 240, height: 240, borderRadius: 120, backgroundColor: "rgba(119,164,101,0.15)", right: -118, top: -126 },
  heroOrbSmall: { position: "absolute", width: 150, height: 150, borderRadius: 75, borderWidth: 1, borderColor: "rgba(255,204,0,0.24)", right: -25, bottom: -72 },
  heroCopy: { flex: 1, maxWidth: "62%", gap: 8, zIndex: 1 },
  heroEyebrowPill: { alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 9, paddingVertical: 6, borderRadius: 99, backgroundColor: "rgba(255,255,255,0.10)", borderWidth: 1, borderColor: "rgba(255,255,255,0.18)" },
  heroEyebrowDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: BRAND_GOLD },
  heroEyebrow: { color: "rgba(255,255,255,0.86)", fontSize: 8, fontWeight: "900", letterSpacing: 0.8 },
  heroTitle: { color: WHITE, fontSize: 27, lineHeight: 31, fontWeight: "900", letterSpacing: -0.7 },
  heroSubtitle: { maxWidth: 230, color: "rgba(255,255,255,0.78)", fontSize: 11, lineHeight: 16 },
  heroButton: { alignSelf: "flex-start", minHeight: 36, marginTop: 2, paddingHorizontal: 12, borderRadius: 10, backgroundColor: BRAND_GOLD, flexDirection: "row", alignItems: "center", gap: 8 },
  heroButtonPressed: { opacity: 0.82 },
  heroButtonText: { color: BRAND_DARK, fontSize: 10, fontWeight: "900" },
  heroButtonArrow: { color: BRAND_DARK, fontSize: 18, lineHeight: 20, fontWeight: "800" },
  heroArtwork: { position: "absolute", right: 12, top: 42, width: 96, height: 112, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,204,0,0.10)", borderWidth: 1, borderColor: "rgba(255,204,0,0.22)", transform: [{ rotate: "7deg" }] },
  heroArtworkNumber: { color: BRAND_GOLD, fontSize: 50, lineHeight: 56, fontWeight: "900", letterSpacing: -3 },
  heroArtworkLabel: { color: WHITE, fontSize: 12, fontWeight: "900", letterSpacing: 2 },
  sectionHeading: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  sectionTitle: { color: INK, fontSize: 16, lineHeight: 20, fontWeight: "900", letterSpacing: -0.2 },
  sectionHint: { color: MUTED, fontSize: 8, fontWeight: "900", letterSpacing: 0.9 },
  serviceGrid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", rowGap: 10 },
  serviceTile: { width: "48.6%", minHeight: 116, borderRadius: 17, padding: 13, borderWidth: 1, borderColor: BORDER, gap: 5 },
  eventsTile: { backgroundColor: "#FFF8E6", borderColor: "#F0E3BD" },
  staysTile: { backgroundColor: "#EAF3EB", borderColor: "#D6E5D8" },
  mobilityTile: { backgroundColor: "#EAF0FA", borderColor: "#D9E3F3" },
  tourismTile: { backgroundColor: "#F0F3E5", borderColor: "#E0E7C9" },
  serviceIcon: { width: 39, height: 39, borderRadius: 13, alignItems: "center", justifyContent: "center", marginBottom: 2 },
  eventsIcon: { backgroundColor: "#FCE9B5" },
  staysIcon: { backgroundColor: "#D7E8D9" },
  mobilityIcon: { backgroundColor: "#D8E4F6" },
  tourismIcon: { backgroundColor: "#E1E9C9" },
  serviceEmoji: { fontSize: 21 },
  serviceTitle: { color: BRAND_DARK, fontSize: 12, lineHeight: 16, fontWeight: "900" },
  serviceHint: { color: MUTED, fontSize: 9, lineHeight: 12, fontWeight: "600" },
  websiteHint: { alignSelf: "flex-start", marginTop: 1, paddingHorizontal: 6, paddingVertical: 3, borderRadius: 6, backgroundColor: "rgba(23,61,40,0.08)" },
  websiteHintText: { color: BRAND_GREEN, fontSize: 7, fontWeight: "900", letterSpacing: 0.5 },
  trendingHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  trendingSubtitle: { color: MUTED, fontSize: 10, lineHeight: 14, marginTop: 2 },
  trendingPulse: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 99, backgroundColor: "#E8F3EA" },
  trendingPulseDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: "#29965B" },
  trendingPulseText: { color: BRAND_GREEN, fontSize: 8, fontWeight: "900", letterSpacing: 0.6 },
  trendRail: { gap: 10, paddingRight: 4 },
  trendCard: { width: 286, minHeight: 118, flexDirection: "row", alignItems: "center", gap: 11, padding: 10, borderRadius: 16, backgroundColor: WHITE, borderWidth: 1, borderColor: BORDER },
  cardPressed: { opacity: 0.82, transform: [{ scale: 0.985 }] },
  trendVisual: { width: 92, height: 94, borderRadius: 12, overflow: "hidden", backgroundColor: "#E9F0E9" },
  trendImage: { width: "100%", height: "100%" },
  trendFallback: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#E8F0E8" },
  trendFallbackIcon: { fontSize: 30 },
  pinnedMark: { position: "absolute", left: 5, top: 5, backgroundColor: BRAND_GOLD, borderRadius: 5, paddingHorizontal: 5, paddingVertical: 3 },
  pinnedMarkText: { color: BRAND_DARK, fontSize: 6, fontWeight: "900" },
  trendCopy: { flex: 1, justifyContent: "center", gap: 4 },
  trendTagRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  trendTag: { color: BRAND_GREEN, fontSize: 7, fontWeight: "900", letterSpacing: 0.7 },
  sponsoredMark: { color: "#815E12", backgroundColor: "#FFF1C8", fontSize: 6, fontWeight: "900", paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, overflow: "hidden" },
  websiteMark: { color: BRAND_GREEN, backgroundColor: "#E8F3EA", fontSize: 6, fontWeight: "900", paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, overflow: "hidden" },
  trendTitle: { color: INK, fontSize: 11, lineHeight: 15, fontWeight: "900" },
  trendMeta: { color: MUTED, fontSize: 8, lineHeight: 11 },
  trendBody: { color: "#68766D", fontSize: 8, lineHeight: 11 },
  trendArrow: { color: BRAND_GREEN, fontSize: 22, fontWeight: "700", marginLeft: 0 },
  feedState: { minHeight: 96, alignItems: "center", justifyContent: "center", gap: 8, padding: 16, borderRadius: 15, backgroundColor: WHITE, borderWidth: 1, borderColor: BORDER },
  feedStateText: { color: MUTED, fontSize: 10, fontWeight: "600" },
  emptyState: { minHeight: 106, alignItems: "center", justifyContent: "center", padding: 16, borderRadius: 15, backgroundColor: WHITE, borderWidth: 1, borderColor: BORDER, gap: 5 },
  emptyStateIcon: { color: BRAND_GREEN, fontSize: 20 },
  emptyStateTitle: { color: INK, fontSize: 11, fontWeight: "900", textAlign: "center" },
  emptyStateBody: { color: MUTED, fontSize: 9, lineHeight: 14, textAlign: "center" },
  errorState: { padding: 14, borderRadius: 14, backgroundColor: "#FFF0EE", gap: 7 },
  errorTitle: { color: "#9A342D", fontSize: 12, fontWeight: "900" },
  errorBody: { color: "#8D4943", fontSize: 10, lineHeight: 15 },
  retryButton: { alignSelf: "flex-start", backgroundColor: "#A33F37", paddingHorizontal: 12, paddingVertical: 8, borderRadius: 9 },
  retryButtonText: { color: WHITE, fontSize: 10, fontWeight: "900" },
  inlineError: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: "#FFF0EE", padding: 10, borderRadius: 10 },
  inlineErrorText: { flex: 1, color: "#9A342D", fontSize: 9, fontWeight: "700" },
  inlineRetry: { color: "#9A342D", fontSize: 10, fontWeight: "900", padding: 5 },
  moreLoading: { width: 42, alignItems: "center", justifyContent: "center" },
});