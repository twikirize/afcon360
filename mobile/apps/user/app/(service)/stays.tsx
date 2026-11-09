import React, { useCallback, useEffect, useState } from "react";
import { Alert, ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
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
  AccommodationBooking,
  AccommodationBookingQuote,
  AccommodationProperty,
} from "@afcon360/mobile-core";
import { accommodationClient } from "../../src/services/api";

function dateOffset(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() + days);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function Field({
  label,
  value,
  onChangeText,
  placeholder,
  keyboardType = "default",
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  keyboardType?: "default" | "numeric";
}) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ color: palette.ink, fontWeight: "700", fontSize: 13 }}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#87938C"
        keyboardType={keyboardType}
        autoCapitalize="none"
        autoCorrect={false}
        style={{
          backgroundColor: "#FFFFFF",
          borderWidth: 1,
          borderColor: palette.border,
          borderRadius: 10,
          paddingHorizontal: 12,
          paddingVertical: 11,
          color: palette.ink,
          fontSize: 15,
        }}
      />
    </View>
  );
}

function isValidDateOnly(value: string): boolean {
  if (value.length !== 10 || value[4] !== "-" || value[7] !== "-") return false;
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return false;
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function money(value: string, currency: string): string {
  const number = Number(value);
  return Number.isFinite(number)
    ? `${number.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${currency}`
    : `${value} ${currency}`;
}

function bookingCanCancel(booking: AccommodationBooking): boolean {
  return ["confirmed", "pending_approval", "held", "pending_payment", "payment_partial"].includes(
    String(booking.status).toLowerCase()
  );
}

export default function Stays() {
  const [properties, setProperties] = useState<AccommodationProperty[]>([]);
  const [bookings, setBookings] = useState<AccommodationBooking[]>([]);
  const [selectedProperty, setSelectedProperty] = useState<AccommodationProperty | null>(null);
  const [query, setQuery] = useState("");
  const [checkIn, setCheckIn] = useState(dateOffset(7));
  const [checkOut, setCheckOut] = useState(dateOffset(9));
  const [guests, setGuests] = useState("2");
  const [rooms, setRooms] = useState("1");
  const [roomTypeToken, setRoomTypeToken] = useState<string | null>(null);
  const [quote, setQuote] = useState<AccommodationBookingQuote | null>(null);
  const [pin, setPin] = useState("");
  const [specialRequests, setSpecialRequests] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [bookingsLoading, setBookingsLoading] = useState(true);
  const [bookingsError, setBookingsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadBookings = useCallback(async () => {
    setBookingsLoading(true);
    setBookingsError(null);
    try {
      const result = await accommodationClient.listBookings(20, 0);
      setBookings(result.items ?? []);
    } catch (e) {
      setBookingsError(e instanceof Error ? e.message : "Your accommodation bookings could not be loaded.");
    } finally {
      setBookingsLoading(false);
    }
  }, []);

  const loadProperties = useCallback(async (term = "") => {
    setLoading(true);
    setError(null);
    try {
      const result = await accommodationClient.listProperties({
        query: term.trim() || undefined,
        limit: 30,
      });
      setProperties(result.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Accommodation search is unavailable.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProperties();
    void loadBookings();
  }, [loadProperties, loadBookings]);

  const chooseProperty = (property: AccommodationProperty) => {
    setSelectedProperty(property);
    setRoomTypeToken(property.room_types.length === 1 ? property.room_types[0].room_token : null);
    setQuote(null);
    setPin("");
    setError(null);
    setNotice(null);
  };

  const requestQuote = async () => {
    if (!selectedProperty) return;
    if (!isValidDateOnly(checkIn) || !isValidDateOnly(checkOut)) {
      setError("Enter real calendar dates using YYYY-MM-DD.");
      return;
    }
    if (checkOut <= checkIn) {
      setError("Check-out must be after check-in.");
      return;
    }
    const guestCount = Number(guests);
    const roomCount = Number(rooms);
    if (!Number.isInteger(guestCount) || guestCount < 1 || !Number.isInteger(roomCount) || roomCount < 1) {
      setError("Guests and rooms must both be whole numbers greater than zero.");
      return;
    }
    if (selectedProperty.room_types.length > 0 && roomTypeToken === null) {
      setError("Choose a room type before requesting a quote.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    setQuote(null);
    try {
      const result = await accommodationClient.quoteBooking({
        propertyPublicId: selectedProperty.public_id,
        checkIn,
        checkOut,
        numGuests: guestCount,
        roomsRequested: roomCount,
        roomTypeToken,
      });
      setQuote(result);
      setNotice("This price was calculated by AFCON360. Review the amount and available Wallet balance before confirming.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "AFCON360 could not prepare the booking quote.");
    } finally {
      setBusy(false);
    }
  };

  const submitBooking = async () => {
    if (!quote) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const booking = await accommodationClient.createWalletBooking({
        quoteToken: quote.quote_token,
        pin,
        specialRequests,
      });
      setQuote(null);
      setPin("");
      setSpecialRequests("");
      setNotice(`Booking ${booking.booking_reference} was created. Status: ${booking.status}.`);
      await loadBookings();
    } catch (e) {
      setError(e instanceof Error ? e.message : "AFCON360 could not confirm the booking.");
    } finally {
      setBusy(false);
    }
  };

  const confirmBooking = () => {
    if (!quote || !pin.trim()) {
      setError("Enter your Wallet transaction PIN to confirm this booking.");
      return;
    }
    Alert.alert(
      "Confirm accommodation booking",
      `Pay ${money(quote.total, quote.currency)} for ${quote.property.title}?\n\n${quote.check_in} to ${quote.check_out} · ${quote.nights} nights\n\nAFCON360 will use your Wallet balance. The property price and availability will be checked again before payment.`,
      [
        { text: "Review again", style: "cancel" },
        { text: "Confirm and pay", onPress: () => void submitBooking() },
      ],
    );
  };

  const cancelBooking = (booking: AccommodationBooking) => {
    Alert.alert(
      "Cancel this booking?",
      `Cancel ${booking.booking_reference}? AFCON360 will apply the property's cancellation policy and show any refund outcome.`,
      [
        { text: "Keep booking", style: "cancel" },
        {
          text: "Cancel booking",
          style: "destructive",
          onPress: () => {
            void (async () => {
              setBusy(true);
              setError(null);
              setNotice(null);
              try {
                const key = `native-accom-cancel-${booking.booking_reference}-${Date.now().toString(36)}`;
                const result = await accommodationClient.cancelBooking({
                  reference: booking.booking_reference,
                  idempotencyKey: key,
                  reason: "Cancelled by guest in AFCON360 User app",
                });
                if (result.refund?.status === "needs_reconciliation") {
                  setNotice("The booking was cancelled, but the refund needs AFCON360 support reconciliation. Do not submit a second refund.");
                } else if (result.refund) {
                  setNotice(`Booking cancelled. Refund: ${money(result.refund.amount, result.refund.currency)}.`);
                } else {
                  setNotice(result.cancellation_message || "Booking cancelled.");
                }
                await loadBookings();
              } catch (e) {
                setError(e instanceof Error ? e.message : "AFCON360 could not cancel this booking.");
              } finally {
                setBusy(false);
              }
            })();
          },
        },
      ],
    );
  };

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Accommodation"
        title="Find your place to stay."
        description="Discover bookable stays, review an AFCON360 price quote and pay from your Wallet."
      />

      {error ? <Panel><Text style={{ color: "#9A342D", lineHeight: 20 }}>{error}</Text></Panel> : null}
      {notice ? <Panel><Text style={{ color: palette.green, lineHeight: 20, fontWeight: "700" }}>{notice}</Text></Panel> : null}

      <Panel>
        <SectionTitle>Find accommodation</SectionTitle>
        <Field label="Property, city or destination" value={query} onChangeText={setQuery} placeholder="Search Kampala, Nairobi, hotel…" />
        <ActionButton label={loading ? "Searching stays…" : "Search stays"} disabled={loading || busy} onPress={() => void loadProperties(query)} />
        {loading ? (
          <ActivityIndicator color={palette.green} />
        ) : properties.length ? (
          properties.map((property) => (
            <Pressable
              key={property.public_id}
              onPress={() => chooseProperty(property)}
              style={{
                borderWidth: 1,
                borderColor: selectedProperty?.public_id === property.public_id ? palette.green : palette.border,
                borderRadius: 12,
                padding: 12,
                gap: 6,
                backgroundColor: selectedProperty?.public_id === property.public_id ? "#EFF6F0" : palette.surface,
              }}
            >
              <Text style={{ color: palette.ink, fontSize: 16, fontWeight: "900" }}>{property.title}</Text>
              <Text style={{ color: palette.muted }}>{property.city}, {property.country}</Text>
              <Text style={{ color: palette.ink, fontWeight: "700" }}>From {money(property.starting_price, property.currency)} per night</Text>
              {property.rating > 0 ? <Text style={{ color: palette.muted }}>Rating {property.rating.toFixed(1)} · {property.review_count} reviews</Text> : null}
              {property.room_types.length ? <Text style={{ color: palette.muted }}>{property.room_types.length} room type(s)</Text> : null}
            </Pressable>
          ))
        ) : error ? null : (
          <Text style={{ color: palette.muted }}>No bookable properties were found. Try another city or search term.</Text>
        )}
      </Panel>

      {selectedProperty ? (
        <Panel>
          <SectionTitle>{selectedProperty.title}</SectionTitle>
          <Text style={{ color: palette.muted, lineHeight: 20 }}>{selectedProperty.description || selectedProperty.summary}</Text>
          <Text style={{ color: palette.ink, fontWeight: "700" }}>{selectedProperty.address || `${selectedProperty.city}, ${selectedProperty.country}`}</Text>
          {selectedProperty.room_types.length ? (
            <View style={{ gap: 8 }}>
              <Text style={{ color: palette.ink, fontWeight: "800" }}>Choose a room</Text>
              {selectedProperty.room_types.map((room) => (
                <Pressable
                  key={room.room_token}
                  onPress={() => {
                    setRoomTypeToken(room.room_token);
                    setQuote(null);
                  }}
                  style={{
                    borderWidth: 1,
                    borderColor: roomTypeToken === room.room_token ? palette.green : palette.border,
                    borderRadius: 10,
                    padding: 10,
                    backgroundColor: roomTypeToken === room.room_token ? "#EFF6F0" : palette.surface,
                    gap: 4,
                  }}
                >
                  <Text style={{ color: palette.ink, fontWeight: "800" }}>{room.name}</Text>
                  <Text style={{ color: palette.muted }}>{room.max_guests} guests · {room.beds} bed(s) · {room.total_units} units</Text>
                  <Text style={{ color: palette.ink }}>{money(room.base_price_per_night, room.currency)} per night</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
          <Field label="Check-in (YYYY-MM-DD)" value={checkIn} onChangeText={(value) => { setCheckIn(value); setQuote(null); }} placeholder="2026-12-10" />
          <Field label="Check-out (YYYY-MM-DD)" value={checkOut} onChangeText={(value) => { setCheckOut(value); setQuote(null); }} placeholder="2026-12-12" />
          <Field label="Guests" value={guests} onChangeText={(value) => { setGuests(value); setQuote(null); }} placeholder="2" keyboardType="numeric" />
          <Field label="Rooms" value={rooms} onChangeText={(value) => { setRooms(value); setQuote(null); }} placeholder="1" keyboardType="numeric" />
          <ActionButton label={busy ? "Preparing quote…" : "Check availability and get price"} onPress={() => void requestQuote()} />
        </Panel>
      ) : null}

      {quote ? (
        <Panel>
          <SectionTitle>Review your booking</SectionTitle>
          <Text style={{ color: palette.ink, fontSize: 21, fontWeight: "900" }}>{money(quote.total, quote.currency)}</Text>
          <Text style={{ color: palette.muted }}>{quote.nights} night(s) · {quote.num_guests} guest(s) · {quote.rooms_requested} room(s)</Text>
          <View style={{ gap: 4 }}>
            <Text style={{ color: palette.muted }}>Nightly rate: {money(quote.nightly_rate, quote.currency)}</Text>
            <Text style={{ color: palette.muted }}>Subtotal: {money(quote.subtotal, quote.currency)}</Text>
            <Text style={{ color: palette.muted }}>Cleaning fee: {money(quote.cleaning_fee, quote.currency)}</Text>
            <Text style={{ color: palette.muted }}>Service fee: {money(quote.service_fee, quote.currency)}</Text>
            <Text style={{ color: palette.muted }}>Taxes: {money(quote.taxes, quote.currency)}</Text>
            <Text style={{ color: palette.ink, fontWeight: "800" }}>
              Wallet balance: {quote.wallet_available_balance ? money(quote.wallet_available_balance, quote.currency) : "No matching Wallet found"}
            </Text>
            <StatusPill tone={quote.wallet_payment_available ? "green" : "gold"}>
              {quote.wallet_payment_available ? "Wallet can cover this booking" : "Wallet payment unavailable"}
            </StatusPill>
            <Text style={{ color: palette.muted, fontSize: 11 }}>Quote expires {new Date(quote.expires_at).toLocaleTimeString()}.</Text>
          </View>
          <Field label="Transaction PIN" value={pin} onChangeText={setPin} placeholder="Enter your Wallet PIN" keyboardType="numeric" />
          <Field label="Special requests (optional)" value={specialRequests} onChangeText={setSpecialRequests} placeholder="Share arrival or accessibility requests" />
          <ActionButton label={busy ? "Confirming booking…" : "Review and pay from Wallet"} onPress={confirmBooking} />
          <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 17 }}>
            AFCON360 rechecks the property, dates and price on the server before charging your Wallet. The app does not calculate the booking total.
          </Text>
        </Panel>
      ) : null}

      <Panel>
        <SectionTitle>Your accommodation bookings</SectionTitle>
        {bookingsError ? <Text style={{ color: "#9A342D", lineHeight: 20 }}>Booking history is unavailable: {bookingsError}</Text> : null}
        {bookingsLoading ? <ActivityIndicator color={palette.green} /> : null}
        {!bookingsLoading && bookings.length ? bookings.map((booking) => (
          <View key={booking.booking_reference} style={{ borderTopWidth: 1, borderTopColor: palette.border, paddingTop: 10, gap: 6 }}>
            <Text style={{ color: palette.ink, fontWeight: "900" }}>{booking.property.title || "Accommodation booking"}</Text>
            <Text style={{ color: palette.muted }}>{booking.booking_reference}</Text>
            <Text style={{ color: palette.muted }}>{booking.check_in} → {booking.check_out}</Text>
            <Text style={{ color: palette.ink, fontWeight: "700" }}>{money(booking.amount, booking.currency)}</Text>
            <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
              <StatusPill tone={booking.status === "confirmed" ? "green" : "gold"}>{booking.status}</StatusPill>
              <StatusPill tone={booking.payment_status === "paid" ? "green" : "gold"}>{booking.payment_status}</StatusPill>
            </View>
            {bookingCanCancel(booking) ? <ActionButton label="Request cancellation" onPress={() => cancelBooking(booking)} /> : null}
          </View>
        )) : bookingsError || bookingsLoading ? null : (
          <Text style={{ color: palette.muted }}>Your accommodation bookings will appear here.</Text>
        )}
        <ActionButton label={bookingsLoading ? "Refreshing bookings…" : "Refresh bookings"} disabled={bookingsLoading} onPress={() => void loadBookings()} />
      </Panel>
    </AppScreen>
  );
}
