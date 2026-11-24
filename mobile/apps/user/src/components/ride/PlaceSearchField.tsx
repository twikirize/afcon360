import React, { useEffect, useRef, useState } from "react";
import { View, Text, TextInput, Pressable, ActivityIndicator, StyleSheet, Keyboard } from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import { authClient } from "../../services/api";
import type { Place, GeocodeCandidate, PlaceSearchState } from "./types";
import {
  normalizePlaceSearchQuery,
  readPlaceSearchCache,
  writePlaceSearchCache,
  EMPTY_PLACE_SEARCH_STATE,
  validGeocodeCandidate,
  friendlyError,
} from "./utils";

type PlaceSearchFieldProps = {
  label: string;
  value: string;
  placeholder: string;
  onValue: (value: string) => void;
  onSelect: (place: Place) => void;
};

export function PlaceSearchField({ label, value, placeholder, onValue, onSelect }: PlaceSearchFieldProps) {
  const [searchState, setSearchState] = useState<PlaceSearchState>(EMPTY_PLACE_SEARCH_STATE);
  const selectedLabelQuery = useRef<string | null>(null);
  const query = value.trim().replace(/\s+/g, " ");
  const queryKey = normalizePlaceSearchQuery(query);
  const visibleState = searchState.query === queryKey
    ? searchState
    : { ...EMPTY_PLACE_SEARCH_STATE, query: queryKey };

  useEffect(() => {
    if (query.length < 2) {
      setSearchState({ ...EMPTY_PLACE_SEARCH_STATE, query: queryKey });
      return;
    }

    if (selectedLabelQuery.current === queryKey) {
      selectedLabelQuery.current = null;
      setSearchState({ ...EMPTY_PLACE_SEARCH_STATE, query: queryKey });
      return;
    }

    const cached = readPlaceSearchCache(queryKey);
    if (cached) {
      setSearchState({
        query: queryKey,
        status: "success",
        results: cached.results,
        attribution: cached.attribution,
        error: null
      });
      return;
    }

    let active = true;
    const controller = new AbortController();
    setSearchState({
      query: queryKey,
      status: "loading",
      results: [],
      attribution: null,
      error: null
    });

    const timer = setTimeout(() => {
      void authClient.request<{
        success?: unknown;
        results?: unknown;
        attribution?: unknown;
      }>(
        "/geo/api/geocode?q=" + encodeURIComponent(query) + "&limit=5",
        { signal: controller.signal }
      ).then((data) => {
          if (!active) return;
          if (data.success !== true || !Array.isArray(data.results)) {
            throw new Error("AFCON360 could not read the place-search results. Search again.");
          }

          const candidates = data.results.filter(validGeocodeCandidate);
          if (data.results.length > 0 && candidates.length === 0) {
            throw new Error("AFCON360 could not verify the returned place results. Search again.");
          }

          const attribution = typeof data.attribution === "string" ? data.attribution : null;
          writePlaceSearchCache(queryKey, candidates, attribution);
          setSearchState({
            query: queryKey,
            status: "success",
            results: candidates,
            attribution,
            error: null
          });
        }).catch((error) => {
          if (!active || controller.signal.aborted) return;
          setSearchState({
            query: queryKey,
            status: "error",
            results: [],
            attribution: null,
            error: friendlyError(error, "Place search is temporarily unavailable. Check your connection and try again.")
          });
        });
    }, 300);

    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, queryKey]);

  const selectCandidate = (candidate: GeocodeCandidate) => {
    const geocode = { ...candidate };
    selectedLabelQuery.current = normalizePlaceSearchQuery(candidate.label);
    setSearchState({ ...EMPTY_PLACE_SEARCH_STATE, query: selectedLabelQuery.current });
    onSelect({ ...geocode, source: "search", geocode });
    Keyboard.dismiss();
  };

  return (
    <View style={styles.fieldGroup}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={nextValue => {
          selectedLabelQuery.current = null;
          onValue(nextValue);
        }}
        onSubmitEditing={() => {
          if (visibleState.status === "success" && visibleState.results[0]) {
            selectCandidate(visibleState.results[0]);
          }
        }}
        style={styles.input}
        placeholder={placeholder}
        placeholderTextColor={colors.text.muted}
        accessibilityLabel={label}
        accessibilityHint="Enter at least two characters, then choose a verified place from the suggestions."
        autoCorrect={false}
        returnKeyType="search"
      />
      {visibleState.status === "loading" ? (
        <View style={styles.searchStatus}>
          <ActivityIndicator color={colors.brand.green} />
          <Text style={styles.helperText}>Searching AFCON360 places…</Text>
        </View>
      ) : null}
      {visibleState.status === "error" ? (
        <Text style={styles.errorText} accessibilityLiveRegion="polite">
          {visibleState.error ?? "Place search is temporarily unavailable. Check your connection and try again."}
        </Text>
      ) : null}
      {visibleState.status === "success" && visibleState.results.length === 0 ? (
        <Text style={styles.helperText} accessibilityLiveRegion="polite">
          No matching places were found. Try a nearby landmark or a more specific address.
        </Text>
      ) : null}
      {visibleState.status === "success" && visibleState.results.length > 0 ? (
        <View style={styles.searchResults}>
          {visibleState.results.map((place, index) => (
            <Pressable
              key={place.provider + ":" + (place.osm_type ?? "") + ":" +
                (place.osm_id ?? place.latitude + "," + place.longitude) + ":" + index}
              accessibilityRole="button"
              accessibilityLabel={place.label}
              accessibilityHint={"Select this result as your " + label.toLowerCase() + "."}
              onPress={() => selectCandidate(place)}
              style={styles.searchResult}
            >
              <Text style={styles.searchResultTitle}>{place.label}</Text>
              <Text style={styles.helperText}>{place.provider}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      {visibleState.status === "success" && visibleState.attribution ? (
        <Text style={styles.attribution}>{visibleState.attribution}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  fieldGroup: { gap: spacing.sm },
  fieldLabel: { color: colors.text.ink, fontWeight: "700", fontSize: 13 },
  input: {
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 13,
    paddingHorizontal: 12,
    paddingVertical: 11,
    color: colors.text.ink,
    fontSize: 15,
  },
  searchStatus: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginTop: spacing.xs },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight },
  errorText: { color: colors.status.error, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight },
  searchResults: { gap: spacing.xs, marginTop: spacing.xs },
  searchResult: { padding: spacing.sm, backgroundColor: colors.surface.canvas, borderRadius: radii.md, borderWidth: 1, borderColor: colors.border },
  searchResultTitle: { color: colors.text.ink, fontSize: 14, fontWeight: "700" },
  attribution: { color: colors.text.muted, fontSize: 10, marginTop: spacing.xs },
});

export default PlaceSearchField;