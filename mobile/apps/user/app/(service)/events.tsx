import React, { useCallback, useEffect, useState } from "react";
import { useLocalSearchParams } from "expo-router";
import { ActivityIndicator, Image, Pressable, Text, TextInput, View } from "react-native";
import {
  ActionButton,
  AppScreen,
  PageHeader,
  Panel,
  SectionTitle,
  StatusPill,
  palette,
} from "@afcon360/mobile-ui";
import {
  NativeEventDetail,
  NativeEventRegistration,
  NativeEventSummary,
  NativeEventTicketType,
} from "@afcon360/mobile-core";
import { eventClient } from "../../src/services/api";
import { serviceErrorMessage } from "../../src/services/service-errors";

function displayDate(start: string | null, end: string | null): string {
  if (!start) return "Date to be announced";
  const startDate = new Date(start + "T00:00:00");
  if (Number.isNaN(startDate.getTime())) return start;
  const from = startDate.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  if (!end || end === start) return from;
  const endDate = new Date(end + "T00:00:00");
  return Number.isNaN(endDate.getTime())
    ? from
    : `${from} – ${endDate.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}`;
}

function ticketPrice(ticket: NativeEventTicketType): string {
  const amount = Number(ticket.price);
  if (Number.isFinite(amount) && amount <= 0) return "Free";
  if (!Number.isFinite(amount)) return `${ticket.price} ${ticket.currency}`;
  return `${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${ticket.currency}`;
}

function registrationPrice(registration: NativeEventRegistration): string {
  const amount = Number(registration.amount);
  return Number.isFinite(amount)
    ? `${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${registration.currency}`
    : `${registration.amount} ${registration.currency}`;
}

