import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, AppState, ScrollView, Text, TextInput, View } from "react-native";
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

type Listing = {
  listing_public_id: string;
  vehicle_public_id: string;
  title: string;
  make: string;
  model: string;
  year?: number | null;
  description: string;
  vehicle_class: string;
  passenger_capacity: number;
  owner_type: string;
  compensation: string;
  application_deadline: string | null;
  already_applied: boolean;
};

type VehicleForm = {
  license_plate: string;
  registration_number: string;
  make: string;
  model: string;
  year: string;
  color: string;
  vin_number: string;
  vehicle_type: string;
  vehicle_class: string;
  passenger_capacity: string;
  luggage_capacity: string;
};

const emptyForm: VehicleForm = {
  license_plate: "",
  registration_number: "",
  make: "",
  model: "",
  year: String(new Date().getFullYear() - 2),
  color: "",
  vin_number: "",
  vehicle_type: "sedan",
  vehicle_class: "comfort",
  passenger_capacity: "4",
  luggage_capacity: "2"
};

function Field({
  label,
  value,
  onChangeText,
  keyboardType,
  placeholder,
  maxLength
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  keyboardType?: "default" | "numeric";
  placeholder?: string;
  maxLength?: number;
}) {
  return (
    <View style={{ flex: 1, minWidth: 135, gap: 4 }}>
      <Text style={{ color: palette.muted, fontSize: 11, fontWeight: "700" }}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        keyboardType={keyboardType ?? "default"}
        placeholder={placeholder}
        maxLength={maxLength}
        autoCapitalize="characters"
        style={{
          minHeight: 44,
          paddingHorizontal: 11,
          paddingVertical: 8,
          borderWidth: 1,
          borderColor: palette.border,
          borderRadius: 10,
          color: palette.ink,
          backgroundColor: "#FFFFFF",
          fontSize: 13
        }}
      />
    </View>
  );
}

function VehicleCard({
  vehicle,
  onEdit
}: {
  vehicle: Vehicle;
  onEdit: (vehicle: Vehicle) => void;
}) {
  return (
    <View style={{ gap: 8, padding: 13, borderRadius: 15, borderWidth: 1, borderColor: palette.border, backgroundColor: "#F8FBF9" }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <Text style={{ flex: 1, color: palette.ink, fontSize: 14, fontWeight: "900" }}>
          {vehicle.make} {vehicle.model} {vehicle.year ? "(" + vehicle.year + ")" : ""}
        </Text>
        <StatusPill tone={vehicle.status === "active" ? "green" : "gold"}>{vehicle.status}</StatusPill>
      </View>
      <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "800" }}>{vehicle.license_plate}</Text>
      <Text style={{ color: palette.muted, fontSize: 11 }}>
        {vehicle.vehicle_class ?? "Class not set"} · {vehicle.passenger_capacity} seats · {vehicle.is_available ? "Available" : "Unavailable"}
      </Text>
      <ActionButton label="Edit vehicle details" onPress={() => onEdit(vehicle)} />
    </View>
  );
}

