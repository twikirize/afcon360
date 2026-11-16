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
import { useFocusEffect, useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useAuth } from "../../src/auth/AuthProvider";
import { authClient, eventClient } from "../../src/services/api";
import type { NativeEventRegistration } from "@afcon360/mobile-core";
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

type RegistrationFilter = "upcoming" | "past" | "all";

function registrationEndDate(registration: NativeEventRegistration): string {
  return (registration.event.end_date || registration.event.start_date || "").slice(0, 10);
}

function registrationIsPast(registration: NativeEventRegistration, today: string): boolean {
  const endDate = registrationEndDate(registration);
  return !!endDate && endDate < today;
}

function registrationLocation(registration: NativeEventRegistration): string {
  return [registration.event.city, registration.event.country].filter(Boolean).join(", ") || "Location to be announced";
}

function registrationActivityLabel(registration: NativeEventRegistration): string {
  return registration.status === "checked_in" ? "Attended" : "Registered";
}

function registrationCreatedLabel(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

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
  const [registrations, setRegistrations] = useState<NativeEventRegistration[]>([]);
  const [registrationsLoading, setRegistrationsLoading] = useState(true);
  const [registrationsError, setRegistrationsError] = useState<string | null>(null);
  const [registrationFilter, setRegistrationFilter] = useState<RegistrationFilter>("upcoming");
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
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

  const loadRegistrations = useCallback(async () => {
    setRegistrationsLoading(true);
    setRegistrationsError(null);
    try {
      const result = await eventClient.listRegistrations(30, 0);
      setRegistrations(result.items ?? []);
    } catch (error) {
      setRegistrationsError(error instanceof Error ? error.message : "Your event registrations are temporarily unavailable.");
    } finally {
      setRegistrationsLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void loadRegistrations();
    }, [loadRegistrations])
  );

  const today = localDateKey();
  const upcomingRegistrations = useMemo(() => registrations
    .filter((registration) =>
      registration.status !== "cancelled" && !registrationIsPast(registration, today)
    )
    .slice()
    .sort((a, b) => {
      const aDate = (a.event.start_date || "9999-12-31").slice(0, 10);
      const bDate = (b.event.start_date || "9999-12-31").slice(0, 10);
      return aDate.localeCompare(bDate);
    }), [registrations, today]);
  const pastRegistrations = useMemo(() => registrations
    .filter((registration) => registrationIsPast(registration, today))
    .slice()
    .sort((a, b) => (b.event.start_date || "").localeCompare(a.event.start_date || "")),
  [registrations, today]);
  const recentRegistrations = useMemo(() => registrations
    .slice()
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
    .slice(0, 5), [registrations]);
  const visibleRegistrations = registrationFilter === "upcoming"
    ? upcomingRegistrations
    : registrationFilter === "past"
      ? pastRegistrations
      : registrations;
  const nextEvent = upcomingRegistrations[0] ?? null;
  const attendedCount = registrations.filter((registration) => registration.status === "checked_in").length;
  const activeTicketCount = registrations.filter((registration) =>
    registration.status !== "cancelled" && !registrationIsPast(registration, today)
  ).length;

  const calendarMonthLabel = calendarMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const calendarDays = useMemo(() => {
    const year = calendarMonth.getFullYear();
    const month = calendarMonth.getMonth();
    const offset = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const cellCount = Math.ceil((offset + daysInMonth) / 7) * 7;
    return Array.from({ length: cellCount }, (_, index) => {
      const day = index - offset + 1;
      return day >= 1 && day <= daysInMonth ? day : null;
    });
  }, [calendarMonth]);
  const calendarEventDays = useMemo(() => {
    const prefix = calendarMonth.getFullYear() + "-" + String(calendarMonth.getMonth() + 1).padStart(2, "0") + "-";
    return new Set(registrations
      .map((registration) => (registration.event.start_date || "").slice(0, 10))
      .filter((value) => value.startsWith(prefix))
      .map((value) => Number(value.slice(8, 10))));
  }, [registrations, calendarMonth]);

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
    void Promise.all([
      loadFeedPage(1, null, "refresh"),
      loadRegistrations(),
    ]);
  }, [loadFeedPage, loadRegistrations]);

  const onLoadMore = useCallback(() => {
    if (!hasMore || loading || loadingMore || !seed) return;
    void loadFeedPage(page + 1, seed, "more");
  }, [hasMore, loading, loadingMore, loadFeedPage, page, seed]);

  const submitSearch = useCallback(() => {
    openEventSearch(search.trim());
  }, [openEventSearch, search]);

  const listHeader = (
    <View style={styles.geminiPage}>
      <View style={styles.geminiPageContent}>
        <View style={styles.geminiTopHeader}>
          <View style={styles.geminiBrandRow}>
            <View style={styles.geminiEmblemOuter}>
              <View style={styles.geminiEmblemInner}>
                <Text style={styles.geminiEmblemMark}>△</Text>
              </View>
            </View>
            <Text style={styles.geminiBrandTitle}>Pamoja</Text>
          </View>
          <View style={styles.geminiTopActions}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Open activity and updates"
              style={styles.geminiCircleButton}
              onPress={() => router.push("/(tabs)/activity" as never)}
            >
              <View style={styles.geminiBellIcon}>
                <View style={styles.geminiBellDome} />
                <View style={styles.geminiBellBase} />
                <View style={styles.geminiBellClapper} />
              </View>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Open account"
              style={[styles.geminiCircleButton, styles.geminiCircleButtonMint]}
              onPress={() => router.push("/(tabs)/account" as never)}
            >
              <View style={styles.geminiPersonIcon}>
                <View style={styles.geminiPersonHead} />
                <View style={styles.geminiPersonShoulders} />
              </View>
            </Pressable>
          </View>
        </View>

        <View style={styles.geminiHeroStage}>
          <View style={styles.geminiHeroCard}>
            <View style={styles.geminiHeroGlowOrb} />
            <View style={styles.geminiHeroLeft}>
              <Text style={styles.geminiHeroEyebrow}>EAST AFRICA</Text>
              <Text style={styles.geminiHeroTitle}>Your world,{"\n"}together.</Text>
              <Text style={styles.geminiHeroSub}>One app. More to explore.</Text>
              {user?.display_name ? (
                <Text style={styles.geminiHeroGreeting}>Good to see you, {user.display_name}.</Text>
              ) : null}
            </View>
            <View style={styles.geminiHeroIllustration}>
              <View style={styles.geminiSunHalo}>
                <View style={styles.geminiSunDot} />
              </View>
              <View style={styles.geminiSkyline}>
                <View style={[styles.geminiTower, { height: 40 }]} />
                <View style={[styles.geminiTower, { height: 58, backgroundColor: "#5D9A74" }]} />
                <View style={[styles.geminiTower, { height: 34 }]} />
                <View style={[styles.geminiTower, { height: 50, backgroundColor: "#498762" }]} />
              </View>
              <View style={styles.geminiTravelerRow}>
                <View style={styles.geminiTravelerCircle}>
                  <Text style={styles.geminiTravelerGlyph}>👥</Text>
                </View>
              </View>
            </View>
            <View style={styles.geminiHeroHillBand} />
            <View style={styles.geminiFloatingSearch}>
              <Text style={styles.geminiSearchGlyph}>⌕</Text>
              <TextInput
                value={search}
                onChangeText={setSearch}
                onSubmitEditing={submitSearch}
                returnKeyType="search"
                placeholder="Search events, tickets and experiences..."
                placeholderTextColor="#164029"
                style={styles.geminiSearchInput}
                accessibilityLabel="Search Pamoja events and tickets"
              />
              {search.trim().length > 0 ? (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Clear search"
                  onPress={() => setSearch("")}
                >
                  <Text style={styles.geminiClearSearch}>×</Text>
                </Pressable>
              ) : null}
            </View>
          </View>
          {search.trim().length > 0 ? (
            <View style={styles.geminiScopeTabsRow}>
              <Pressable style={[styles.geminiScopeTab, styles.geminiScopeTabActive]} onPress={() => setSearch("")}>
                <Text style={[styles.geminiScopeText, styles.geminiScopeTextActive]}>All</Text>
              </Pressable>
              <Pressable style={styles.geminiScopeTab} onPress={() => openService("events")}>
                <Text style={styles.geminiScopeText}>Events</Text>
              </Pressable>
              <Pressable style={styles.geminiScopeTab} onPress={() => openService("stays")}>
                <Text style={styles.geminiScopeText}>Stays</Text>
              </Pressable>
              <Pressable style={styles.geminiScopeTab} onPress={() => openService("rides")}>
                <Text style={styles.geminiScopeText}>Transport</Text>
              </Pressable>
              <Pressable style={styles.geminiScopeTab} onPress={() => openService("tourism")}>
                <Text style={styles.geminiScopeText}>Adventure</Text>
              </Pressable>
            </View>
          ) : null}
        </View>

        <View style={styles.geminiSection}>
          <Text style={styles.geminiSectionTitle}>Make yourself feel at home</Text>
          <View style={styles.geminiServiceGrid}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Open transport and rides"
              style={styles.geminiServiceCard}
              onPress={() => openService("rides")}
            >
              <View style={styles.geminiServiceCardTop}>
                <View style={[styles.geminiServiceIconCircle, styles.geminiMintIcon]}>
                  <Text style={styles.geminiServiceIcon}>🚌</Text>
                </View>
                <Text style={styles.geminiDiagonalArrow}>↗</Text>
              </View>
              <Text style={styles.geminiServiceTitle}>Transport</Text>
              <Text style={styles.geminiServiceSubtitle}>Find your ride</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Find a place to stay"
              style={styles.geminiServiceCard}
              onPress={() => openService("stays")}
            >
              <View style={styles.geminiServiceCardTop}>
                <View style={[styles.geminiServiceIconCircle, styles.geminiPeachIcon]}>
                  <Text style={styles.geminiServiceIcon}>🛏️</Text>
                </View>
                <Text style={styles.geminiDiagonalArrow}>↗</Text>
              </View>
              <Text style={styles.geminiServiceTitle}>Stays</Text>
              <Text style={styles.geminiServiceSubtitle}>Find a place to stay</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Discover events and tickets"
              style={styles.geminiServiceCard}
              onPress={() => openService("events")}
            >
              <View style={styles.geminiServiceCardTop}>
                <View style={[styles.geminiServiceIconCircle, styles.geminiPeachIcon]}>
                  <Text style={styles.geminiServiceIcon}>🎟️</Text>
                </View>
                <Text style={styles.geminiDiagonalArrow}>↗</Text>
              </View>
              <Text style={styles.geminiServiceTitle}>Events & Tickets</Text>
              <Text style={styles.geminiServiceSubtitle}>Events & QR passes</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Adventure and tourism on website"
              style={styles.geminiServiceCard}
              onPress={() => openService("tourism")}
            >
              <View style={styles.geminiServiceCardTop}>
                <View style={[styles.geminiServiceIconCircle, styles.geminiMintIcon]}>
                  <Text style={styles.geminiServiceIcon}>🧭</Text>
                </View>
                <Text style={styles.geminiDiagonalArrow}>↗</Text>
              </View>
              <Text style={styles.geminiServiceTitle}>Adventure</Text>
              <Text style={styles.geminiServiceSubtitle}>Tours, safaris & experiences</Text>
              <View style={styles.geminiWebsiteHint}>
                <Text style={styles.geminiWebsiteHintText}>ON PAMOJA WEBSITE</Text>
              </View>
            </Pressable>
          </View>
        </View>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Open Pamoja wallet"
          style={styles.geminiWalletBanner}
          onPress={() => openService("wallet")}
        >
          <View style={styles.geminiBannerLeft}>
            <View style={styles.geminiWalletIconBox}>
              <Text style={styles.geminiWalletIcon}>◈</Text>
            </View>
            <View style={styles.geminiBannerCopy}>
              <Text style={styles.geminiWalletTitle}>Your Pamoja wallet</Text>
              <Text style={styles.geminiWalletSubtitle}>Payments, all in one place</Text>
            </View>
          </View>
          <Text style={styles.geminiWalletChevron}>›</Text>
        </Pressable>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Open your bookings and activity"
          style={styles.geminiBookingsCard}
          onPress={() => openService("stays")}
        >
          <View style={styles.geminiBannerLeft}>
            <View style={[styles.geminiServiceIconCircle, styles.geminiMintIcon]}>
              <Text style={styles.geminiBookingsIcon}>▦</Text>
            </View>
            <View style={styles.geminiBannerCopy}>
              <Text style={styles.geminiBookingsTitle}>My bookings</Text>
              <Text style={styles.geminiBookingsSubtitle}>Manage your stays and rides</Text>
            </View>
          </View>
          <Text style={styles.geminiBookingsChevron}>›</Text>
        </Pressable>
      </View>

      <View style={styles.myEventsDashboard}>
        <View style={styles.myEventsHeading}>
          <View style={styles.myEventsHeadingCopy}>
            <Text style={styles.dashboardEyebrow}>YOUR AFCON360 DASHBOARD</Text>
            <Text accessibilityRole="header" style={styles.myEventsTitle}>My Events</Text>
            <Text style={styles.myEventsSubtitle}>Your tickets, registrations, schedule and event activity.</Text>
          </View>
          <Pressable accessibilityRole="button" onPress={() => openService("events")} style={styles.browseEventsButton}>
            <Text style={styles.browseEventsButtonText}>Browse events</Text>
          </Pressable>
        </View>

        {registrationsError ? (
          <View style={styles.registrationError}>
            <Text style={styles.registrationErrorTitle}>Your event activity could not be loaded</Text>
            <Text style={styles.registrationErrorText}>{registrationsError}</Text>
            <Pressable accessibilityRole="button" onPress={() => void loadRegistrations()} style={styles.registrationRetryButton}>
              <Text style={styles.registrationRetryText}>Retry</Text>
            </Pressable>
          </View>
        ) : null}

        <View style={styles.organizerPromo}>
          <View style={styles.organizerPromoIcon}><Text style={styles.organizerPromoIconText}>🎤</Text></View>
          <View style={styles.organizerPromoCopy}>
            <Text style={styles.organizerPromoTitle}>Want to host your own event?</Text>
            <Text style={styles.organizerPromoDescription}>Become an organiser, publish events and manage your audience on Pamoja.</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Become an event organiser on Pamoja website"
            onPress={() => openWebsite("/events/create")}
            style={styles.organizerPromoButton}
          >
            <Text style={styles.organizerPromoButtonText}>Host an event on website ↗</Text>
          </Pressable>
        </View>

        <View style={styles.dashboardStatsRow}>
          <View style={styles.dashboardStatCard}>
            <Text style={styles.dashboardStatValue}>{registrationsLoading ? "—" : upcomingRegistrations.length}</Text>
            <Text style={styles.dashboardStatLabel}>UPCOMING</Text>
          </View>
          <View style={styles.dashboardStatCard}>
            <Text style={styles.dashboardStatValue}>{registrationsLoading ? "—" : activeTicketCount}</Text>
            <Text style={styles.dashboardStatLabel}>ACTIVE TICKETS</Text>
          </View>
          <View style={styles.dashboardStatCard}>
            <Text style={styles.dashboardStatValue}>{registrationsLoading ? "—" : attendedCount}</Text>
            <Text style={styles.dashboardStatLabel}>BADGES EARNED</Text>
          </View>
        </View>

        <View style={styles.dashboardCard}>
          <View style={styles.dashboardCardHeader}>
            <View>
              <Text style={styles.dashboardCardTitle}>Event calendar</Text>
              <Text style={styles.dashboardCardSubtitle}>Your registered event dates</Text>
            </View>
            <View style={styles.calendarMonthControls}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Previous month"
                onPress={() => setCalendarMonth((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))}
                style={styles.calendarMonthButton}
              >
                <Text style={styles.calendarMonthButtonText}>‹</Text>
              </Pressable>
              <Text style={styles.calendarMonthLabel}>{calendarMonthLabel}</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Next month"
                onPress={() => setCalendarMonth((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))}
                style={styles.calendarMonthButton}
              >
                <Text style={styles.calendarMonthButtonText}>›</Text>
              </Pressable>
            </View>
          </View>
          <View style={styles.calendarWeekRow}>
            {["S", "M", "T", "W", "T", "F", "S"].map((day, index) => (
              <Text key={day + index} style={styles.calendarWeekday}>{day}</Text>
            ))}
          </View>
          <View style={styles.calendarGrid}>
            {calendarDays.map((day, index) => {
              const dateKey = day
                ? calendarMonth.getFullYear() + "-" + String(calendarMonth.getMonth() + 1).padStart(2, "0") + "-" + String(day).padStart(2, "0")
                : "";
              const isToday = dateKey === today;
              const hasEvent = day !== null && calendarEventDays.has(day);
              return (
                <View key={"calendar-" + index} style={styles.calendarDayCell}>
                  <View style={[styles.calendarDayCircle, isToday && styles.calendarDayToday, hasEvent && styles.calendarDayHasEvent]}>
                    <Text style={[styles.calendarDayText, isToday && styles.calendarDayTodayText, hasEvent && styles.calendarDayEventText]}>
                      {day ?? ""}
                    </Text>
                  </View>
                  {hasEvent ? <View style={styles.calendarEventDot} /> : <View style={styles.calendarNoDot} />}
                </View>
              );
            })}
          </View>
          <View style={styles.calendarLegend}>
            <View style={styles.calendarLegendDot} />
            <Text style={styles.calendarLegendText}>Registered event</Text>
          </View>
        </View>

        <View style={styles.dashboardCard}>
          <View style={styles.dashboardCardHeader}>
            <View style={{ flex: 1 }}>
              <Text style={styles.dashboardCardTitle}>Next event</Text>
              <Text style={styles.dashboardCardSubtitle}>Your next registered experience</Text>
            </View>
            <Text style={styles.dashboardSectionIcon}>📅</Text>
          </View>
          {registrationsLoading ? (
            <View style={styles.dashboardLoadingRow}>
              <ActivityIndicator color={BRAND_GREEN} />
              <Text style={styles.dashboardMuted}>Loading your registrations…</Text>
            </View>
          ) : nextEvent ? (
            <View style={styles.nextEventContent}>
              <Text style={styles.nextEventName}>{nextEvent.event.name || "Registered event"}</Text>
              <Text style={styles.nextEventMeta}>📅 {displayDate(nextEvent.event.start_date)}</Text>
              <Text style={styles.nextEventMeta}>📍 {registrationLocation(nextEvent)}</Text>
              <Text style={styles.nextEventTicket}>{nextEvent.ticket_type} · {nextEvent.registration_reference}</Text>
              <Pressable accessibilityRole="button" onPress={() => openService("events")} style={styles.nextEventButton}>
                <Text style={styles.nextEventButtonText}>Open my tickets ›</Text>
              </Pressable>
            </View>
          ) : (
            <View style={styles.dashboardEmpty}>
              <Text style={styles.dashboardEmptyTitle}>No upcoming events yet</Text>
              <Text style={styles.dashboardMuted}>When you register for an event, its date and ticket will appear here.</Text>
              <Pressable accessibilityRole="button" onPress={() => openService("events")} style={styles.nextEventButton}>
                <Text style={styles.nextEventButtonText}>Discover events ›</Text>
              </Pressable>
            </View>
          )}
        </View>

        <View style={styles.dashboardCard}>
          <View style={styles.dashboardCardHeader}>
            <View>
              <Text style={styles.dashboardCardTitle}>Upcoming reminders</Text>
              <Text style={styles.dashboardCardSubtitle}>The next dates on your event schedule</Text>
            </View>
            <Text style={styles.dashboardSectionIcon}>🔔</Text>
          </View>
          {registrationsLoading ? (
            <ActivityIndicator color={BRAND_GREEN} />
          ) : upcomingRegistrations.length ? (
            upcomingRegistrations.slice(0, 3).map((registration) => (
              <View key={"reminder-" + registration.registration_reference} style={styles.reminderRow}>
                <View style={styles.reminderDateBadge}>
                  <Text style={styles.reminderDateDay}>
                    {registration.event.start_date ? registration.event.start_date.slice(8, 10) : "—"}
                  </Text>
                  <Text style={styles.reminderDateMonth}>
                    {registration.event.start_date
                      ? new Date(registration.event.start_date.slice(0, 10) + "T00:00:00").toLocaleDateString(undefined, { month: "short" }).toUpperCase()
                      : "DATE"}
                  </Text>
                </View>
                <View style={styles.reminderCopy}>
                  <Text numberOfLines={1} style={styles.reminderTitle}>{registration.event.name || "Registered event"}</Text>
                  <Text numberOfLines={1} style={styles.reminderMeta}>{displayDate(registration.event.start_date)} · {registrationLocation(registration)}</Text>
                </View>
              </View>
            ))
          ) : (
            <Text style={styles.dashboardMuted}>No upcoming event reminders.</Text>
          )}
        </View>

        <View style={styles.dashboardCard}>
          <View style={styles.dashboardCardHeader}>
            <View style={{ flex: 1 }}>
              <Text style={styles.dashboardCardTitle}>My registrations</Text>
              <Text style={styles.dashboardCardSubtitle}>Review your upcoming and past event tickets</Text>
            </View>
            <Pressable accessibilityRole="button" onPress={() => openService("events")}>
              <Text style={styles.dashboardLink}>All tickets ›</Text>
            </Pressable>
          </View>
          <View style={styles.registrationFilters}>
            {([
              { key: "upcoming", label: "Upcoming", count: upcomingRegistrations.length },
              { key: "past", label: "Past", count: pastRegistrations.length },
              { key: "all", label: "All", count: registrations.length },
            ] as const).map((filter) => (
              <Pressable
                key={filter.key}
                accessibilityRole="button"
                accessibilityState={{ selected: registrationFilter === filter.key }}
                onPress={() => setRegistrationFilter(filter.key)}
                style={[styles.registrationFilter, registrationFilter === filter.key && styles.registrationFilterActive]}
              >
                <Text style={[styles.registrationFilterText, registrationFilter === filter.key && styles.registrationFilterTextActive]}>
                  {filter.label} {filter.count}
                </Text>
              </Pressable>
            ))}
          </View>
          {registrationsLoading ? (
            <View style={styles.dashboardLoadingRow}>
              <ActivityIndicator color={BRAND_GREEN} />
              <Text style={styles.dashboardMuted}>Loading your event registrations…</Text>
            </View>
          ) : visibleRegistrations.length ? (
            visibleRegistrations.slice(0, 5).map((registration) => (
              <Pressable
                key={"registration-" + registration.registration_reference}
                accessibilityRole="button"
                accessibilityLabel={"Open tickets for " + (registration.event.name || "registered event")}
                onPress={() => openService("events")}
                style={styles.registrationRow}
              >
                <View style={styles.registrationRowCopy}>
                  <Text numberOfLines={1} style={styles.registrationRowTitle}>{registration.event.name || "Registered event"}</Text>
                  <Text style={styles.registrationRowMeta}>{displayDate(registration.event.start_date)} · {registration.ticket_type}</Text>
                  <Text style={styles.registrationRowReference}>{registration.registration_reference}</Text>
                </View>
                <View style={[styles.registrationStatus, registration.status === "confirmed" || registration.status === "checked_in" ? styles.registrationStatusGood : styles.registrationStatusOther]}>
                  <Text style={[styles.registrationStatusText, registration.status === "confirmed" || registration.status === "checked_in" ? styles.registrationStatusTextGood : styles.registrationStatusTextOther]}>
                    {registration.status.replace(/_/g, " ")}
                  </Text>
                </View>
                <Text style={styles.registrationChevron}>›</Text>
              </Pressable>
            ))
          ) : (
            <View style={styles.dashboardEmpty}>
              <Text style={styles.dashboardEmptyTitle}>
                {registrationFilter === "past" ? "No past events" : registrationFilter === "all" ? "No registrations yet" : "No upcoming events"}
              </Text>
              <Text style={styles.dashboardMuted}>
                {registrationFilter === "past"
                  ? "Your attended events will appear here."
                  : "Register for an event to see your tickets and schedule here."}
              </Text>
              {registrationFilter !== "past" ? (
                <Pressable accessibilityRole="button" onPress={() => openService("events")} style={styles.nextEventButton}>
                  <Text style={styles.nextEventButtonText}>Browse events ›</Text>
                </Pressable>
              ) : null}
            </View>
          )}
        </View>

        <View style={styles.dashboardCard}>
          <View style={styles.dashboardCardHeader}>
            <View>
              <Text style={styles.dashboardCardTitle}>Recent activity</Text>
              <Text style={styles.dashboardCardSubtitle}>Your latest event registrations and attendance</Text>
            </View>
            <Text style={styles.dashboardSectionIcon}>↗</Text>
          </View>
          {registrationsLoading ? (
            <ActivityIndicator color={BRAND_GREEN} />
          ) : recentRegistrations.length ? (
            recentRegistrations.map((registration) => (
              <View key={"activity-" + registration.registration_reference} style={styles.activityRow}>
                <View style={styles.activityIcon}>
                  <Text style={styles.activityIconText}>{registration.status === "checked_in" ? "✓" : "🎟️"}</Text>
                </View>
                <View style={styles.activityCopy}>
                  <Text numberOfLines={1} style={styles.activityTitle}>{registration.event.name || "Event registration"}</Text>
                  <Text style={styles.activityMeta}>
                    {registrationActivityLabel(registration)} · {registration.ticket_type} · {registrationCreatedLabel(registration.created_at)}
                  </Text>
                </View>
              </View>
            ))
          ) : (
            <Text style={styles.dashboardMuted}>No activity yet. Register for an event to get started.</Text>
          )}
        </View>
      </View>

      <View style={styles.geminiLowerContent}>
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
    </View>
  );

  const listFooter = (
    <View style={styles.listFooter}>
      {loadingMore ? (
        <View style={styles.loadingMore}><ActivityIndicator color={BRAND_GREEN} /><Text style={styles.loadingMoreText}>Loading more from Pamoja…</Text></View>
      ) : null}
      {!hasMore && feedItems.length > 0 ? <Text style={styles.feedEndText}>You’re all caught up.</Text> : null}
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
  myEventsDashboard: { paddingHorizontal: 16, gap: 12 },
  myEventsHeading: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  myEventsHeadingCopy: { flex: 1, gap: 3 },
  dashboardEyebrow: { color: BRAND_GREEN, fontSize: 9, fontWeight: "900", letterSpacing: 1.1 },
  myEventsTitle: { color: INK, fontSize: 22, lineHeight: 27, fontWeight: "900", letterSpacing: -0.45 },
  myEventsSubtitle: { color: MUTED, fontSize: 10, lineHeight: 15 },
  browseEventsButton: { minHeight: 38, justifyContent: "center", paddingHorizontal: 12, borderRadius: 10, backgroundColor: BRAND_GREEN },
  browseEventsButtonText: { color: WHITE, fontSize: 10, fontWeight: "900" },
  organizerPromo: { flexDirection: "row", alignItems: "center", gap: 9, padding: 11, borderRadius: 14, borderWidth: 1, borderColor: "#DCE9DE", backgroundColor: "#EEF5EF" },
  organizerPromoIcon: { width: 34, height: 34, borderRadius: 11, alignItems: "center", justifyContent: "center", backgroundColor: "#DCEBDD" },
  organizerPromoIconText: { fontSize: 17 },
  organizerPromoCopy: { flex: 1, minWidth: 0, gap: 2 },
  organizerPromoTitle: { color: BRAND_DARK, fontSize: 10, fontWeight: "900" },
  organizerPromoDescription: { color: MUTED, fontSize: 8, lineHeight: 12 },
  organizerPromoButton: { minHeight: 34, alignItems: "center", justifyContent: "center", paddingHorizontal: 9, borderRadius: 9, backgroundColor: BRAND_GREEN },
  organizerPromoButtonText: { color: WHITE, fontSize: 8, fontWeight: "900" },
  dashboardStatsRow: { flexDirection: "row", gap: 8 },
  dashboardStatCard: { flex: 1, minHeight: 66, justifyContent: "center", alignItems: "center", gap: 4, borderRadius: 13, borderWidth: 1, borderColor: BORDER, backgroundColor: WHITE },
  dashboardStatValue: { color: BRAND_DARK, fontSize: 19, fontWeight: "900" },
  dashboardStatLabel: { color: MUTED, fontSize: 7, fontWeight: "900", letterSpacing: 0.65 },
  dashboardCard: { padding: 13, borderRadius: 15, borderWidth: 1, borderColor: BORDER, backgroundColor: WHITE, gap: 10 },
  dashboardCardHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  dashboardCardTitle: { color: INK, fontSize: 13, fontWeight: "900" },
  dashboardCardSubtitle: { color: MUTED, fontSize: 9, lineHeight: 13, marginTop: 2 },
  dashboardSectionIcon: { fontSize: 19 },
  dashboardLink: { color: BRAND_GREEN, fontSize: 10, fontWeight: "900" },
  dashboardLoadingRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  dashboardMuted: { color: MUTED, fontSize: 10, lineHeight: 15 },
  dashboardEmpty: { paddingVertical: 5, gap: 6 },
  dashboardEmptyTitle: { color: INK, fontSize: 12, fontWeight: "900" },
  dashboardErrorPlaceholder: { color: "#9A342D", fontSize: 10 },
  nextEventContent: { gap: 6 },
  nextEventName: { color: BRAND_DARK, fontSize: 16, lineHeight: 20, fontWeight: "900" },
  nextEventMeta: { color: MUTED, fontSize: 10, lineHeight: 15 },
  nextEventTicket: { color: "#738178", fontSize: 9, fontWeight: "700" },
  nextEventButton: { minHeight: 38, alignSelf: "flex-start", justifyContent: "center", paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: "#EAF2EB", marginTop: 2 },
  nextEventButtonText: { color: BRAND_GREEN, fontSize: 10, fontWeight: "900" },
  calendarMonthControls: { flexDirection: "row", alignItems: "center", gap: 6 },
  calendarMonthButton: { width: 27, height: 27, borderRadius: 8, alignItems: "center", justifyContent: "center", backgroundColor: "#F1F5F1" },
  calendarMonthButtonText: { color: BRAND_GREEN, fontSize: 19, fontWeight: "900", lineHeight: 22 },
  calendarMonthLabel: { minWidth: 84, textAlign: "center", color: INK, fontSize: 9, fontWeight: "900" },
  calendarWeekRow: { flexDirection: "row" },
  calendarWeekday: { width: "14.285%", textAlign: "center", color: MUTED, fontSize: 8, fontWeight: "900", paddingVertical: 4 },
  calendarGrid: { flexDirection: "row", flexWrap: "wrap" },
  calendarDayCell: { width: "14.285%", minHeight: 38, alignItems: "center", justifyContent: "center", gap: 2 },
  calendarDayCircle: { width: 26, height: 26, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  calendarDayToday: { backgroundColor: BRAND_DARK },
  calendarDayHasEvent: { borderWidth: 1, borderColor: "#D8B43B", backgroundColor: "#FFF7D8" },
  calendarDayText: { color: INK, fontSize: 9, fontWeight: "700" },
  calendarDayTodayText: { color: WHITE },
  calendarDayEventText: { color: BRAND_DARK, fontWeight: "900" },
  calendarEventDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: BRAND_GREEN },
  calendarNoDot: { width: 4, height: 4 },
  calendarLegend: { flexDirection: "row", alignItems: "center", gap: 6 },
  calendarLegendDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: BRAND_GREEN },
  calendarLegendText: { color: MUTED, fontSize: 8, fontWeight: "700" },
  reminderRow: { minHeight: 49, flexDirection: "row", alignItems: "center", gap: 10, borderTopWidth: 1, borderTopColor: "#EFF2EF", paddingTop: 8 },
  reminderDateBadge: { width: 39, height: 39, borderRadius: 11, alignItems: "center", justifyContent: "center", backgroundColor: "#FFF4D5" },
  reminderDateDay: { color: BRAND_DARK, fontSize: 14, lineHeight: 16, fontWeight: "900" },
  reminderDateMonth: { color: "#8A6A12", fontSize: 7, fontWeight: "900" },
  reminderCopy: { flex: 1, minWidth: 0, gap: 3 },
  reminderTitle: { color: INK, fontSize: 10, fontWeight: "900" },
  reminderMeta: { color: MUTED, fontSize: 8 },
  registrationFilters: { flexDirection: "row", gap: 7 },
  registrationFilter: { minHeight: 32, alignItems: "center", justifyContent: "center", paddingHorizontal: 10, borderRadius: 99, borderWidth: 1, borderColor: BORDER, backgroundColor: "#FAFCFA" },
  registrationFilterActive: { backgroundColor: BRAND_DARK, borderColor: BRAND_DARK },
  registrationFilterText: { color: MUTED, fontSize: 9, fontWeight: "800" },
  registrationFilterTextActive: { color: WHITE },
  registrationRow: { minHeight: 60, flexDirection: "row", alignItems: "center", gap: 7, borderTopWidth: 1, borderTopColor: "#EFF2EF", paddingVertical: 9 },
  registrationRowCopy: { flex: 1, minWidth: 0, gap: 3 },
  registrationRowTitle: { color: INK, fontSize: 10, fontWeight: "900" },
  registrationRowMeta: { color: MUTED, fontSize: 8 },
  registrationRowReference: { color: "#87938D", fontSize: 8, fontFamily: "monospace" },
  registrationStatus: { maxWidth: 85, paddingHorizontal: 7, paddingVertical: 4, borderRadius: 99 },
  registrationStatusGood: { backgroundColor: "#E7F3E9" },
  registrationStatusOther: { backgroundColor: "#FFF3D6" },
  registrationStatusText: { fontSize: 7, fontWeight: "900", textTransform: "capitalize" },
  registrationStatusTextGood: { color: BRAND_GREEN },
  registrationStatusTextOther: { color: "#88651A" },
  registrationChevron: { color: BRAND_GREEN, fontSize: 17, fontWeight: "900" },
  activityRow: { flexDirection: "row", alignItems: "center", gap: 9, borderTopWidth: 1, borderTopColor: "#EFF2EF", paddingTop: 9 },
  activityIcon: { width: 29, height: 29, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: "#EAF2EB" },
  activityIconText: { color: BRAND_GREEN, fontSize: 13, fontWeight: "900" },
  activityCopy: { flex: 1, minWidth: 0, gap: 3 },
  activityTitle: { color: INK, fontSize: 10, fontWeight: "900" },
  activityMeta: { color: MUTED, fontSize: 8 },
  registrationError: { padding: 12, borderWidth: 1, borderColor: "#F1D6D2", borderRadius: 12, backgroundColor: "#FFF6F5", gap: 5 },
  registrationErrorTitle: { color: "#9A342D", fontSize: 11, fontWeight: "900" },
  registrationErrorText: { color: "#8D4943", fontSize: 9, lineHeight: 14 },
  registrationRetryButton: { alignSelf: "flex-start", marginTop: 3, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: "#F5E3E0", borderRadius: 8 },
  registrationRetryText: { color: "#9A342D", fontSize: 9, fontWeight: "900" },

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

  geminiPage: { backgroundColor: "#F5F6F2", paddingBottom: 28 },
  geminiPageContent: { paddingHorizontal: 18, paddingTop: 12, paddingBottom: 8, gap: 14 },
  geminiTopHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 2 },
  geminiBrandRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  geminiEmblemOuter: { width: 34, height: 34, borderRadius: 17, backgroundColor: "#F5B700", alignItems: "center", justifyContent: "center" },
  geminiEmblemInner: { width: 28, height: 28, borderRadius: 14, backgroundColor: "#0E5B36", alignItems: "center", justifyContent: "center" },
  geminiEmblemMark: { color: "#F5B700", fontSize: 15, fontWeight: "900", marginTop: -2 },
  geminiBrandTitle: { fontSize: 22, fontWeight: "800", color: "#0E5B36", letterSpacing: -0.4 },
  geminiTopActions: { flexDirection: "row", alignItems: "center", gap: 10 },
  geminiCircleButton: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#E6EAE4", alignItems: "center", justifyContent: "center" },
  geminiCircleButtonMint: { backgroundColor: "#E6EFE8", borderColor: "transparent" },
  geminiActionGlyph: { color: "#0E5B36", fontSize: 20, fontWeight: "700" },
  geminiBellIcon: { width: 22, height: 23, alignItems: "center", justifyContent: "center" },
  geminiBellDome: { width: 14, height: 14, borderWidth: 1.7, borderColor: "#0E5B36", borderBottomWidth: 1, borderTopLeftRadius: 8, borderTopRightRadius: 8, borderBottomLeftRadius: 3, borderBottomRightRadius: 3, marginTop: 2 },
  geminiBellBase: { width: 18, height: 2, borderRadius: 2, backgroundColor: "#0E5B36", marginTop: -1 },
  geminiBellClapper: { width: 4, height: 3, borderRadius: 2, backgroundColor: "#0E5B36", marginTop: 1 },
  geminiPersonIcon: { width: 22, height: 22, alignItems: "center", justifyContent: "center" },
  geminiPersonHead: { width: 8, height: 8, borderRadius: 4, borderWidth: 1.7, borderColor: "#0E5B36", marginBottom: 2 },
  geminiPersonShoulders: { width: 17, height: 8, borderWidth: 1.7, borderColor: "#0E5B36", borderBottomWidth: 0, borderTopLeftRadius: 9, borderTopRightRadius: 9 },
  geminiHeroStage: { position: "relative", marginBottom: 4, zIndex: 10 },
  geminiHeroCard: { backgroundColor: "#D6EBDD", borderRadius: 24, borderWidth: 1, borderColor: "rgba(255,255,255,0.85)", paddingHorizontal: 18, paddingTop: 18, paddingBottom: 80, flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 204, overflow: "hidden", position: "relative" },
  geminiHeroGlowOrb: { position: "absolute", top: -32, right: -20, width: 140, height: 140, borderRadius: 70, backgroundColor: "rgba(252,238,226,0.55)" },
  geminiHeroHillBand: { position: "absolute", left: 0, right: 0, bottom: 0, height: 68, backgroundColor: "rgba(30,91,57,0.72)", borderTopLeftRadius: 120, borderTopRightRadius: 80, zIndex: 1 },
  geminiHeroLeft: { flex: 1, justifyContent: "space-between", paddingRight: 8, zIndex: 2 },
  geminiHeroEyebrow: { fontSize: 10, fontWeight: "700", letterSpacing: 1.2, color: "#1F5C3D", marginBottom: 6 },
  geminiHeroTitle: { fontFamily: "serif", fontSize: 25, fontWeight: "700", color: "#093E24", lineHeight: 28, marginBottom: 12 },
  geminiHeroSub: { fontSize: 13, fontWeight: "500", color: "#214A34" },
  geminiHeroGreeting: { fontSize: 10, fontWeight: "600", color: "#214A34", marginTop: 7 },
  geminiHeroIllustration: { width: 118, height: 112, alignItems: "center", justifyContent: "flex-end", position: "relative", zIndex: 2 },
  geminiSunHalo: { position: "absolute", top: 0, left: 20, width: 24, height: 24, borderRadius: 12, backgroundColor: "rgba(245,183,0,0.24)", alignItems: "center", justifyContent: "center" },
  geminiSunDot: { width: 11, height: 11, borderRadius: 5.5, backgroundColor: "#EA8426" },
  geminiSkyline: { flexDirection: "row", alignItems: "flex-end", gap: 5, opacity: 0.35, marginBottom: 8 },
  geminiTower: { width: 12, backgroundColor: "#0E5B36", borderTopLeftRadius: 3, borderTopRightRadius: 3 },
  geminiTravelerRow: { alignItems: "center" },
  geminiTravelerCircle: { width: 56, height: 56, borderRadius: 28, backgroundColor: "#1E5B39", alignItems: "center", justifyContent: "center" },
  geminiTravelerGlyph: { fontSize: 23 },
  geminiFloatingSearch: { position: "absolute", left: 12, right: 12, bottom: 14, zIndex: 25, flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: "rgba(255,255,255,0.88)", borderRadius: 999, borderWidth: 1.5, borderColor: "rgba(255,255,255,0.96)", paddingHorizontal: 16, minHeight: 48, shadowColor: "#082918", shadowOpacity: 0.22, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 6 },
  geminiSearchGlyph: { color: "#093E24", fontSize: 25, lineHeight: 28, fontWeight: "700" },
  geminiSearchInput: { flex: 1, minHeight: 44, fontSize: 13, fontWeight: "600", color: "#082918", paddingVertical: 0 },
  geminiClearSearch: { color: "#093E24", fontSize: 25, fontWeight: "500", paddingHorizontal: 2 },
  geminiScopeTabsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10, marginHorizontal: 10 },
  geminiScopeTab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#DCE4DD" },
  geminiScopeTabActive: { backgroundColor: "#0E5B36", borderColor: "#0E5B36" },
  geminiScopeText: { fontSize: 11, fontWeight: "600", color: "#48524A" },
  geminiScopeTextActive: { color: "#FFFFFF" },
  geminiSection: { gap: 0 },
  geminiSectionTitle: { fontFamily: "serif", fontSize: 20, fontWeight: "700", color: "#122419", marginBottom: 12 },
  geminiServiceGrid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", gap: 10, marginBottom: 2 },
  geminiServiceCard: { width: "48.3%", minHeight: 118, backgroundColor: "#FFFFFF", borderRadius: 18, borderWidth: 1, borderColor: "#E6EAE4", padding: 14, justifyContent: "flex-start" },
  geminiServiceCardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 },
  geminiServiceIconCircle: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  geminiMintIcon: { backgroundColor: "#E8F4EC" },
  geminiPeachIcon: { backgroundColor: "#FCEEE2" },
  geminiServiceIcon: { fontSize: 19 },
  geminiDiagonalArrow: { color: "#4A554C", fontSize: 18, transform: [{ rotate: "0deg" }] },
  geminiServiceTitle: { fontSize: 15, fontWeight: "700", color: "#141915", marginBottom: 2 },
  geminiServiceSubtitle: { fontSize: 11, color: "#6C766E" },
  geminiWebsiteHint: { alignSelf: "flex-start", marginTop: 5, paddingHorizontal: 6, paddingVertical: 3, borderRadius: 6, backgroundColor: "rgba(23,61,40,0.08)" },
  geminiWebsiteHintText: { color: "#0E5B36", fontSize: 7, fontWeight: "900", letterSpacing: 0.5 },
  geminiWalletBanner: { marginHorizontal: 18, backgroundColor: "#0E5B36", borderRadius: 18, padding: 15, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  geminiBannerLeft: { flexDirection: "row", alignItems: "center", gap: 12, flex: 1 },
  geminiWalletIconBox: { width: 44, height: 44, borderRadius: 12, backgroundColor: "rgba(255,255,255,0.16)", alignItems: "center", justifyContent: "center" },
  geminiWalletIcon: { color: "#FFFFFF", fontSize: 27, fontWeight: "700" },
  geminiBannerCopy: { flex: 1 },
  geminiWalletTitle: { fontSize: 16, fontWeight: "700", color: "#FFFFFF", marginBottom: 2 },
  geminiWalletSubtitle: { fontSize: 12, color: "rgba(255,255,255,0.82)" },
  geminiWalletChevron: { color: "#FFFFFF", fontSize: 24, marginLeft: 8 },
  geminiBookingsCard: { marginHorizontal: 18, backgroundColor: "#FFFFFF", borderRadius: 18, borderWidth: 1, borderColor: "#E6EAE4", padding: 14, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  geminiBookingsIcon: { fontSize: 18, color: "#0E5B36" },
  geminiBookingsTitle: { fontSize: 15, fontWeight: "700", color: "#141915", marginBottom: 2 },
  geminiBookingsSubtitle: { fontSize: 11, color: "#6C766E" },
  geminiBookingsChevron: { color: "#6C766E", fontSize: 22 },
  geminiLowerContent: { gap: 20, paddingTop: 2 },
  });
