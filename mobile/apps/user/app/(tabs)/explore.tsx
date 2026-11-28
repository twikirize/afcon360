import React, { useEffect, useMemo, useState } from "react";
import {
  Keyboard,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import {
  ActionButton,
  AppScreen,
  EmptyState,
  PageHeader,
  Panel,
  SectionTitle,
  ServiceTile,
  palette,
} from "@afcon360/mobile-ui";

const SITE = "https://www.pamoja.space";

const SEARCHABLE_SERVICES = [
  {
    id: "rides",
    category: "Transport",
    title: "Rides",
    description: "On-demand transport with resolved locations, signed fares and server-certified payment options.",
    symbol: "🚘",
    actionLabel: "Book a ride",
    searchTerms: [
      "transport", "ride", "rides", "taxi", "cab", "car", "driver",
      "airport", "airport transfer", "airport shuttle", "shuttle",
    ],
  },
  {
    id: "stays",
    category: "Accommodation",
    title: "Stays",
    description: "Discover properties and manage accommodation reservations.",
    symbol: "🏨",
    actionLabel: "Find and book a stay",
    searchTerms: [
      "stay", "stays", "hotel", "hotels", "accommodation", "lodging",
      "room", "rooms", "apartment", "apartments", "guest house",
    ],
  },
  {
    id: "experiences",
    category: "Tourism and experiences",
    title: "Tours and experiences",
    description: "Explore packages and local providers on the AFCON360 website.",
    symbol: "🧭",
    actionLabel: "Explore tourism on website",
    searchTerms: [
      "tour", "tours", "tourism", "experience", "experiences",
      "safari", "safaris", "adventure", "excursion", "excursions",
      "guide", "guides", "trip", "trips",
    ],
  },
  {
    id: "events",
    category: "Tourism and events",
    title: "Events and tickets",
    description: "Discover events, registrations and available ticket journeys.",
    symbol: "🎟️",
    actionLabel: "Discover events and tickets",
    searchTerms: [
      "event", "events", "ticket", "tickets", "football", "soccer",
      "match", "matches", "matchday", "stadium", "concert", "festival",
    ],
  },
] as const;

type ExploreService = (typeof SEARCHABLE_SERVICES)[number];

const SERVICE_SECTIONS = [
  { title: "Transport", ids: ["rides"] },
  { title: "Accommodation", ids: ["stays"] },
  { title: "Tourism and events", ids: ["experiences", "events"] },
] as const;

const SEARCH_STOP_WORDS = new Set([
  "a", "an", "and", "are", "can", "do", "for", "find", "from",
  "i", "in", "is", "me", "my", "near", "of", "on", "or", "please",
  "search", "show", "the", "to", "want", "what", "where", "with",
]);

/**
 * Search only the services the native app currently exposes. This is a
 * service directory, not a fabricated listing of hotels, events or drivers.
 */
function getMatchingServices(query: string): ExploreService[] {
  const tokens = (query.toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [])
    .filter(token => token.length > 1 && !SEARCH_STOP_WORDS.has(token));

  if (!tokens.length) return [];

  return SEARCHABLE_SERVICES.filter(service => {
    const corpus = [
      service.category,
      service.title,
      ...service.searchTerms,
    ].join(" ").toLocaleLowerCase();

    return tokens.some(token =>
      corpus.split(/\s+/).some(word =>
        word.startsWith(token) || token.startsWith(word)
      )
    );
  });
}

export default function Explore() {
  const router = useRouter();
  const params = useLocalSearchParams<{ q?: string | string[] }>();
  const routeQuery = Array.isArray(params.q)
    ? (params.q[0] ?? "")
    : (params.q ?? "");
  const [searchQuery, setSearchQuery] = useState(routeQuery);

  // Keep the visible input synchronized when Home submits a new q parameter
  // while Explore is already mounted in the tab navigator.
  useEffect(() => {
    setSearchQuery(routeQuery);
  }, [routeQuery]);

  const activeQuery = searchQuery.trim();
  const matchingServices = useMemo(
    () => getMatchingServices(activeQuery),
    [activeQuery]
  );

  const openService = (service: ExploreService) => {
    switch (service.id) {
      case "rides":
        router.push("/(service)/ride" as never);
        break;
      case "stays":
        router.push("/(service)/stays" as never);
        break;
      case "experiences":
        void WebBrowser.openBrowserAsync(SITE + "/tourism");
        break;
      case "events":
        router.push("/(service)/events" as never);
        break;
    }
  };

  const renderService = (service: ExploreService) => (
    <React.Fragment key={service.id}>
      <ServiceTile
        title={service.title}
        description={service.description}
        symbol={service.symbol}
      />
      <ActionButton
        label={service.actionLabel}
        onPress={() => openService(service)}
      />
    </React.Fragment>
  );

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Explore"
        title="Make more of the journey."
        description="Search the AFCON360 service directory, then open the ride, stay, event or experience journey you need."
      />

      <Panel style={styles.searchPanel}>
        <View style={styles.searchField}>
          <Text style={styles.searchIcon}>⌕</Text>
          <TextInput
            value={searchQuery}
            onChangeText={setSearchQuery}
            onSubmitEditing={Keyboard.dismiss}
            placeholder="Search stays, transport, events..."
            placeholderTextColor={palette.muted}
            style={styles.searchInput}
            returnKeyType="search"
            autoCorrect={false}
            accessibilityLabel="Search AFCON360 services"
            accessibilityHint="Search rides, hotels, events, tickets, tours and experiences."
          />
          {searchQuery.length > 0 ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Clear search"
              hitSlop={8}
              onPress={() => setSearchQuery("")}
              style={styles.clearButton}
            >
              <Text style={styles.clearText}>×</Text>
            </Pressable>
          ) : null}
        </View>
        <Text style={styles.searchHint}>
          {activeQuery
            ? matchingServices.length === 1
              ? "1 matching service"
              : matchingServices.length + " matching services"
            : "Search rides, hotels, airport transfers, events, tickets, tours or safaris."}
        </Text>
      </Panel>

      {activeQuery ? (
        <Panel>
          <SectionTitle>Search results</SectionTitle>
          {matchingServices.length > 0 ? (
            <View style={styles.results}>
              {matchingServices.map(renderService)}
            </View>
          ) : (
            <EmptyState
              title={"No services found for “" + activeQuery + "”"}
              description="Try rides, transport, hotels, stays, airport transfers, events, tickets, tours or safaris."
            />
          )}
        </Panel>
      ) : (
        <>
          {SERVICE_SECTIONS.map(section => (
            <Panel key={section.title}>
              <SectionTitle>{section.title}</SectionTitle>
              <View style={styles.results}>
                {section.ids.map(id => {
                  const service = SEARCHABLE_SERVICES.find(item => item.id === id);
                  return service ? renderService(service) : null;
                })}
              </View>
            </Panel>
          ))}
        </>
      )}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  searchPanel: {
    gap: 9,
  },
  searchField: {
    minHeight: 48,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 14,
    backgroundColor: palette.surface,
    paddingHorizontal: 13,
  },
  searchIcon: {
    color: palette.green,
    fontSize: 25,
    lineHeight: 29,
    fontWeight: "700",
  },
  searchInput: {
    flex: 1,
    minWidth: 0,
    paddingVertical: 10,
    color: palette.ink,
    fontSize: 14,
  },
  clearButton: {
    width: 30,
    height: 30,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 15,
    backgroundColor: "#EDF1EF",
  },
  clearText: {
    color: palette.ink,
    fontSize: 22,
    lineHeight: 24,
  },
  searchHint: {
    color: palette.muted,
    fontSize: 12,
    lineHeight: 17,
  },
  results: {
    gap: 10,
  },
});
