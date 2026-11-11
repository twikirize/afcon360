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
import { authClient } from "../../src/services/api";
import { getSelectedApiBaseUrl } from "../../src/services/api";

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
  start_date?: string | null;
  end_date?: string | null;
  city?: string | null;
  country?: string | null;
  venue?: string | null;
  featured?: boolean;
  registration_fee?: string | number | null;
  currency?: string | null;
  property_type?: string | null;
  price_per_night?: string | number | null;
  route_type?: string | null;
  primary_zone?: string | null;
  price_per_seat?: string | number | null;
  available_seats?: number | null;
  likes?: number | null;
  comments?: number | null;
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
  layout?: string;
  seed?: string;
  error?: string;
};

type LoadMode = "initial" | "refresh" | "more";

function localDateKey(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return year + "-" + month + "-" + day;
}

function displayDate(value?: string | null): string {
  if (!value) return "Date to be announced";
  const datePart = value.slice(0, 10);
  const date = new Date(datePart + "T00:00:00");
  if (Number.isNaN(date.getTime())) return datePart;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function displayEventDate(item: FeedItem): string {
  const start = item.metadata?.start_date;
  const end = item.metadata?.end_date;
  if (!start) return "Date to be announced";
  const from = displayDate(start);
  if (!end || end === start) return from;
  return from + " – " + displayDate(end);
}

function isCurrentEvent(item: FeedItem, today: string): boolean {
  const start = item.metadata?.start_date;
  const end = item.metadata?.end_date;
  const lastActiveDay = (end || start || "").slice(0, 10);
  return !lastActiveDay || lastActiveDay >= today;
}

function isHappeningToday(item: FeedItem, today: string): boolean {
  const start = (item.metadata?.start_date || "").slice(0, 10);
  const end = (item.metadata?.end_date || start).slice(0, 10);
  return !!start && start <= today && (!end || end >= today);
}

function eventLocation(item: FeedItem): string {
  const city = item.metadata?.city;
  const country = item.metadata?.country;
  const venue = item.metadata?.venue;
  const place = [city, country].filter(Boolean).join(", ");
  return [venue, place].filter(Boolean).join(" · ");
}

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

function itemIcon(type: string): string {
  switch (type) {
    case "event": return "🏟️";
    case "ad": return "📣";
    case "system_update": return "🔔";
    case "property": return "🏨";
    case "transport": return "🚌";
    case "post": return "💬";
    default: return "📰";
  }
}

function itemTypeLabel(type: string): string {
  switch (type) {
    case "event": return "Event";
    case "ad": return "Sponsored";
    case "system_update": return "Pamoja update";
    case "property": return "Stay";
    case "transport": return "Transport";
    case "post": return "Community";
    default: return "Pamoja";
  }
}

function mergeFeedItems(existing: FeedItem[], incoming: FeedItem[]): FeedItem[] {
  const merged = new Map<string, FeedItem>();
  for (const item of existing) merged.set(item.feed_id, item);
  for (const item of incoming) merged.set(item.feed_id, item);
  return Array.from(merged.values());
}

function SectionHeading({
  title,
  subtitle,
  action,
  onAction,
}: {
  title: string;
  subtitle?: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <View style={styles.sectionHeading}>
      <View style={styles.sectionHeadingCopy}>
        <Text accessibilityRole="header" style={styles.sectionTitle}>{title}</Text>
        {subtitle ? <Text style={styles.sectionSubtitle}>{subtitle}</Text> : null}
      </View>
      {action && onAction ? (
        <Pressable accessibilityRole="button" onPress={onAction} hitSlop={8}>
          <Text style={styles.sectionAction}>{action} ›</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function FeedCard({
  item,
  baseUrl,
  onOpenWebsite,
}: {
  item: FeedItem;
  baseUrl: string;
  onOpenWebsite: (path: string) => void;
}) {
  const image = imageUri(item.image_url, baseUrl);
  const metadata = item.metadata;
  const extras: string[] = [];
  if (item.type === "event") {
    if (metadata?.start_date) extras.push("📅 " + displayDate(metadata.start_date));
    const location = eventLocation(item);
    if (location) extras.push("📍 " + location);
    if (metadata?.registration_fee != null) {
      extras.push("💵 " + String(metadata.registration_fee) + " " + String(metadata.currency || "USD"));
    }
  } else if (item.type === "property") {
    if (metadata?.property_type) extras.push("🏠 " + String(metadata.property_type));
    if (metadata?.city || metadata?.country) extras.push("📍 " + [metadata.city, metadata.country].filter(Boolean).join(", "));
    if (metadata?.price_per_night != null) extras.push("💵 " + String(metadata.price_per_night) + "/night");
  } else if (item.type === "transport") {
    if (metadata?.route_type) extras.push(String(metadata.route_type));
    if (metadata?.primary_zone) extras.push("📍 " + String(metadata.primary_zone));
    if (metadata?.price_per_seat != null) extras.push("💵 " + String(metadata.price_per_seat) + "/seat");
    if (metadata?.available_seats != null) extras.push("🪑 " + String(metadata.available_seats) + " seats");
  } else if (item.type === "post") {
    if (metadata?.likes != null) extras.push("❤ " + String(metadata.likes));
    if (metadata?.comments != null) extras.push("💬 " + String(metadata.comments));
  } else if (item.type === "system_update" && metadata?.module_label) {
    extras.push(String(metadata.module_label));
  }

  return (
    <View style={styles.feedCard}>
      {item.is_pinned ? <Text style={styles.pinnedTag}>📌 Pinned</Text> : null}
      <View style={styles.feedCardHeader}>
        <View style={styles.feedTypeIcon}><Text style={styles.feedTypeIconText}>{itemIcon(item.type)}</Text></View>
        <View style={styles.feedAuthorCopy}>
          <Text style={styles.feedAuthor}>{item.author_name || "Pamoja"}</Text>
          <Text style={styles.feedSource}>{itemTypeLabel(item.type)}{item.source_module ? " · " + item.source_module : ""}</Text>
        </View>
        {item.type === "ad" ? <Text style={styles.sponsoredTag}>Sponsored</Text> : null}
      </View>
      {item.title ? <Text style={styles.feedTitle}>{item.title}</Text> : null}
      {item.body ? <Text style={styles.feedBody}>{item.body}</Text> : null}
      {image ? <Image source={{ uri: image }} style={styles.feedImage} resizeMode="cover" /> : null}
      {extras.length ? (
        <View style={styles.feedExtras}>
          {extras.map((extra, index) => <Text key={String(index)} style={styles.feedExtra}>{extra}</Text>)}
        </View>
      ) : null}
      {item.link_url ? (
        <Pressable accessibilityRole="button" onPress={() => onOpenWebsite(item.link_url || "")} style={styles.feedLink}>
          <Text style={styles.feedLinkText}>View on Pamoja website ↗</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function EventCard({
  item,
  baseUrl,
  onOpenWebsite,
  compact = false,
}: {
  item: FeedItem;
  baseUrl: string;
  onOpenWebsite: (path: string) => void;
  compact?: boolean;
}) {
  const image = imageUri(item.image_url, baseUrl);
  const happening = isHappeningToday(item, localDateKey());
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={"View " + (item.title || "event") + " on Pamoja website"}
      onPress={() => onOpenWebsite(item.link_url || "/events")}
      style={[styles.eventCard, compact && styles.eventCardCompact]}
    >
      {image ? <Image source={{ uri: image }} style={styles.eventImage} resizeMode="cover" /> : (
        <View style={styles.eventArtwork}>
          <Text style={styles.eventArtworkIcon}>🏟️</Text>
          <View style={styles.eventArtworkOrb} />
        </View>
      )}
      <View style={styles.eventCardOverlay} />
      <View style={styles.eventCardContent}>
        <View style={styles.eventBadgeRow}>
          <Text style={happening ? styles.liveBadge : styles.featuredBadge}>
            {happening ? "HAPPENING NOW" : item.metadata?.featured ? "FEATURED" : "UPCOMING"}
          </Text>
        </View>
        <Text numberOfLines={2} style={styles.eventTitle}>{item.title || "Pamoja event"}</Text>
        <Text numberOfLines={1} style={styles.eventMeta}>📅 {displayEventDate(item)}</Text>
        {eventLocation(item) ? <Text numberOfLines={1} style={styles.eventMeta}>📍 {eventLocation(item)}</Text> : null}
        <Text style={styles.eventAction}>Explore event ›</Text>
      </View>
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
      setFeedError(error instanceof Error ? error.message : "Pamoja updates are temporarily unavailable.");
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

  const currentEvents = useMemo(() => {
    const today = localDateKey();
    return feedItems.filter((item) => item.type === "event" && isCurrentEvent(item, today));
  }, [feedItems]);

  const featuredEvents = useMemo(
    () => currentEvents.filter((item) => item.metadata?.featured === true).slice(0, 4),
    [currentEvents]
  );
  const liveUpcomingEvents = useMemo(() => currentEvents.slice(0, 6), [currentEvents]);

  const trendingTopics = useMemo(() => {
    const names = currentEvents.map((item) => item.title).filter((name): name is string => !!name);
    return Array.from(new Set(["AFCON 2027", ...names])).slice(0, 5);
  }, [currentEvents]);

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

  const onRefresh = useCallback(() => {
    void loadFeedPage(1, null, "refresh");
  }, [loadFeedPage]);

  const onLoadMore = useCallback(() => {
    if (!hasMore || loading || loadingMore || !seed) return;
    void loadFeedPage(page + 1, seed, "more");
  }, [hasMore, loading, loadingMore, loadFeedPage, page, seed]);

  const submitSearch = useCallback(() => {
    openEventSearch(search.trim());
  }, [openEventSearch, search]);

  const listHeader = (
    <View style={styles.pageContent}>
      <View style={styles.hero}>
        <View style={styles.heroGlowLarge} />
        <View style={styles.heroGlowSmall} />
        <View style={styles.heroTopLine}>
          <Text style={styles.heroEyebrow}>PAMOJA · AFCON360</Text>
          <View style={styles.heroLivePill}><View style={styles.heroLiveDot} /><Text style={styles.heroLiveText}>EAST AFRICA & BEYOND</Text></View>
        </View>
        <Text style={styles.heroTitle}>Welcome to <Text style={styles.heroTitleGold}>Pamoja</Text></Text>
        <Text style={styles.heroSubtitle}>
          Your gateway to matches, travel, tickets, and experiences across Africa and beyond.
        </Text>
        {user?.display_name ? <Text style={styles.heroGreeting}>Good to see you, {user.display_name}.</Text> : null}
        <View style={styles.heroActions}>
          <Pressable accessibilityRole="button" onPress={() => openService("events")} style={styles.heroPrimaryButton}>
            <Text style={styles.heroPrimaryText}>Explore events</Text>
            <Text style={styles.heroPrimaryArrow}>›</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => openService("stays")} style={styles.heroSecondaryButton}>
            <Text style={styles.heroSecondaryText}>Find Stays & Hotels</Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.serviceChipsFloat}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.serviceChips}>
          <Pressable style={[styles.serviceChip, styles.serviceChipActive]} onPress={() => openService("events")}>
            <Text style={styles.serviceChipIcon}>🏟️</Text><Text style={[styles.serviceChipText, styles.serviceChipTextActive]}>Events</Text>
          </Pressable>
          <Pressable style={styles.serviceChip} onPress={() => openService("stays")}>
            <Text style={styles.serviceChipIcon}>🏨</Text><Text style={styles.serviceChipText}>Stays</Text>
          </Pressable>
          <Pressable style={styles.serviceChip} onPress={() => openService("rides")}>
            <Text style={styles.serviceChipIcon}>🚌</Text><Text style={styles.serviceChipText}>Transport</Text>
          </Pressable>
          <Pressable style={styles.serviceChip} onPress={() => openService("tourism")}>
            <Text style={styles.serviceChipIcon}>🌴</Text><Text style={styles.serviceChipText}>Tourism · website</Text>
          </Pressable>
          <Pressable style={styles.serviceChip} onPress={() => openService("wallet")}>
            <Text style={styles.serviceChipIcon}>👛</Text><Text style={styles.serviceChipText}>Wallet</Text>
          </Pressable>
        </ScrollView>
      </View>

      <View style={styles.searchPanel}>
        <View style={styles.searchHeading}>
          <View>
            <Text style={styles.searchTitle}>What would you like to discover?</Text>
            <Text style={styles.searchSubtitle}>Search events and experiences across the region.</Text>
          </View>
          <Text style={styles.searchIcon}>⌕</Text>
        </View>
        <View style={styles.searchRow}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            onSubmitEditing={submitSearch}
            returnKeyType="search"
            placeholder="Search events, football, music, culture…"
            placeholderTextColor="#89958D"
            style={styles.searchInput}
            accessibilityLabel="Search events and experiences"
          />
          <Pressable accessibilityRole="button" accessibilityLabel="Search events" onPress={submitSearch} style={styles.searchButton}>
            <Text style={styles.searchButtonText}>Search</Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.trendingSection}>
        <Text style={styles.trendingLabel}>🔥  TRENDING</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.trendingChips}>
          {trendingTopics.map((topic) => (
            <Pressable key={topic} onPress={() => openEventSearch(topic)} style={styles.trendingChip}>
              <Text style={styles.trendingChipText}>{topic}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      <View style={styles.quickActionsGrid}>
        <Pressable onPress={() => openService("rides")} style={styles.quickAction}>
          <View style={[styles.quickActionIcon, { backgroundColor: "#E8F2EA" }]}><Text style={styles.quickActionEmoji}>🚘</Text></View>
          <Text style={styles.quickActionTitle}>Book a ride</Text>
          <Text style={styles.quickActionSub}>Move around</Text>
        </Pressable>
        <Pressable onPress={() => openService("stays")} style={styles.quickAction}>
          <View style={[styles.quickActionIcon, { backgroundColor: "#FFF3D6" }]}><Text style={styles.quickActionEmoji}>🏨</Text></View>
          <Text style={styles.quickActionTitle}>Find a stay</Text>
          <Text style={styles.quickActionSub}>Places to rest</Text>
        </Pressable>
        <Pressable onPress={() => openService("events")} style={styles.quickAction}>
          <View style={[styles.quickActionIcon, { backgroundColor: "#E8EEF9" }]}><Text style={styles.quickActionEmoji}>🎟️</Text></View>
          <Text style={styles.quickActionTitle}>Discover events</Text>
          <Text style={styles.quickActionSub}>Moments that matter</Text>
        </Pressable>
        <Pressable onPress={() => openService("wallet")} style={styles.quickAction}>
          <View style={[styles.quickActionIcon, { backgroundColor: "#F2EAF7" }]}><Text style={styles.quickActionEmoji}>👛</Text></View>
          <Text style={styles.quickActionTitle}>Open Wallet</Text>
          <Text style={styles.quickActionSub}>Your payments</Text>
        </Pressable>
      </View>

      <View style={styles.sectionBlock}>
        <SectionHeading title="Featured Events" subtitle="Selected from currently published Pamoja events" action="View all" onAction={() => openEventSearch()} />
        {featuredEvents.length ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.eventRail}>
            {featuredEvents.map((item) => <EventCard key={item.feed_id} item={item} baseUrl={apiBaseUrl} onOpenWebsite={openWebsite} />)}
          </ScrollView>
        ) : (
          <View style={styles.sectionEmpty}>
            <Text style={styles.sectionEmptyIcon}>✨</Text>
            <Text style={styles.sectionEmptyTitle}>Featured events will appear here</Text>
            <Text style={styles.sectionEmptyText}>When an organiser publishes a featured event, it will show up in this space.</Text>
          </View>
        )}
      </View>

      <View style={styles.sectionBlock}>
        <SectionHeading title="Live & Upcoming Events" subtitle="See what is happening now and what is coming next" action="Explore" onAction={() => openEventSearch()} />
        {liveUpcomingEvents.length ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.eventRail}>
            {liveUpcomingEvents.map((item) => <EventCard key={"live-" + item.feed_id} item={item} baseUrl={apiBaseUrl} onOpenWebsite={openWebsite} compact />)}
          </ScrollView>
        ) : (
          <View style={styles.sectionEmptyCompact}>
            <Text style={styles.sectionEmptyIcon}>📅</Text>
            <Text style={styles.sectionEmptyTitle}>New events are on the way</Text>
            <Text style={styles.sectionEmptyText}>Live and upcoming events will appear here as they are published.</Text>
          </View>
        )}
      </View>

      <View style={styles.feedSectionHeading}>
        <SectionHeading title="Latest from Pamoja" subtitle="Posts, announcements, stays, transport and active promotions" />
        <View style={styles.feedLiveLabel}><View style={styles.feedLiveDot} /><Text style={styles.feedLiveText}>LIVE UPDATES</Text></View>
      </View>
    </View>
  );

  const listFooter = (
    <View style={styles.listFooter}>
      {loadingMore ? (
        <View style={styles.loadingMore}><ActivityIndicator color={BRAND_GREEN} /><Text style={styles.loadingMoreText}>Loading more from Pamoja…</Text></View>
      ) : null}
      {!hasMore && feedItems.length > 0 ? <Text style={styles.feedEndText}>You’re all caught up.</Text> : null}
      <View style={styles.hostBanner}>
        <View style={styles.hostBannerDecoration}><Text style={styles.hostBannerStadium}>🏟️</Text></View>
        <Text style={styles.hostBannerEyebrow}>FOR ORGANISERS & COMMUNITIES</Text>
        <Text style={styles.hostBannerTitle}>Host Your Event on <Text style={styles.hostBannerGold}>Pamoja</Text></Text>
        <Text style={styles.hostBannerSubtitle}>Reach new audiences, manage registrations and promote your event.</Text>
        <Pressable accessibilityRole="button" onPress={() => openWebsite("/events/create")} style={styles.hostBannerButton}>
          <Text style={styles.hostBannerButtonText}>Host an event on website ›</Text>
        </Pressable>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      <FlatList
        data={feedItems}
        keyExtractor={(item) => item.feed_id}
        renderItem={({ item }) => <FeedCard item={item} baseUrl={apiBaseUrl} onOpenWebsite={openWebsite} />}
        ListHeaderComponent={listHeader}
        ListFooterComponent={listFooter}
        ListEmptyComponent={
          loading ? (
            <View style={styles.feedEmpty}>
              <ActivityIndicator color={BRAND_GREEN} />
              <Text style={styles.feedEmptyText}>Loading the latest from Pamoja…</Text>
            </View>
          ) : feedError ? (
            <View style={styles.feedError}>
              <Text style={styles.feedErrorTitle}>Pamoja updates are unavailable</Text>
              <Text style={styles.feedErrorText}>{feedError}</Text>
              <Pressable accessibilityRole="button" onPress={() => void loadFeedPage(1, null, "refresh")} style={styles.retryButton}>
                <Text style={styles.retryButtonText}>Try again</Text>
              </Pressable>
            </View>
          ) : (
            <View style={styles.feedEmpty}>
              <Text style={styles.feedEmptyIcon}>🌍</Text>
              <Text style={styles.feedEmptyTitle}>Your Pamoja feed starts here</Text>
              <Text style={styles.feedEmptyText}>New posts, events, places to stay and promotions will appear as they are published.</Text>
            </View>
          )
        }
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={BRAND_GREEN} colors={[BRAND_GREEN]} />}
        onEndReached={onLoadMore}
        onEndReachedThreshold={0.35}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      />
      {feedError && feedItems.length > 0 ? (
        <View style={styles.inlineFeedError}>
          <Text style={styles.inlineFeedErrorText}>{feedError}</Text>
          <Pressable accessibilityRole="button" onPress={() => void loadFeedPage(page + 1, seed || null, "more")}>
            <Text style={styles.inlineFeedRetry}>Retry</Text>
          </Pressable>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: CANVAS },
  listContent: { paddingBottom: 28 },
  pageContent: { paddingBottom: 4, gap: 20 },
  hero: {
    backgroundColor: BRAND_DARK,
    paddingHorizontal: 20,
    paddingTop: 22,
    paddingBottom: 18,
    overflow: "hidden",
    borderBottomLeftRadius: 24,
    borderBottomRightRadius: 24,
  },
  heroGlowLarge: {
    position: "absolute",
    width: 250,
    height: 250,
    borderRadius: 125,
    backgroundColor: "rgba(105,153,91,0.18)",
    right: -105,
    top: -115,
  },
  heroGlowSmall: {
    position: "absolute",
    width: 130,
    height: 130,
    borderRadius: 65,
    borderWidth: 1,
    borderColor: "rgba(255,204,0,0.28)",
    right: 20,
    top: 20,
  },
  heroTopLine: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 22 },
  heroEyebrow: { color: "rgba(255,255,255,0.76)", fontSize: 10, fontWeight: "900", letterSpacing: 1.6 },
  heroLivePill: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: "rgba(255,255,255,0.24)", borderRadius: 99, paddingHorizontal: 9, paddingVertical: 6 },
  heroLiveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: BRAND_GOLD },
  heroLiveText: { color: "rgba(255,255,255,0.8)", fontSize: 8, fontWeight: "800", letterSpacing: 0.8 },
  heroTitle: { color: WHITE, fontSize: 31, fontWeight: "900", letterSpacing: -1.1, lineHeight: 38 },
  heroTitleGold: { color: BRAND_GOLD },
  heroSubtitle: { color: "rgba(255,255,255,0.88)", fontSize: 14, lineHeight: 21, marginTop: 8, maxWidth: 340 },
  heroGreeting: { color: "rgba(255,255,255,0.72)", fontSize: 12, fontWeight: "600", marginTop: 9 },
  heroActions: { flexDirection: "row", gap: 10, marginTop: 19, marginBottom: 16 },
  heroPrimaryButton: { minHeight: 46, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 12, backgroundColor: BRAND_GOLD, borderRadius: 13 },
  heroPrimaryText: { color: "#16351F", fontSize: 13, fontWeight: "900" },
  heroPrimaryArrow: { color: "#16351F", fontSize: 22, lineHeight: 24, fontWeight: "700" },
  heroSecondaryButton: { minHeight: 46, paddingHorizontal: 15, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.10)", borderWidth: 1, borderColor: "rgba(255,255,255,0.38)", borderRadius: 13 },
  heroSecondaryText: { color: WHITE, fontSize: 13, fontWeight: "800" },
  serviceChipsFloat: { marginTop: -21, paddingHorizontal: 18, zIndex: 3, elevation: 3, marginBottom: -4 },
  serviceChips: { gap: 8, paddingRight: 18, paddingVertical: 2 },
  serviceChip: { minHeight: 40, flexDirection: "row", alignItems: "center", gap: 7, paddingHorizontal: 13, borderRadius: 99, borderWidth: 1, borderColor: BORDER, backgroundColor: WHITE, shadowColor: "#173D28", shadowOpacity: 0.08, shadowRadius: 7, shadowOffset: { width: 0, height: 3 } },
  serviceChipActive: { backgroundColor: BRAND_GOLD, borderColor: BRAND_GOLD },
  serviceChipIcon: { fontSize: 14 },
  serviceChipText: { color: BRAND_DARK, fontSize: 11, fontWeight: "800" },
  serviceChipTextActive: { color: BRAND_DARK },
  searchPanel: { marginHorizontal: 16, marginTop: 10, padding: 15, backgroundColor: WHITE, borderRadius: 18, borderWidth: 1, borderColor: BORDER, shadowColor: "#173D28", shadowOpacity: 0.05, shadowRadius: 12, shadowOffset: { width: 0, height: 5 }, elevation: 2, gap: 12 },
  searchHeading: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  searchTitle: { color: INK, fontSize: 15, fontWeight: "900" },
  searchSubtitle: { color: MUTED, fontSize: 11, marginTop: 3 },
  searchIcon: { color: BRAND_GREEN, fontSize: 28, fontWeight: "700" },
  searchRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  searchInput: { flex: 1, minHeight: 46, borderWidth: 1, borderColor: BORDER, backgroundColor: "#FAFCFA", borderRadius: 12, paddingHorizontal: 12, color: INK, fontSize: 13 },
  searchButton: { minHeight: 46, paddingHorizontal: 14, borderRadius: 12, backgroundColor: BRAND_GREEN, alignItems: "center", justifyContent: "center" },
  searchButtonText: { color: WHITE, fontSize: 12, fontWeight: "900" },
  trendingSection: { paddingHorizontal: 18, gap: 9 },
  trendingLabel: { color: MUTED, fontSize: 10, fontWeight: "900", letterSpacing: 1 },
  trendingChips: { gap: 7, paddingRight: 16 },
  trendingChip: { borderRadius: 99, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: "#E9F0E9", borderWidth: 1, borderColor: "#D9E5D9" },
  trendingChipText: { color: BRAND_DARK, fontSize: 11, fontWeight: "800" },
  quickActionsGrid: { paddingHorizontal: 16, flexDirection: "row", flexWrap: "wrap", gap: 9 },
  quickAction: { width: "48%", flexGrow: 1, minHeight: 105, borderRadius: 16, padding: 12, backgroundColor: WHITE, borderWidth: 1, borderColor: BORDER, gap: 4 },
  quickActionIcon: { width: 36, height: 36, borderRadius: 12, alignItems: "center", justifyContent: "center", marginBottom: 3 },
  quickActionEmoji: { fontSize: 18 },
  quickActionTitle: { color: INK, fontSize: 12, fontWeight: "900" },
  quickActionSub: { color: MUTED, fontSize: 10 },
  sectionBlock: { gap: 11 },
  sectionHeading: { paddingHorizontal: 18, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  sectionHeadingCopy: { flex: 1, gap: 3 },
  sectionTitle: { color: INK, fontSize: 17, fontWeight: "900", letterSpacing: -0.25 },
  sectionSubtitle: { color: MUTED, fontSize: 11, lineHeight: 16 },
  sectionAction: { color: BRAND_GREEN, fontSize: 11, fontWeight: "900" },
  eventRail: { gap: 11, paddingHorizontal: 16, paddingRight: 22 },
  eventCard: { width: 275, height: 182, borderRadius: 17, overflow: "hidden", backgroundColor: BRAND_DARK, justifyContent: "flex-end" },
  eventCardCompact: { width: 252, height: 158 },
  eventImage: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0 },
  eventArtwork: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0, backgroundColor: "#1D4A32", alignItems: "flex-end", justifyContent: "flex-start", padding: 16, overflow: "hidden" },
  eventArtworkIcon: { fontSize: 54, opacity: 0.45 },
  eventArtworkOrb: { position: "absolute", width: 170, height: 170, borderRadius: 85, borderWidth: 20, borderColor: "rgba(255,204,0,0.18)", right: -40, bottom: -70 },
  eventCardOverlay: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0, backgroundColor: "rgba(8,26,16,0.30)" },
  eventCardContent: { padding: 14, gap: 4 },
  eventBadgeRow: { flexDirection: "row", alignItems: "center" },
  featuredBadge: { overflow: "hidden", color: BRAND_DARK, backgroundColor: BRAND_GOLD, fontSize: 8, fontWeight: "900", letterSpacing: 0.7, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 99 },
  liveBadge: { overflow: "hidden", color: WHITE, backgroundColor: "#D64A40", fontSize: 8, fontWeight: "900", letterSpacing: 0.7, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 99 },
  eventTitle: { color: WHITE, fontSize: 15, lineHeight: 19, fontWeight: "900" },
  eventMeta: { color: "rgba(255,255,255,0.82)", fontSize: 10, fontWeight: "600" },
  eventAction: { color: BRAND_GOLD, fontSize: 10, fontWeight: "900", marginTop: 3 },
  sectionEmpty: { marginHorizontal: 16, padding: 16, borderRadius: 15, backgroundColor: WHITE, borderWidth: 1, borderColor: BORDER, gap: 5 },
  sectionEmptyCompact: { marginHorizontal: 16, padding: 14, borderRadius: 15, backgroundColor: WHITE, borderWidth: 1, borderColor: BORDER, gap: 5 },
  sectionEmptyIcon: { fontSize: 20 },
  sectionEmptyTitle: { color: INK, fontSize: 12, fontWeight: "900" },
  sectionEmptyText: { color: MUTED, fontSize: 11, lineHeight: 16 },
  feedSectionHeading: { paddingTop: 5, gap: 8 },
  feedLiveLabel: { paddingHorizontal: 18, flexDirection: "row", alignItems: "center", gap: 6 },
  feedLiveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#2D9A61" },
  feedLiveText: { color: BRAND_GREEN, fontSize: 9, fontWeight: "900", letterSpacing: 0.8 },
  feedCard: { marginHorizontal: 16, marginBottom: 11, padding: 14, borderWidth: 1, borderColor: BORDER, borderRadius: 17, backgroundColor: WHITE, gap: 9 },
  pinnedTag: { alignSelf: "flex-start", color: "#795E16", fontSize: 9, fontWeight: "900", backgroundColor: "#FFF4D5", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 99 },
  feedCardHeader: { flexDirection: "row", alignItems: "center", gap: 10 },
  feedTypeIcon: { width: 36, height: 36, borderRadius: 12, backgroundColor: "#EDF4EE", alignItems: "center", justifyContent: "center" },
  feedTypeIconText: { fontSize: 18 },
  feedAuthorCopy: { flex: 1, gap: 2 },
  feedAuthor: { color: INK, fontSize: 12, fontWeight: "900" },
  feedSource: { color: MUTED, fontSize: 9, fontWeight: "700", textTransform: "capitalize" },
  sponsoredTag: { color: "#88651A", backgroundColor: "#FFF3D5", fontSize: 9, fontWeight: "900", paddingHorizontal: 8, paddingVertical: 5, borderRadius: 99, overflow: "hidden" },
  feedTitle: { color: INK, fontSize: 14, lineHeight: 19, fontWeight: "900" },
  feedBody: { color: "#506057", fontSize: 12, lineHeight: 18 },
  feedImage: { width: "100%", height: 190, borderRadius: 12, backgroundColor: "#E8EEE9" },
  feedExtras: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  feedExtra: { color: "#596A60", backgroundColor: "#F2F6F2", borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, fontSize: 9, fontWeight: "700", overflow: "hidden" },
  feedLink: { alignSelf: "flex-start", paddingVertical: 3 },
  feedLinkText: { color: BRAND_GREEN, fontSize: 11, fontWeight: "900" },
  feedEmpty: { alignItems: "center", paddingHorizontal: 28, paddingVertical: 25, gap: 8 },
  feedEmptyIcon: { fontSize: 28 },
  feedEmptyTitle: { color: INK, fontSize: 14, fontWeight: "900", textAlign: "center" },
  feedEmptyText: { color: MUTED, fontSize: 11, lineHeight: 17, textAlign: "center" },
  feedError: { marginHorizontal: 16, marginVertical: 8, padding: 15, borderRadius: 14, backgroundColor: "#FFF0EE", gap: 7 },
  feedErrorTitle: { color: "#9A342D", fontSize: 13, fontWeight: "900" },
  feedErrorText: { color: "#8D4943", fontSize: 11, lineHeight: 16 },
  retryButton: { alignSelf: "flex-start", backgroundColor: "#A33F37", paddingHorizontal: 13, paddingVertical: 8, borderRadius: 9, marginTop: 3 },
  retryButtonText: { color: WHITE, fontSize: 11, fontWeight: "900" },
  inlineFeedError: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: "#FFF0EE", padding: 10, marginHorizontal: 16, borderRadius: 10 },
  inlineFeedErrorText: { flex: 1, color: "#9A342D", fontSize: 10, fontWeight: "700" },
  inlineFeedRetry: { color: "#9A342D", fontSize: 11, fontWeight: "900", padding: 5 },
  loadingMore: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8, padding: 16 },
  loadingMoreText: { color: MUTED, fontSize: 10, fontWeight: "700" },
  feedEndText: { color: MUTED, textAlign: "center", fontSize: 10, fontWeight: "700", padding: 12 },
  listFooter: { paddingHorizontal: 0, paddingTop: 2, gap: 10 },
  hostBanner: { marginHorizontal: 16, marginTop: 8, marginBottom: 18, padding: 20, borderRadius: 19, backgroundColor: BRAND_DARK, overflow: "hidden", alignItems: "flex-start", gap: 8 },
  hostBannerDecoration: { position: "absolute", right: 6, top: 12, opacity: 0.14 },
  hostBannerStadium: { fontSize: 74 },
  hostBannerEyebrow: { color: "rgba(255,255,255,0.66)", fontSize: 8, fontWeight: "900", letterSpacing: 1.2 },
  hostBannerTitle: { color: WHITE, fontSize: 19, fontWeight: "900", lineHeight: 24 },
  hostBannerGold: { color: BRAND_GOLD },
  hostBannerSubtitle: { color: "rgba(255,255,255,0.82)", fontSize: 11, lineHeight: 17, maxWidth: 260 },
  hostBannerButton: { minHeight: 42, paddingHorizontal: 14, paddingVertical: 10, justifyContent: "center", borderRadius: 11, backgroundColor: BRAND_GOLD, marginTop: 3 },
  hostBannerButtonText: { color: BRAND_DARK, fontSize: 11, fontWeight: "900" },
});
