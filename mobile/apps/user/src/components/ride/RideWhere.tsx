import React, { useCallback, useEffect, useState } from "react";
import { Alert, ActivityIndicator, Pressable, Text, View, Keyboard } from "react-native";
import { colors, spacing, radii, typography } from "../theme/tokens";
import {
  PamojaActionButton as ActionButton,
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
} from "../PamojaScreen";
import { PlaceSearchField } from "./PlaceSearchField";
import { ServiceTypeSelector } from "./ServiceTypeSelector";
import { ScheduleSelector } from "./ScheduleSelector";
import { Map } from "../maps/MapProvider";
import { validLocalSchedule } from "./utils";
import type { Place, LocationSource } from "./types";

type RideWhereProps = {
  pickup: Place | null;
  dropoff: Place | null;
  pickupText: string;
  dropoffText: string;
  serviceType: "on_demand" | "airport_departure";
  vip: boolean;
  schedule: "now" | "later";
  scheduledAt: string;
  locationBusy: boolean;
  locationMessage: string | null;
  reverseAttribution: string | null;
  mapReady: boolean;
  mapError: string | null;
  onPickupTextChange: (value: string) => void;
  onDropoffTextChange: (value: string) => void;
  onPickupSelect: (place: Place) => void;
  onDropoffSelect: (place: Place) => void;
  onUseCurrentLocation: () => void;
  onSwapLocations: () => void;
  onServiceTypeChange: (serviceType: "on_demand" | "airport_departure", vip: boolean) => void;
  onScheduleChange: (schedule: "now" | "later") => void;
  onScheduledAtChange: (value: string) => void;
  onContinue: () => void;
  resetCommitment: () => void;
  popularDestinations?: string[];
};

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
  mapReady,
  mapError,
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
  popularDestinations = [
    "Mandela National Stadium, Namboole",
    "Lugogo Cricket Oval, Kampala",
    "Nile Independence Stadium"
  ],
}: RideWhereProps) {
  const [mapErrorState, setMapErrorState] = useState<string | null>(mapError);

  useEffect(() => {
    setMapErrorState(mapError);
  }, [mapError]);

  const handleMapMessage = useCallback((message: any) => {
    // Message handling is done by the Map component
  }, []);

  const handleMapReady = useCallback(() => {
    // Handled by the Map component
  }, []);

  const handleMapError = useCallback((error: string) => {
    setMapErrorState(error);
  }, []);

  const handlePopularDestination = (name: string) => {
    onDropoffTextChange(name);
    resetCommitment();
  };

  const canContinue = pickup && dropoff && (schedule === "now" || validLocalSchedule(scheduledAt));

  return (
    <>
      <Panel>
        <SectionTitle>Where are you going?</SectionTitle>
        <View style={styles.routeRow}>
          <View style={styles.routeFields}>
            <PlaceSearchField
              label="Pickup location"
              value={pickupText}
              placeholder="Current location or search an address"
              onValue={onPickupTextChange}
              onSelect={onPickupSelect}
            />
            {pickup && (
              <Text style={styles.sourceText}>
                {pickup.source === "gps" ? "Current device location" :
                  pickup.source === "map" ? "Selected on map" : "Verified place-search result"}
              </Text>
            )}
            <Pressable
              accessibilityRole="button"
              disabled={locationBusy}
              onPress={onUseCurrentLocation}
              style={[styles.locationButton, locationBusy && styles.disabled]}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              {locationBusy ? <ActivityIndicator color={colors.brand.green} /> : <Text style={styles.locationButtonText}>◎  Use my current location</Text>}
            </Pressable>

            <PlaceSearchField
              label="Destination"
              value={dropoffText}
              placeholder="Enter destination"
              onValue={onDropoffTextChange}
              onSelect={onDropoffSelect}
            />
            {dropoff && (
              <Text style={styles.sourceText}>
                {dropoff.source === "gps" ? "Current device location" :
                  dropoff.source === "map" ? "Selected on map" : "Verified place-search result"}
              </Text>
            )}
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Swap pickup and destination"
            onPress={onSwapLocations}
            style={styles.swapButton}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={styles.swapText}>↕</Text>
          </Pressable>
        </View>

        <Text style={styles.label}>Popular destinations</Text>
        <View style={styles.chips}>
          {popularDestinations.map((name, index) => (
            <Pressable
              key={name}
              onPress={() => handlePopularDestination(name)}
              style={styles.chip}
              hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
            >
              <Text style={styles.chipText}>
                {["Namboole Stadium", "Lugogo Oval", "Nile Independence"][index]}
              </Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Service type</Text>
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

        {locationMessage && <Text style={styles.helperText}>{locationMessage}</Text>}
        {reverseAttribution && <Text style={styles.attribution}>{reverseAttribution}</Text>}

        <ActionButton
          label="See Ride Options"
          disabled={!canContinue}
          onPress={onContinue}
        />
        <Text style={styles.helperText}>Choose both locations by verified search, GPS or the map before requesting a fare.</Text>
      </Panel>

      <Panel>
        <SectionTitle>Choose pickup and destination on the map</SectionTitle>
        <Text style={styles.helperText}>Tap once to place pickup, then tap again for destination. Drag either pin to adjust it. When both pins are set, tapping near one moves that pin.</Text>
        <View style={styles.mapFrame}>
          <Map
            pickup={pickup}
            dropoff={dropoff}
            onMapMessage={handleMapMessage}
            onMapReady={handleMapReady}
            onMapError={handleMapError}
            style={{ width: "100%", height: 300 }}
          />
        </View>
        {!mapReady && (
          <View style={styles.mapOverlay}>
            <ActivityIndicator color={colors.brand.green} />
            <Text style={styles.helperText}>Loading map…</Text>
          </View>
        )}
        {mapErrorState && <Text style={styles.errorText}>{mapErrorState}</Text>}
        <Text style={styles.attribution}>Map data © OpenStreetMap contributors. Distance is a straight-line estimate, not road distance.</Text>
        <View style={styles.selectedRoute}>
          <Text style={styles.selectedRouteText}>Pickup: {pickup?.label ?? "Not selected"}</Text>
          <Text style={styles.selectedRouteText}>Destination: {dropoff?.label ?? "Not selected"}</Text>
        </View>
      </Panel>
    </>
  );
}

const styles = StyleSheet.create({
  routeRow: { flexDirection: "row", gap: spacing.md },
  routeFields: { flex: 1, gap: spacing.md },
  sourceText: { color: colors.text.muted, fontSize: 11, marginTop: spacing.xs },
  locationButton: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: radii.md, backgroundColor: colors.brand.greenSoft, alignItems: "center", borderWidth: 1, borderColor: colors.brand.green },
  disabled: { opacity: 0.5, backgroundColor: colors.surface.canvas },
  locationButtonText: { color: colors.brand.green, fontWeight: "800" },
  swapButton: { width: 44, height: 44, borderRadius: radii.lg, backgroundColor: colors.brand.greenSoft, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.brand.green },
  swapText: { color: colors.brand.green, fontSize: 24, fontWeight: "700" },
  label: { color: colors.text.ink, fontWeight: "700", fontSize: 13, marginTop: spacing.lg },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  chip: { paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: radii.pill, backgroundColor: colors.surface.canvas, borderWidth: 1, borderColor: colors.border },
  chipText: { color: colors.text.ink, fontSize: 12, fontWeight: "700" },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, marginTop: spacing.xs },
  attribution: { color: colors.text.muted, fontSize: 10, marginTop: spacing.xs },
  errorText: { color: colors.status.error, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, marginTop: spacing.sm },
  mapFrame: { marginTop: spacing.md, borderRadius: radii.lg, overflow: "hidden", borderWidth: 1, borderColor: colors.border },
  mapOverlay: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: "rgba(245,246,242,0.9)", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  selectedRoute: { marginTop: spacing.md, padding: spacing.md, backgroundColor: colors.surface.canvas, borderRadius: radii.md, gap: spacing.xs },
  selectedRouteText: { color: colors.text.ink, fontSize: 12 },
});

export default RideWhere;