export default function DriverVehicles() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingVehicle, setEditingVehicle] = useState<Vehicle | null>(null);
  const [form, setForm] = useState<VehicleForm>(emptyForm);
  const [coverLetters, setCoverLetters] = useState<Record<string, string>>({});

  const setField = (key: keyof VehicleForm, value: string) =>
    setForm(previous => ({ ...previous, [key]: value }));

  const load = useCallback(async () => {
    try {
      const [assignmentResponse, marketplaceResponse] = await Promise.all([
        authClient.request<{ data: { owned_vehicles: Vehicle[] } }>("/api/mobile/v1/driver/assignments"),
        authClient.request<{ data: { items: Listing[]; count: number } }>("/api/mobile/v1/driver/marketplace/vehicles")
      ]);
      setVehicles(assignmentResponse.data.owned_vehicles ?? []);
      setListings(marketplaceResponse.data.items ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Vehicle information could not be loaded.");
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

  function startNewVehicle() {
    setEditingVehicle(null);
    setForm(emptyForm);
    setShowForm(true);
  }

  function startEdit(vehicle: Vehicle) {
    setEditingVehicle(vehicle);
    setForm({
      ...emptyForm,
      license_plate: vehicle.license_plate,
      make: vehicle.make,
      model: vehicle.model,
      year: vehicle.year ? String(vehicle.year) : "",
      vehicle_class: vehicle.vehicle_class ?? "comfort",
      passenger_capacity: String(vehicle.passenger_capacity ?? 4)
    });
    setShowForm(true);
  }

  async function saveVehicle() {
    const required: Array<[keyof VehicleForm, string]> = [
      ["license_plate", "License plate"],
      ["make", "Make"],
      ["model", "Model"],
      ["year", "Year"],
      ["vehicle_class", "Vehicle class"],
      ["passenger_capacity", "Passenger capacity"],
      ["color", "Color"]
    ];
    const missing = required.find(([key]) => !form[key].trim());
    if (missing) {
      Alert.alert("Vehicle details required", missing[1] + " is required.");
      return;
    }
    const year = Number(form.year);
    const capacity = Number(form.passenger_capacity);
    if (!Number.isInteger(year) || !Number.isInteger(capacity)) {
      Alert.alert("Check vehicle details", "Year and passenger capacity must be whole numbers.");
      return;
    }
    const payload = {
      license_plate: form.license_plate.trim(),
      registration_number: form.registration_number.trim() || undefined,
      make: form.make.trim(),
      model: form.model.trim(),
      year,
      color: form.color.trim(),
      vin_number: form.vin_number.trim() || undefined,
      vehicle_type: form.vehicle_type.trim(),
      vehicle_class: form.vehicle_class,
      passenger_capacity: capacity,
      luggage_capacity: form.luggage_capacity.trim() ? Number(form.luggage_capacity) : undefined
    };
    setSaving(true);
    try {
      if (editingVehicle) {
        await authClient.request(
          "/api/mobile/v1/driver/vehicles/" + encodeURIComponent(editingVehicle.public_id),
          { method: "PUT", body: payload }
        );
        Alert.alert("Vehicle updated", "AFCON360 saved the vehicle specification changes.");
      } else {
        await authClient.request("/api/mobile/v1/driver/vehicles", {
          method: "POST",
          body: payload
        });
        Alert.alert(
          "Vehicle registration submitted",
          "AFCON360 accepted your registration request. Availability and assignment remain controlled by Transport."
        );
      }
      setShowForm(false);
      setEditingVehicle(null);
      await load();
    } catch (e) {
      Alert.alert(
        editingVehicle ? "Vehicle not updated" : "Vehicle not registered",
        e instanceof Error
          ? e.message
          : "AFCON360 could not save the vehicle. Check your KYC and vehicle requirements."
      );
    } finally {
      setSaving(false);
    }
  }

  async function applyForVehicle(listing: Listing) {
    setApplying(listing.listing_public_id);
    try {
      const response = await authClient.request<{ data: { status: string } }>(
        "/api/mobile/v1/driver/marketplace/vehicles/" +
          encodeURIComponent(listing.listing_public_id) +
          "/apply",
        {
          method: "POST",
          body: {
            cover_letter: coverLetters[listing.listing_public_id] ?? "",
            proposed_schedule: {},
            references: []
          }
        }
      );
      Alert.alert("Application submitted", "Your application status is " + response.data.status + ".");
      await load();
    } catch (e) {
      Alert.alert(
        "Application not submitted",
        e instanceof Error ? e.message : "AFCON360 could not submit this application."
      );
    } finally {
      setApplying(null);
    }
  }

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Vehicles"
        title="Your vehicles and opportunities."
        description="Manage vehicles you own and review public listings. Registration and applications remain subject to AFCON360 Transport approval."
      />

      {loading && !vehicles.length && !listings.length ? <ActivityIndicator color={palette.green} /> : null}
      {error ? (
        <Panel>
          <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>{error}</Text>
          <ActionButton label="Retry vehicles" disabled={loading} onPress={() => { setLoading(true); void load(); }} />
        </Panel>
      ) : null}

      <Panel>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <SectionTitle>Vehicles you own</SectionTitle>
          <StatusPill>{vehicles.length} vehicles</StatusPill>
        </View>
        {vehicles.length ? (
          vehicles.map(vehicle => (
            <VehicleCard key={vehicle.public_id} vehicle={vehicle} onEdit={startEdit} />
          ))
        ) : (
          <EmptyState
            title="No owned vehicles registered"
            description="You can register a vehicle owned by you. AFCON360 checks KYC tier, driver approval and vehicle details."
          />
        )}
        <ActionButton label="Register a vehicle" onPress={startNewVehicle} />
      </Panel>

      {showForm ? (
        <Panel>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <SectionTitle>{editingVehicle ? "Edit vehicle" : "Register vehicle"}</SectionTitle>
            <StatusPill tone="gold">Transport validation</StatusPill>
          </View>
          <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 16 }}>
            Required fields follow the website's vehicle registration validator. Vehicle registration requires KYC tier 3 and an approved Driver profile.
          </Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
            <Field label="License plate *" value={form.license_plate} onChangeText={v => setField("license_plate", v)} />
            <Field label="Registration number" value={form.registration_number} onChangeText={v => setField("registration_number", v)} />
            <Field label="Make *" value={form.make} onChangeText={v => setField("make", v)} />
            <Field label="Model *" value={form.model} onChangeText={v => setField("model", v)} />
            <Field label="Year *" value={form.year} keyboardType="numeric" onChangeText={v => setField("year", v)} />
            <Field label="Color *" value={form.color} onChangeText={v => setField("color", v)} />
            <Field label="VIN (17 characters)" value={form.vin_number} maxLength={17} onChangeText={v => setField("vin_number", v)} />
            <Field label="Vehicle type *" value={form.vehicle_type} onChangeText={v => setField("vehicle_type", v)} placeholder="sedan, van, bus" />
            <Field label="Class *" value={form.vehicle_class} onChangeText={v => setField("vehicle_class", v.toLowerCase())} placeholder="economy, comfort, premium, luxury, van, bus" />
            <Field label="Passenger capacity *" value={form.passenger_capacity} keyboardType="numeric" onChangeText={v => setField("passenger_capacity", v)} />
            <Field label="Luggage capacity" value={form.luggage_capacity} keyboardType="numeric" onChangeText={v => setField("luggage_capacity", v)} />
          </View>
          <ActionButton label={saving ? "Saving…" : editingVehicle ? "Save vehicle details" : "Submit vehicle registration"} disabled={saving} onPress={() => { void saveVehicle(); }} />
          <ActionButton label="Cancel" color="secondary" disabled={saving} onPress={() => { setShowForm(false); setEditingVehicle(null); }} />
        </Panel>
      ) : null}

      <Panel>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <SectionTitle>Vehicle marketplace</SectionTitle>
          <StatusPill>{listings.length} listings</StatusPill>
        </View>
        {listings.length ? (
          listings.map(listing => (
            <View key={listing.listing_public_id} style={{ gap: 9, padding: 13, borderWidth: 1, borderColor: palette.border, borderRadius: 15, backgroundColor: "#F8FBF9" }}>
              <Text style={{ color: palette.ink, fontSize: 14, fontWeight: "900" }}>{listing.title}</Text>
              <Text style={{ color: palette.ink, fontSize: 13, fontWeight: "700" }}>
                {listing.make} {listing.model} {listing.year ? "(" + listing.year + ")" : ""}
              </Text>
              <Text style={{ color: palette.muted, fontSize: 11 }}>
                {listing.vehicle_class} · {listing.passenger_capacity} seats · {listing.owner_type}
              </Text>
              {listing.description ? <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>{listing.description}</Text> : null}
              <StatusPill tone="neutral">{listing.compensation}</StatusPill>
              {listing.application_deadline ? (
                <Text style={{ color: palette.muted, fontSize: 11 }}>Apply before: {listing.application_deadline}</Text>
              ) : null}
              <Text style={{ color: palette.muted, fontSize: 11, fontWeight: "700" }}>Application note (optional)</Text>
              <TextInput
                multiline
                value={coverLetters[listing.listing_public_id] ?? ""}
                onChangeText={value => setCoverLetters(previous => ({ ...previous, [listing.listing_public_id]: value }))}
                placeholder="Introduce your driving experience and why you are interested."
                style={{ minHeight: 76, padding: 10, borderWidth: 1, borderColor: palette.border, borderRadius: 10, color: palette.ink, backgroundColor: "#FFFFFF", fontSize: 12, textAlignVertical: "top" }}
              />
              <ActionButton
                label={applying === listing.listing_public_id ? "Submitting…" : "Apply for this vehicle"}
                disabled={applying !== null}
                onPress={() => { void applyForVehicle(listing); }}
              />
            </View>
          ))
        ) : (
          <EmptyState
            title="No matching public listings"
            description="Public active listings that meet your Driver verification tier and vehicle requirements will appear here."
          />
        )}
      </Panel>

      <ActionButton label={loading ? "Refreshing…" : "Refresh vehicles"} disabled={loading || saving || applying !== null} onPress={() => { setLoading(true); void load(); }} />
    </AppScreen>
  );
}