export default function Events() {
  const params = useLocalSearchParams<{ query?: string }>();
  const routeQuery = typeof params.query === "string" ? params.query : "";
  const [events, setEvents] = useState<NativeEventSummary[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<NativeEventDetail | null>(null);
  const [registrations, setRegistrations] = useState<NativeEventRegistration[]>([]);
  const [visibleTicket, setVisibleTicket] = useState<string | null>(null);
  const [query, setQuery] = useState(routeQuery);
  const [city, setCity] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [registrationsLoading, setRegistrationsLoading] = useState(true);
  const [registrationsError, setRegistrationsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadEvents = useCallback(async (search: string, destination: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await eventClient.listEvents({
        query: search.trim() || undefined,
        city: destination.trim() || undefined,
        limit: 30,
      });
      setEvents(result.items ?? []);
    } catch (e) {
      setEvents([]);
      setError(serviceErrorMessage(e, "Events"));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRegistrations = useCallback(async () => {
    setRegistrationsLoading(true);
    setRegistrationsError(null);
    try {
      const result = await eventClient.listRegistrations(30, 0);
      setRegistrations(result.items ?? []);
    } catch (e) {
      setRegistrations([]);
      setRegistrationsError(serviceErrorMessage(e, "Events"));
    } finally {
      setRegistrationsLoading(false);
    }
  }, []);

  useEffect(() => {
    setQuery(routeQuery);
    void loadEvents(routeQuery, "");
    void loadRegistrations();
  }, [routeQuery, loadEvents, loadRegistrations]);

  const openEvent = async (event: NativeEventSummary) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    setSelectedEvent(null);
    try {
      const detail = await eventClient.getEvent(event.public_id);
      setSelectedEvent(detail);
    } catch (e) {
      setError(serviceErrorMessage(e, "Events"));
    } finally {
      setBusy(false);
    }
  };

  const register = async (ticket: NativeEventTicketType) => {
    if (!selectedEvent) return;
    if (Number(ticket.price) > 0) {
      setError("This ticket requires payment. Paid-ticket checkout is not available in the app yet; no payment has been taken.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await eventClient.registerFreeTicket(selectedEvent.public_id, ticket.ticket_token);
      setNotice(`Your free ticket is confirmed. Reference: ${result.registration_reference}.`);
      setVisibleTicket(result.registration_reference);
      setRegistrations((current) => [
        result,
        ...current.filter((item) => item.registration_reference !== result.registration_reference),
      ]);
    } catch (e) {
      setError(serviceErrorMessage(e, "Events"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Events and tickets"
        title="Be there for the moments."
        description="Discover published events, check ticket availability and register for free tickets in AFCON360."
      />

      {error ? <Panel><Text style={{ color: "#9A342D", lineHeight: 20 }}>{error}</Text></Panel> : null}
      {notice ? <Panel><Text style={{ color: palette.green, lineHeight: 20, fontWeight: "800" }}>{notice}</Text></Panel> : null}

      <Panel>
        <SectionTitle>Find events</SectionTitle>
        <View style={{ gap: 6 }}>
          <Text style={{ color: palette.ink, fontWeight: "700", fontSize: 13 }}>Event or activity</Text>
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search football, fan zone, concert…"
            placeholderTextColor="#87938C"
            autoCapitalize="none"
            style={{ backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 12, color: palette.ink }}
          />
        </View>
        <View style={{ gap: 6 }}>
          <Text style={{ color: palette.ink, fontWeight: "700", fontSize: 13 }}>City (optional)</Text>
          <TextInput
            value={city}
            onChangeText={setCity}
            placeholder="Kampala, Nairobi, Dar es Salaam…"
            placeholderTextColor="#87938C"
            autoCapitalize="words"
            style={{ backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 12, color: palette.ink }}
          />
        </View>
        <ActionButton label={loading ? "Searching events…" : "Search events"} disabled={loading || busy} onPress={() => void loadEvents(query, city)} />
        {loading ? (
          <ActivityIndicator color={palette.green} />
        ) : events.length ? (
          events.map((event) => (
            <Pressable
              key={event.public_id}
              onPress={() => void openEvent(event)}
              disabled={busy}
              style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 12, padding: 12, gap: 5, backgroundColor: palette.surface }}
            >
              <Text style={{ color: palette.ink, fontSize: 16, fontWeight: "900" }}>{event.name}</Text>
              <Text style={{ color: palette.muted }}>{event.city}, {event.country}</Text>
              <Text style={{ color: palette.muted }}>{displayDate(event.start_date, event.end_date)}</Text>
              <Text style={{ color: palette.ink, fontWeight: "700" }}>{event.category}</Text>
            </Pressable>
          ))
        ) : error ? null : (
          <Text style={{ color: palette.muted }}>No published events matched that search.</Text>
        )}
      </Panel>

      {selectedEvent ? (
        <Panel>
          <SectionTitle>{selectedEvent.name}</SectionTitle>
          <Text style={{ color: palette.muted, lineHeight: 20 }}>{selectedEvent.description}</Text>
          <Text style={{ color: palette.ink, fontWeight: "700" }}>{selectedEvent.venue ? `${selectedEvent.venue} · ` : ""}{selectedEvent.city}, {selectedEvent.country}</Text>
          <Text style={{ color: palette.muted }}>{displayDate(selectedEvent.start_date, selectedEvent.end_date)}</Text>
          <StatusPill tone={selectedEvent.registration.state === "open" ? "green" : "gold"}>
            {selectedEvent.registration.state}
          </StatusPill>
          <Text style={{ color: palette.muted, lineHeight: 20 }}>{selectedEvent.registration.message}</Text>
          <SectionTitle>Ticket types</SectionTitle>
          {selectedEvent.ticket_availability.length ? selectedEvent.ticket_availability.map((ticket) => {
            const isFree = Number(ticket.price) <= 0;
            const canRegister = isFree && ticket.is_available_now && selectedEvent.registration.state === "open";
            return (
              <View key={ticket.ticket_token} style={{ borderTopWidth: 1, borderTopColor: palette.border, paddingTop: 10, gap: 6 }}>
                <Text style={{ color: palette.ink, fontWeight: "900" }}>{ticket.name}</Text>
                {ticket.description ? <Text style={{ color: palette.muted }}>{ticket.description}</Text> : null}
                <Text style={{ color: palette.ink, fontWeight: "800" }}>{ticketPrice(ticket)}</Text>
                {ticket.capacity_limited ? <Text style={{ color: palette.muted }}>{ticket.remaining ?? 0} remaining</Text> : null}
                <StatusPill tone={ticket.is_available_now ? "green" : "gold"}>
                  {ticket.is_available_now ? "Available now" : "Not currently available"}
                </StatusPill>
                {canRegister ? (
                  <ActionButton label={busy ? "Registering…" : "Register for free"} disabled={busy} onPress={() => void register(ticket)} />
                ) : !isFree ? (
                  <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>
                    Paid checkout is not enabled in the native app yet. You will not be charged here.
                  </Text>
                ) : null}
              </View>
            );
          }) : (
            <Text style={{ color: palette.muted }}>No ticket types are currently published for this event.</Text>
          )}
        </Panel>
      ) : null}

      <Panel>
        <SectionTitle>Your tickets</SectionTitle>
        {registrationsError ? <Text style={{ color: "#9A342D", lineHeight: 20 }}>Ticket history is unavailable: {registrationsError}</Text> : null}
        {registrationsLoading ? <ActivityIndicator color={palette.green} /> : null}
        {!registrationsLoading && registrations.length ? registrations.map((ticket) => (
          <View key={ticket.registration_reference} style={{ borderTopWidth: 1, borderTopColor: palette.border, paddingTop: 10, gap: 6 }}>
            <Text style={{ color: palette.ink, fontWeight: "900" }}>{ticket.event.name || "Event ticket"}</Text>
            <Text style={{ color: palette.muted }}>{ticket.ticket_type} · {ticket.registration_reference}</Text>
            <Text style={{ color: palette.muted }}>{ticket.event.city}, {ticket.event.country}</Text>
            <Text style={{ color: palette.ink, fontWeight: "700" }}>{registrationPrice(ticket)}</Text>
            <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
              <StatusPill tone={ticket.status === "confirmed" ? "green" : "gold"}>{ticket.status}</StatusPill>
              <StatusPill tone={ticket.payment_status === "free" || ticket.payment_status === "paid" ? "green" : "gold"}>{ticket.payment_status}</StatusPill>
            </View>
            <ActionButton
              label={visibleTicket === ticket.registration_reference ? "Hide QR ticket" : "Show QR ticket"}
              onPress={() => setVisibleTicket((current) => current === ticket.registration_reference ? null : ticket.registration_reference)}
            />
            {visibleTicket === ticket.registration_reference ? (
              <View style={{ alignItems: "center", gap: 8, padding: 12 }}>
                <Image source={{ uri: ticket.qr_code }} style={{ width: 220, height: 220 }} resizeMode="contain" />
                <Text style={{ color: palette.ink, fontWeight: "900" }}>{ticket.ticket_number}</Text>
                <Text style={{ color: palette.muted, fontSize: 12 }}>Present this QR code at the event entrance.</Text>
              </View>
            ) : null}
          </View>
        )) : registrationsError || registrationsLoading ? null : (
          <Text style={{ color: palette.muted }}>Your confirmed event tickets will appear here.</Text>
        )}
        <ActionButton label={registrationsLoading ? "Refreshing tickets…" : "Refresh tickets"} disabled={registrationsLoading} onPress={() => void loadRegistrations()} />
      </Panel>
    </AppScreen>
  );
}
