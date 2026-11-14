import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, AppState, Text, View } from "react-native";
import {
  ActionButton,
  AppScreen,
  EmptyState,
  PageHeader,
  Panel,
  SectionTitle,
  StatusPill,
  palette
} from "@afcon360/mobile-ui";
import { useFocusEffect } from "expo-router";
import { authClient } from "../../src/services/api";

type Vehicle = {
  public_id: string;
  make: string;
  model: string;
  year?: number | null;
  license_plate: string;
  vehicle_class?: string | null;
  status: string;
  is_available: boolean;
  passenger_capacity: number;
  safety_features: string[];
};

type VehicleHistory = {
  license_plate: string;
  assignment_reason: string;
  was_breakdown: boolean;
  started_at: string | null;
  ended_at: string | null;
};

type ScheduledRoute = {
  name: string;
  route_code: string;
  route_type: string;
  primary_zone: string;
  next_departure: string | null;
  available_seats: number;
  vehicle_capacity: number;
  price_per_seat: string | null;
  is_free: boolean;
};

type AssignmentsData = {
  assigned_vehicle: Vehicle | null;
  owned_vehicles: Vehicle[];
  switchable_vehicles: Vehicle[];
  vehicle_history: VehicleHistory[];
  scheduled_routes: ScheduledRoute[];
  history_window_days: number;
};

function VehicleSummary({ vehicle }: { vehicle: Vehicle }) {
  return (
    <View style={{ gap: 8, padding: 13, borderRadius: 15, borderWidth: 1, borderColor: palette.border, backgroundColor: "#F8FBF9" }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "900", flexShrink: 1 }}>
          {vehicle.make} {vehicle.model} {vehicle.year ? "(" + vehicle.year + ")" : ""}
        </Text>
        <StatusPill tone={vehicle.status === "active" ? "green" : "gold"}>{vehicle.status}</StatusPill>
      </View>
      <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "800" }}>{vehicle.license_plate}</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 14 }}>
        <Text style={{ color: palette.muted, fontSize: 11 }}>{vehicle.vehicle_class ?? "Vehicle class not set"}</Text>
        <Text style={{ color: palette.muted, fontSize: 11 }}>{vehicle.passenger_capacity} passenger seats</Text>
        <Text style={{ color: palette.muted, fontSize: 11 }}>{vehicle.is_available ? "Available" : "Unavailable"}</Text>
      </View>
      {vehicle.safety_features.length ? (
        <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
          Safety features: {vehicle.safety_features.join(", ")}
        </Text>
      ) : null}
    </View>
  );
}

