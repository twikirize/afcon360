import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import { PamojaActionButton as ActionButton } from "../PamojaScreen";
import { PlaceSearchField } from "./PlaceSearchField";
import { ServiceTypeSelector } from "./ServiceTypeSelector";
import { ScheduleSelector } from "./ScheduleSelector";
import { Map } from "../maps/MapProvider";
import { validLocalSchedule } from "./utils";
import type { Place, RideSchedule, RideServiceType, RideVip } from "./types";

type RideWhereProps = {
  pickup: Place | null;
  dropoff: Place | null;
  pickupText: string;
  dropoffText: string;
  serviceType: RideServiceType;
  vip: RideVip;
  schedule: RideSchedule;
  scheduledAt: string;
  locationBusy: boolean;
  locationMessage: string | null;
  reverseAttribution: string | null;
  onPickupTextChange: (value: string) => void;
  onDropoffTextChange: (value: string) => void;
  onPickupSelect: (place: Place) => void;
  onDropoffSelect: (place: Place) => void;
  onUseCurrentLocation: () => void;
  onSwapLocations: () => void;
  onServiceTypeChange: (serviceType: RideServiceType, vip: RideVip) => void;
  onScheduleChange: (schedule: RideSchedule) => void;
  onScheduledAtChange: (value: string) => void;
  onContinue: () => void;
  resetCommitment: () => void;
  /** Map taps and pin drags, resolved by the screen (reverse geocode). */
  onMapMessage: (message: any) => void;
  popularDestinations?: string[];
};

/**
 * The rider's first screen, laid out the way Uber / Go Dudu / SafeBoda do it:
 * search card on top, map filling the middle, one bottom sheet that holds
 * service type, when, popular destinations and a CTA that never scrolls away.
 *
 * The previous stacked-cards page pushed the map below the fold, so a rider
 * scrolled past a half-visible "See Ride Options" button to reach it.
 */
