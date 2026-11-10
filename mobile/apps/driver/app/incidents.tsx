import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, AppState, Pressable, Text, TextInput, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
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
import { authClient } from "../src/services/api";

type IncidentSeverity = "info" | "low" | "medium" | "high" | "critical";
type IncidentItem = {
  incident_reference: string;
  incident_type: string;
  incident_category?: string | null;
  severity: IncidentSeverity;
  title: string;
  description: string;
  occurred_at: string;
  status: string;
  priority: string;
  created_at?: string | null;
};

type IncidentListResponse = { data: { items: IncidentItem[]; count: number } };

const severities: IncidentSeverity[] = ["info", "low", "medium", "high", "critical"];

export default function DriverIncidents() {
  const router = useRouter();
  const [items, setItems] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [incidentType, setIncidentType] = useState("safety");
  const [severity, setSeverity] = useState<IncidentSeverity>("medium");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [bookingReference, setBookingReference] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await authClient.request<IncidentListResponse>(
        "/api/mobile/v1/driver/incidents?limit=30"
      );
      setItems(response.data.items ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Incident reports could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
      const sub = AppState.addEventListener("change", state => {
        if (state === "active") void load();
      });
      return () => sub.remove();
    }, [load])
  );

  const submit = async () => {
    const type = incidentType.trim();
    const heading = title.trim();
    const detail = description.trim();
    if (!type || !heading || !detail) {
      setError("Enter an incident type, title and description.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await authClient.request<{ data: { incident_reference: string } }>(
        "/api/mobile/v1/driver/incidents",
        {
          method: "POST",
          body: {
            incident_type: type,
            incident_category: type.toLowerCase().includes("vehicle") ? "vehicle" : "safety",
            severity,
            title: heading,
            description: detail,
            occurred_at: new Date().toISOString(),
            ...(bookingReference.trim()
              ? { booking_reference: bookingReference.trim() }
              : {})
          }
        }
      );
      setTitle("");
      setDescription("");
      setBookingReference("");
      await load();
      Alert.alert(
        "Incident report submitted",
        "AFCON360 reference: " + response.data.incident_reference
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "AFCON360 could not submit this incident report.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Driver safety"
        title="Report an incident."
        description="Send a Transport incident report to AFCON360. Your Driver identity is attached securely by the server."
      />
      <Panel>
        <SectionTitle>New incident report</SectionTitle>
        <Text style={{ color:palette.muted, fontSize:11 }}>
          Occurrence time is recorded as the current device time in UTC. Attach a trip reference only when the incident relates to a trip assigned to you.
        </Text>
        <Text style={{ color:palette.ink, fontSize:12, fontWeight:"800" }}>Incident type</Text>
        <TextInput
          value={incidentType}
          onChangeText={setIncidentType}
          placeholder="safety, service, vehicle, payment"
          placeholderTextColor={palette.muted}
          style={{ borderWidth:1, borderColor:palette.border, borderRadius:11, padding:11, color:palette.ink }}
        />
        <Text style={{ color:palette.ink, fontSize:12, fontWeight:"800" }}>Severity</Text>
        <View style={{ flexDirection:"row", flexWrap:"wrap", gap:6 }}>
          {severities.map(value => (
            <Pressable
              key={value}
              onPress={() => setSeverity(value)}
              accessibilityRole="button"
              accessibilityState={{ selected:severity === value }}
              style={{
                paddingHorizontal:10, paddingVertical:8, borderRadius:10,
                backgroundColor:severity === value ? palette.green : "#F1F5F2",
                borderWidth:1, borderColor:severity === value ? palette.green : palette.border
              }}
            >
              <Text style={{ color:severity === value ? "#FFFFFF" : palette.ink, fontSize:11, fontWeight:"800" }}>
                {value.toUpperCase()}
              </Text>
            </Pressable>
          ))}
        </View>
        <Text style={{ color:palette.ink, fontSize:12, fontWeight:"800" }}>Title</Text>
        <TextInput
          value={title}
          onChangeText={setTitle}
          maxLength={200}
          placeholder="Briefly describe what happened"
          placeholderTextColor={palette.muted}
          style={{ borderWidth:1, borderColor:palette.border, borderRadius:11, padding:11, color:palette.ink }}
        />
        <Text style={{ color:palette.ink, fontSize:12, fontWeight:"800" }}>Details</Text>
        <TextInput
          value={description}
          onChangeText={setDescription}
          maxLength={5000}
          multiline
          textAlignVertical="top"
          placeholder="Describe the incident and any immediate safety concerns."
          placeholderTextColor={palette.muted}
          style={{ minHeight:110, borderWidth:1, borderColor:palette.border, borderRadius:11, padding:11, color:palette.ink }}
        />
        <Text style={{ color:palette.ink, fontSize:12, fontWeight:"800" }}>Trip reference (optional)</Text>
        <TextInput
          value={bookingReference}
          onChangeText={setBookingReference}
          autoCapitalize="characters"
          placeholder="AF360-…"
          placeholderTextColor={palette.muted}
          style={{ borderWidth:1, borderColor:palette.border, borderRadius:11, padding:11, color:palette.ink }}
        />
        {error ? <Text accessibilityRole="alert" style={{ color:"#9A3A2F", fontSize:12 }}>{error}</Text> : null}
        <ActionButton label={saving ? "Submitting…" : "Submit incident report"} disabled={saving} onPress={() => { void submit(); }} />
      </Panel>
      <Panel>
        <View style={{ flexDirection:"row", justifyContent:"space-between", alignItems:"center", gap:8 }}>
          <SectionTitle>Your incident reports</SectionTitle>
          <StatusPill>{items.length} reports</StatusPill>
        </View>
        {loading && !items.length ? <ActivityIndicator color={palette.green} /> : null}
        {!loading && !items.length ? (
          <EmptyState title="No reports submitted" description="Reports you submit from this Driver account will appear here." />
        ) : null}
        {items.map(item => (
          <View key={item.incident_reference} style={{ gap:6, padding:12, borderRadius:12, borderWidth:1, borderColor:palette.border }}>
            <View style={{ flexDirection:"row", alignItems:"center", justifyContent:"space-between", gap:8 }}>
              <Text style={{ color:palette.ink, fontSize:12, fontWeight:"900" }}>{item.incident_reference}</Text>
              <StatusPill tone={item.severity === "high" || item.severity === "critical" ? "gold" : "neutral"}>
                {item.severity}
              </StatusPill>
            </View>
            <Text style={{ color:palette.ink, fontSize:13, fontWeight:"800" }}>{item.title}</Text>
            <Text style={{ color:palette.muted, fontSize:11 }}>{item.incident_type} · {item.status}</Text>
            <Text style={{ color:palette.ink, fontSize:12, lineHeight:18 }}>{item.description}</Text>
            <Text style={{ color:palette.muted, fontSize:10 }}>{new Date(item.occurred_at).toLocaleString()}</Text>
          </View>
        ))}
        <ActionButton label={loading ? "Refreshing…" : "Refresh reports"} disabled={loading} onPress={() => { setLoading(true); void load(); }} />
      </Panel>
      <ActionButton label="Back to Driver account" onPress={() => router.back()} />
    </AppScreen>
  );
}