export default function DriverAssignments() {
  const [data, setData] = useState<AssignmentsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await authClient.request<{ data: AssignmentsData }>(
        "/api/mobile/v1/driver/assignments"
      );
      setData(response.data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Driver assignments could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
      const subscription = AppState.addEventListener("change", state => {
        if (state === "active") void load();
      });
      return () => subscription.remove();
    }, [load])
  );

  async function switchVehicle(vehicle: Vehicle) {
    Alert.alert(
      "Switch assigned vehicle",
      "Switch your active assignment to " + vehicle.make + " " + vehicle.model + " (" + vehicle.license_plate + ")? AFCON360 will check ownership and vehicle eligibility.",
      [
        { text: "Keep current vehicle", style: "cancel" },
        {
          text: "Switch vehicle",
          onPress: async () => {
            setSwitching(vehicle.public_id);
            try {
              await authClient.request("/api/mobile/v1/driver/vehicles/switch", {
                method: "POST",
                body: { vehicle_public_id: vehicle.public_id, reason: "shift_start" }
              });
              await load();
              Alert.alert("Vehicle assignment updated", "AFCON360 confirmed your new vehicle assignment.");
            } catch (e) {
              Alert.alert(
                "Vehicle not switched",
                e instanceof Error ? e.message : "AFCON360 could not switch this vehicle."
              );
            } finally {
              setSwitching(null);
            }
          }
        }
      ]
    );
  }

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Assignments"
        title="Your assigned transport."
        description="Review your current vehicle, scheduled work and assignment history. Vehicle switches are confirmed by AFCON360."
      />

      {loading && !data ? <ActivityIndicator color={palette.green} /> : null}
      {error ? (
        <Panel>
          <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>{error}</Text>
          <ActionButton label="Retry assignments" disabled={loading} onPress={() => { setLoading(true); void load(); }} />
        </Panel>
      ) : null}

      <Panel>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <SectionTitle>Current assigned vehicle</SectionTitle>
          {data?.assigned_vehicle ? <StatusPill tone="green">Assigned</StatusPill> : null}
        </View>
        {data?.assigned_vehicle ? (
          <VehicleSummary vehicle={data.assigned_vehicle} />
        ) : (
          <EmptyState title="No vehicle assigned" description="Your current vehicle assignment will appear here when Transport assigns or you switch to an eligible owned vehicle." />
        )}
      </Panel>

      <Panel>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <SectionTitle>Switch vehicle</SectionTitle>
          <StatusPill>{data?.switchable_vehicles.length ?? 0} available</StatusPill>
        </View>
        {(data?.switchable_vehicles ?? []).length ? (
          data?.switchable_vehicles.map(vehicle => (
            <View key={vehicle.public_id} style={{ gap: 7 }}>
              <VehicleSummary vehicle={vehicle} />
              <ActionButton
                label={switching === vehicle.public_id ? "Switching…" : "Switch to this vehicle"}
                disabled={switching !== null}
                onPress={() => switchVehicle(vehicle)}
              />
            </View>
          ))
        ) : (
          <EmptyState title="No other switchable vehicles" description="Only active vehicles owned by you and approved by Transport can be selected here." />
        )}
      </Panel>

      <Panel>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <SectionTitle>Scheduled work</SectionTitle>
          <StatusPill>{data?.scheduled_routes.length ?? 0} routes</StatusPill>
        </View>
        {(data?.scheduled_routes ?? []).length ? (
          data?.scheduled_routes.map(route => (
            <View key={route.route_code} style={{ gap: 6, padding: 13, borderRadius: 14, borderWidth: 1, borderColor: palette.border }}>
              <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "900" }}>{route.name}</Text>
              <Text style={{ color: palette.muted, fontSize: 11 }}>{route.route_code} · {route.route_type} · {route.primary_zone || "Zone not set"}</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 14 }}>
                <Text style={{ color: palette.ink, fontSize: 12 }}>Departure: {route.next_departure ?? "Not scheduled"}</Text>
                <Text style={{ color: palette.ink, fontSize: 12 }}>Seats: {route.available_seats}/{route.vehicle_capacity}</Text>
                <Text style={{ color: palette.ink, fontSize: 12 }}>{route.is_free ? "Free" : (route.price_per_seat ?? "Price not set") + " per seat"}</Text>
              </View>
            </View>
          ))
        ) : (
          <EmptyState title="No scheduled routes" description="Scheduled assignments connected to your Driver profile appear here." />
        )}
      </Panel>

      <Panel>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <SectionTitle>Vehicle history</SectionTitle>
          <StatusPill>{data?.history_window_days ?? 90} days</StatusPill>
        </View>
        {(data?.vehicle_history ?? []).length ? (
          data?.vehicle_history.map((entry, index) => (
            <View key={entry.license_plate + "-" + String(index)} style={{ gap: 4, paddingVertical: 8, borderBottomWidth: index === (data?.vehicle_history.length ?? 0) - 1 ? 0 : 1, borderBottomColor: palette.border }}>
              <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "800" }}>{entry.license_plate}</Text>
              <Text style={{ color: palette.muted, fontSize: 11 }}>{entry.assignment_reason.replace(/_/g, " ")}{entry.was_breakdown ? " · Breakdown replacement" : ""}</Text>
              <Text style={{ color: palette.muted, fontSize: 11 }}>{entry.started_at ?? "Start time unavailable"} – {entry.ended_at ?? "Current/ongoing"}</Text>
            </View>
          ))
        ) : (
          <EmptyState title="No recent vehicle history" description="Vehicle changes and assignment periods from the last 90 days will appear here." />
        )}
      </Panel>

      <ActionButton label={loading ? "Refreshing…" : "Refresh assignments"} disabled={loading || switching !== null} onPress={() => { setLoading(true); void load(); }} />
    </AppScreen>
  );
}