export function RideWhere({
  pickup,
  dropoff,
  pickupText,
  dropoffText,
  serviceType,
  vip,
  schedule,
  scheduledAt,
  locationBusy,
  locationMessage,
  reverseAttribution,
  onPickupTextChange,
  onDropoffTextChange,
  onPickupSelect,
  onDropoffSelect,
  onUseCurrentLocation,
  onSwapLocations,
  onServiceTypeChange,
  onScheduleChange,
  onScheduledAtChange,
  onContinue,
  resetCommitment,
  onMapMessage,
  popularDestinations = [
    "Mandela National Stadium, Namboole",
    "Lugogo Cricket Oval, Kampala",
    "Nile Independence Stadium",
  ],
}: RideWhereProps) {
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapReloadKey, setMapReloadKey] = useState(0);

  const handleMapReady = useCallback(() => {
    setMapReady(true);
  }, []);

  const handleMapError = useCallback((error: string) => {
    setMapReady(false);
    setMapError(error);
  }, []);

  const handleMapMessage = useCallback((message: any) => {
    if (message.type === "map_ready") {
      setMapReady(true);
      setMapError(null);
      return;
    }
    onMapMessage(message);
  }, [onMapMessage]);

  const retryMap = useCallback(() => {
    setMapError(null);
    setMapReady(false);
    setMapReloadKey(key => key + 1);
  }, []);

  const handlePopularDestination = useCallback((name: string) => {
    onDropoffTextChange(name);
    resetCommitment();
  }, [onDropoffTextChange, resetCommitment]);

  const scheduleValid = schedule === "now" || validLocalSchedule(scheduledAt);
  const canContinue = !!pickup && !!dropoff && scheduleValid;

  // The CTA states why it is disabled and what happens next. A grey button
  // with no explanation is the single most common "nothing happens" report.
  const ctaHint = !pickup && !dropoff
    ? "Select pickup + destination to continue. Est. fare appears next."
    : !pickup
      ? "Select a pickup point to continue."
      : !dropoff
        ? "Select a destination to continue."
        : !scheduleValid
          ? "Enter a valid pickup date and time (YYYY-MM-DDTHH:mm)."
          : "Fare and ride options are shown next. Nothing is charged yet.";

  return (
    <View style={styles.root}>
      <View style={styles.searchCard}>
        <ScrollView
          style={styles.searchScroll}
          contentContainerStyle={styles.searchScrollContent}
          keyboardShouldPersistTaps="handled"
          nestedScrollEnabled
          showsVerticalScrollIndicator={false}
        >
          <PlaceSearchField
            label="Pickup"
            value={pickupText}
            placeholder="Search pickup"
            onValue={onPickupTextChange}
            onSelect={onPickupSelect}
            accessory={
              // Same action, on the row it belongs to: the full-width button
              // it replaces cost 42dp of a 360dp screen.
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Use my current location as pickup"
                disabled={locationBusy}
                onPress={onUseCurrentLocation}
                style={styles.locationLink}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                {locationBusy ? (
                  <ActivityIndicator color={colors.brand.green} size="small" />
                ) : (
                  <Text style={styles.locationLinkText}>◎ Use my current location</Text>
                )}
              </Pressable>
            }
          />

          <View style={styles.swapRow}>
            <View style={styles.swapLine} />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Swap pickup and destination"
              onPress={onSwapLocations}
              style={styles.swapButton}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            >
              <Text style={styles.swapText}>↕</Text>
            </Pressable>
            <View style={styles.swapLine} />
          </View>

          <PlaceSearchField
            label="Destination"
            value={dropoffText}
            placeholder="Search destination"
            onValue={onDropoffTextChange}
            onSelect={onDropoffSelect}
          />

          {(pickup || dropoff) && (
            <Text style={styles.sourceText}>
              {[pickup, dropoff].filter(Boolean).map(place => {
                const label = place === pickup ? "Pickup" : "Destination";
                const source = place!.source === "gps"
                  ? "current device location"
                  : place!.source === "map"
                    ? "selected on map"
                    : "verified search result";
                return label + ": " + source;
              }).join("  ·  ")}
            </Text>
          )}
        </ScrollView>
      </View>

      <View style={styles.mapArea}>
        {mapError ? (
          <View style={styles.mapFallback} accessibilityRole="summary">
            <Text style={styles.mapFallbackTitle}>Map unavailable</Text>
            <Text style={styles.mapFallbackText}>
              Booking still works. Search for a place or use your current location, then
              tap "See Ride Options".
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={retryMap}
              style={styles.mapRetry}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Text style={styles.mapRetryText}>Retry map</Text>
            </Pressable>
          </View>
        ) : (
          <Map
            key={mapReloadKey}
            pickup={pickup}
            dropoff={dropoff}
            onMapMessage={handleMapMessage}
            onMapReady={handleMapReady}
            onMapError={handleMapError}
            style={styles.map}
          />
        )}
        {!mapReady && !mapError && (
          <View style={styles.mapLoading} pointerEvents="none">
            <Text style={styles.mapLoadingText}>Loading map…</Text>
          </View>
        )}
      </View>

      <Text style={styles.mapFootnote} numberOfLines={1}>
        © OpenStreetMap contributors · straight-line distance, not road distance
      </Text>

      <View style={styles.sheet}>
        <ScrollView
          style={styles.sheetScroll}
          contentContainerStyle={styles.sheetScrollContent}
          keyboardShouldPersistTaps="handled"
          nestedScrollEnabled
          showsVerticalScrollIndicator={false}
        >
          <ServiceTypeSelector
            serviceType={serviceType}
            vip={vip}
            onSelect={onServiceTypeChange}
          />

          <ScheduleSelector
            schedule={schedule}
            scheduledAt={scheduledAt}
            onScheduleChange={onScheduleChange}
            onScheduledAtChange={onScheduledAtChange}
            resetCommitment={resetCommitment}
          />

          <Text style={styles.label}>Popular destinations</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chips}
            keyboardShouldPersistTaps="handled"
          >
            {popularDestinations.map((name, index) => (
              <Pressable
                key={name}
                accessibilityRole="button"
                accessibilityLabel={"Search " + name + " as destination"}
                onPress={() => handlePopularDestination(name)}
                style={styles.chip}
                hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
              >
                <Text style={styles.chipText} numberOfLines={1}>
                  {["Namboole Stadium", "Lugogo Oval", "Nile Independence"][index] ?? name}
                </Text>
              </Pressable>
            ))}
          </ScrollView>

          {locationMessage && (
            <Text style={styles.statusText}>{locationMessage}</Text>
          )}
          {reverseAttribution && (
            <Text style={styles.attribution}>{reverseAttribution}</Text>
          )}
        </ScrollView>

        <View style={styles.ctaBar}>
          <Text style={styles.ctaHint}>{ctaHint}</Text>
          <ActionButton
            label="See Ride Options"
            disabled={!canContinue}
            onPress={onContinue}
          />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, gap: spacing.sm, paddingHorizontal: 12, paddingBottom: 8 },

  searchCard: {
    backgroundColor: colors.surface.white,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.lg,
    paddingHorizontal: spacing.md,
    paddingTop: 10,
    paddingBottom: spacing.sm,
  },
  // Capped in dp: the two fields stay fully visible, and a list of
  // suggestions scrolls inside the card instead of pushing the map and the
  // sticky CTA off a 360dp phone.
  searchScroll: { flexGrow: 0, flexShrink: 1, maxHeight: 236 },
  searchScrollContent: { gap: 2 },

  swapRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  swapLine: { flex: 1, height: 1, backgroundColor: colors.border },
  swapButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.brand.greenSoft,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.brand.green,
  },
  swapText: { color: colors.brand.green, fontSize: 18, fontWeight: "800", lineHeight: 22 },

  sourceText: {
    color: colors.text.ink,
    fontSize: 10,
    fontWeight: "600",
    marginTop: 2,
  },
  locationLink: { minHeight: 24, justifyContent: "center" },
  locationLinkText: { color: colors.brand.green, fontWeight: "800", fontSize: 11 },

  mapArea: {
    flex: 1,
    minHeight: 132,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
    backgroundColor: "#dfe7e0",
  },
  map: { flex: 1 },
  mapLoading: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 8,
    alignItems: "center",
  },
  mapLoadingText: {
    color: colors.text.ink,
    fontSize: 11,
    fontWeight: "700",
    backgroundColor: "rgba(255,255,255,0.92)",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radii.pill,
    overflow: "hidden",
  },
  mapFallback: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.lg,
    gap: spacing.xs,
    backgroundColor: colors.surface.canvas,
  },
  mapFallbackTitle: { color: colors.text.ink, fontSize: 14, fontWeight: "800" },
  mapFallbackText: {
    color: colors.text.ink,
    fontSize: 11,
    lineHeight: 16,
    textAlign: "center",
  },
  mapRetry: {
    marginTop: spacing.xs,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radii.pill,
    backgroundColor: colors.brand.greenSoft,
    borderWidth: 1,
    borderColor: colors.brand.green,
  },
  mapRetryText: { color: colors.brand.green, fontSize: 12, fontWeight: "800" },

  mapFootnote: {
    color: colors.text.muted,
    fontSize: 9,
    marginTop: 2,
    paddingHorizontal: 2,
  },

  sheet: {
    flexShrink: 1,
    backgroundColor: colors.surface.white,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.xl,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    gap: spacing.xs,
  },
  sheetScroll: { flexGrow: 0, flexShrink: 1 },
  sheetScrollContent: { gap: 2 },

  label: {
    color: colors.text.ink,
    fontWeight: "700",
    fontSize: 12,
    marginTop: spacing.sm,
  },
  chips: { flexDirection: "row", gap: spacing.sm, paddingVertical: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radii.pill,
    backgroundColor: colors.surface.canvas,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipText: { color: colors.text.ink, fontSize: 12, fontWeight: "700" },

  statusText: {
    color: colors.text.ink,
    fontSize: typography.caption.fontSize,
    lineHeight: typography.caption.lineHeight,
    fontWeight: "600",
  },
  attribution: { color: colors.text.muted, fontSize: 9 },

  ctaBar: { gap: 4, paddingTop: 2 },
  ctaHint: {
    // Dark, not muted: this line is the reason the button is grey.
    color: colors.text.ink,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "600",
  },
});

export default RideWhere;
