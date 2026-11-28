import React, { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from "react-native";
import { BlurTargetView } from "expo-blur";
import Svg, { Circle, Path } from "react-native-svg";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import { GlassView } from "../GlassView";
import { Afcon360Brand } from "./Afcon360Brand";
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
  onMapMessage: (message: any) => void;
  popularDestinations?: string[];
};

function LocationPin({ color }: { color: string }) {
  return (
    <Svg width={21} height={24} viewBox="0 0 24 28" fill="none">
      <Path
        d="M12 26s9-8.4 9-15A9 9 0 1 0 3 11c0 6.6 9 15 9 15Z"
        fill={color}
      />
      <Circle cx={12} cy={11} r={3.2} fill="#FFFFFF" />
    </Svg>
  );
}

/** AFCON360 rider picker: brand, floating search, map and fixed booking sheet. */
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
  const { height } = useWindowDimensions();
  const compact = height < 760;
  const veryCompact = height < 680;
  const sheetHeight = veryCompact ? 260 : compact ? 282 : height < 860 ? 304 : 324;
  const searchHeight = veryCompact ? 136 : compact ? 146 : 158;
  const mapOverlap = veryCompact ? 60 : 78;
  const mapTop = 50 + searchHeight - mapOverlap;
  const mapBottom = sheetHeight - mapOverlap;

  const mapBlurTarget = useRef<View | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapReloadKey, setMapReloadKey] = useState(0);

  const handleMapReady = useCallback(() => {
    setMapReady(true);
    setMapError(null);
  }, []);

  const handleMapError = useCallback((error: string) => {
    setMapReady(false);
    setMapError(error);
  }, []);

  const handleMapMessage = useCallback((message: any) => {
    if (message.type === "map_ready" || message.type === "map_tiles_ready") {
      handleMapReady();
      return;
    }
    onMapMessage(message);
  }, [handleMapReady, onMapMessage]);

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
  const canContinue = Boolean(pickup && dropoff && scheduleValid);
  const ctaHint = !pickup && !dropoff
    ? "Select pickup + destination to continue. Your fare appears next."
    : !pickup
      ? "Select a pickup point to continue."
      : !dropoff
        ? "Select a destination to continue."
        : !scheduleValid
          ? "Enter a valid pickup date and time."
          : "Fare and ride options are shown next. Nothing is charged yet.";

  return (
    <View style={styles.root}>
      <BlurTargetView
        ref={mapBlurTarget}
        style={[styles.mapLayer, { top: mapTop, bottom: mapBottom }]}
      >
        {mapError ? (
          <View style={styles.mapFallback} accessibilityRole="summary">
            <Text style={styles.mapFallbackTitle}>Map unavailable</Text>
            <Text style={styles.mapFallbackText}>
              Search for a place or use your current location. You can still request ride options.
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
            testID="ride-request-map"
          />
        )}

        {!mapReady && !mapError ? (
          <View style={styles.mapLoading} pointerEvents="none">
            <Text style={styles.mapLoadingText}>Loading map…</Text>
          </View>
        ) : null}
      </BlurTargetView>

      <View style={styles.overlay} pointerEvents="box-none">
        <Afcon360Brand />

        <GlassView
          radius={23}
          blurAmount={24}
          blurTarget={mapBlurTarget}
          style={[styles.searchCard, { height: searchHeight }]}
          contentStyle={styles.searchGlassContent}
        >
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
              leading={<LocationPin color="#29A96B" />}
              trailing={
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Swap pickup and destination"
                  onPress={onSwapLocations}
                  style={styles.swapButton}
                  hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                >
                  <Text style={styles.swapText}>↕</Text>
                </Pressable>
              }
            />
            <PlaceSearchField
              label="Destination"
              value={dropoffText}
              placeholder="Where to?"
              onValue={onDropoffTextChange}
              onSelect={onDropoffSelect}
              leading={<LocationPin color="#DF645C" />}
            />

            {(pickup || dropoff) ? (
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
            ) : null}
          </ScrollView>
        </GlassView>

        <View style={styles.mapGap} pointerEvents="box-none">
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Use my current location as pickup"
            accessibilityState={{ disabled: locationBusy }}
            disabled={locationBusy}
            onPress={onUseCurrentLocation}
            style={styles.locationButton}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            {locationBusy ? (
              <ActivityIndicator color={colors.brand.emerald} size="small" />
            ) : (
              <Text style={styles.locationArrow}>➤</Text>
            )}
            <Text style={styles.locationButtonText}>
              {locationBusy ? "Locating…" : "Use my current location"}
            </Text>
          </Pressable>
        </View>

        <Text style={styles.mapFootnote} numberOfLines={1}>
          © OpenStreetMap contributors · straight-line distance, not road distance
        </Text>

        <GlassView
          radius={28}
          blurAmount={22}
          blurTarget={mapBlurTarget}
          style={[styles.sheet, { height: sheetHeight }]}
          contentStyle={styles.sheetInner}
        >
          <View style={styles.sheetHandle} />
          <ScrollView
            style={styles.sheetScroll}
            contentContainerStyle={styles.sheetScrollContent}
            keyboardShouldPersistTaps="handled"
            nestedScrollEnabled
            showsVerticalScrollIndicator={false}
          >
            <Text accessibilityRole="header" style={styles.sectionTitle}>Service type</Text>
            <ServiceTypeSelector serviceType={serviceType} vip={vip} onSelect={onServiceTypeChange} />

            <ScheduleSelector
              schedule={schedule}
              scheduledAt={scheduledAt}
              onScheduleChange={onScheduleChange}
              onScheduledAtChange={onScheduledAtChange}
              resetCommitment={resetCommitment}
            />

            <Text accessibilityRole="header" style={styles.sectionTitle}>Popular destinations</Text>
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
                  <Text style={styles.chipIcon}>{["▤", "⚽", "△"][index] ?? "•"}</Text>
                  <Text style={styles.chipText} numberOfLines={1}>
                    {["Namboole Stadium", "Lugogo Oval", "Nile Independence"][index] ?? name}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>

            {locationMessage ? <Text style={styles.statusText}>{locationMessage}</Text> : null}
            {reverseAttribution ? <Text style={styles.attribution}>{reverseAttribution}</Text> : null}
          </ScrollView>

          <View style={styles.ctaBar}>
            <Text style={styles.ctaHint} numberOfLines={2}>{ctaHint}</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: !canContinue }}
              disabled={!canContinue}
              onPress={onContinue}
              style={({ pressed }) => [
                styles.ctaButton,
                !canContinue && styles.ctaButtonDisabled,
                pressed && canContinue && styles.ctaButtonPressed,
              ]}
            >
              <Text style={styles.ctaButtonText}>See Ride Options</Text>
            </Pressable>
          </View>
        </GlassView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, minHeight: 0, backgroundColor: colors.surface.canvas },
  mapLayer: {
    position: "absolute",
    left: 12,
    right: 12,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
    backgroundColor: "#E6ECE8",
  },
  map: { flex: 1 },
  mapLoading: { position: "absolute", left: 0, right: 0, bottom: 9, alignItems: "center" },
  mapLoadingText: {
    color: colors.text.ink,
    fontSize: 11,
    fontWeight: "700",
    backgroundColor: "rgba(255,255,255,0.94)",
    paddingHorizontal: 12,
    paddingVertical: 6,
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
  mapFallbackTitle: { color: colors.text.ink, fontSize: 15, fontWeight: "900" },
  mapFallbackText: { color: colors.text.ink, fontSize: 12, lineHeight: 17, textAlign: "center" },
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

  overlay: {
    flex: 1,
    paddingHorizontal: 12,
    paddingBottom: 7,
    gap: 6,
  },
  searchCard: { flexShrink: 0, minHeight: 132 },
  searchGlassContent: { flex: 1, paddingHorizontal: 13, paddingVertical: 9 },
  searchScroll: { flex: 1, minHeight: 0 },
  searchScrollContent: { gap: 6, paddingBottom: 4 },
  swapButton: {
    width: 34,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F1F8F3",
    borderWidth: 1,
    borderColor: "#CFE8D8",
  },
  swapText: { color: colors.brand.emerald, fontSize: 19, lineHeight: 22, fontWeight: "900" },
  sourceText: { color: colors.text.ink, fontSize: 9, fontWeight: "600", marginTop: 1 },

  mapGap: {
    flex: 1,
    minHeight: 84,
    justifyContent: "flex-end",
    alignItems: "flex-end",
    paddingBottom: 3,
  },
  locationButton: {
    minHeight: 38,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    paddingHorizontal: 13,
    borderRadius: radii.pill,
    backgroundColor: "rgba(255,255,255,0.96)",
    borderWidth: 1,
    borderColor: "rgba(225,232,226,0.96)",
    shadowColor: "#13251A",
    shadowOpacity: 0.12,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 4,
  },
  locationArrow: { color: colors.brand.emerald, fontSize: 16, fontWeight: "900" },
  locationButtonText: { color: colors.text.ink, fontSize: 11, fontWeight: "800" },
  mapFootnote: { color: "#56665B", fontSize: 9, lineHeight: 12, paddingHorizontal: 3, marginTop: -1 },

  sheet: { flexShrink: 0, minHeight: 244 },
  sheetInner: { flex: 1, minHeight: 0, paddingHorizontal: 15, paddingTop: 8, paddingBottom: 10 },
  sheetHandle: {
    alignSelf: "center",
    width: 38,
    height: 4,
    borderRadius: 4,
    backgroundColor: "#C8CEC9",
    marginBottom: 7,
  },
  sheetScroll: { flex: 1, minHeight: 0 },
  sheetScrollContent: { gap: 4, paddingBottom: 8 },
  sectionTitle: {
    color: "#101C16",
    fontSize: 16,
    lineHeight: 21,
    fontWeight: "800",
    marginTop: 3,
    marginBottom: 2,
  },
  chips: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 4, paddingRight: 6 },
  chip: {
    maxWidth: 160,
    minHeight: 32,
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 9,
    paddingVertical: 6,
    borderRadius: 11,
    backgroundColor: "#F0F1F0",
    borderWidth: 1,
    borderColor: "#E5E8E5",
  },
  chipIcon: { color: "#647067", fontSize: 11, fontWeight: "700" },
  chipText: { color: colors.text.ink, fontSize: 10, fontWeight: "700", flexShrink: 1 },
  statusText: { color: colors.text.ink, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, fontWeight: "600" },
  attribution: { color: colors.text.muted, fontSize: 9 },
  ctaBar: {
    flexShrink: 0,
    gap: 5,
    paddingTop: 7,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "rgba(34,63,44,0.12)",
  },
  ctaHint: { color: "#24342A", fontSize: 10, lineHeight: 13, fontWeight: "700" },
  ctaButton: {
    minHeight: 49,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 15,
    backgroundColor: "#0E9F5B",
    paddingHorizontal: 16,
  },
  ctaButtonDisabled: { backgroundColor: "#AEBBB2" },
  ctaButtonPressed: { opacity: 0.86 },
  ctaButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "900" },
});

export default RideWhere;
