import React, { useCallback, useEffect, useState, useMemo } from "react";
import { useRouter } from "expo-router";
import { Alert, ActivityIndicator, Pressable, Text, TextInput, View, Image, StyleSheet, ScrollView } from "react-native";
import { palette as basePalette } from "@afcon360/mobile-ui";
import {
  PamojaActionButton as ActionButton,
  PamojaScreen as AppScreen,
  PamojaPageHeader as PageHeader,
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
  PamojaStatusPill as StatusPill,
} from "../../src/components/PamojaScreen";
import { ServiceHeroAccent } from "../../src/components/ServiceHeroAccent";
import { PropertyCard } from "../../src/components/PropertyCard";
import { StaysFiltersBottomSheet, type StaysFilters } from "../../src/components/StaysFilters";
import {
  AccommodationBooking,
  AccommodationBookingQuote,
  AccommodationProperty,
} from "@afcon360/mobile-core";
import { accommodationClient } from "../../src/services/api";
import { serviceErrorMessage } from "../../src/services/service-errors";
import { userOfflineRepository, type WishlistItem } from "../../src/offline/repositories";
import { useAuth } from "../../src/auth/AuthProvider";

const palette = {
  ...basePalette,
  canvas: "#F5F6F2",
  surface: "#FFFFFF",
  ink: "#122419",
  muted: "#6C766E",
  green: "#0E5B36",
  greenDark: "#093E24",
  greenSoft: "#E8F4EC",
  border: "#E6EAE4",
  warningSoft: "#FFF4D5",
};

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
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#87938C"
        keyboardType={keyboardType}
        autoCapitalize="none"
        autoCorrect={false}
        style={styles.input}
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
  const router = useRouter();
  const { user } = useAuth();
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

  // Filters & view
  const [filters, setFilters] = useState<StaysFilters>({});
  const [filtersVisible, setFiltersVisible] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");

  // Wishlist
  const [wishlist, setWishlist] = useState<WishlistItem[]>([]);
  const [wishlistLoading, setWishlistLoading] = useState(true);

  const loadWishlist = useCallback(async () => {
    if (!user?.public_id) { setWishlist([]); setWishlistLoading(false); return; }
    setWishlistLoading(true);
    try {
      const cached = await userOfflineRepository.readWishlist(user.public_id);
      setWishlist(cached?.value?.items ?? []);
    } catch {
      setWishlist([]);
    } finally {
      setWishlistLoading(false);
    }
  }, [user?.public_id]);

  const toggleWishlist = useCallback(async (property: AccommodationProperty) => {
    if (!user?.public_id) return;
    const isWishlisted = wishlist.some((w) => w.propertyId === property.public_id);
    try {
      if (isWishlisted) {
        await userOfflineRepository.removeFromWishlist(user.public_id, property.public_id);
        setWishlist((prev) => prev.filter((w) => w.propertyId !== property.public_id));
      } else {
        const item: WishlistItem = {
          propertyId: property.public_id,
          propertyTitle: property.title,
          propertyCity: property.city,
          propertyCountry: property.country,
          propertyImage: property.main_image,
          propertyStartingPrice: property.starting_price,
          propertyCurrency: property.currency,
          addedAt: Date.now(),
        };
        await userOfflineRepository.addToWishlist(user.public_id, item);
        setWishlist((prev) => [item, ...prev.filter((w) => w.propertyId !== property.public_id)]);
      }
    } catch {
      // Wishlist is best-effort; don't block the UI
    }
  }, [user?.public_id, wishlist]);

  const isWishlisted = (propertyId: string) => wishlist.some((w) => w.propertyId === propertyId);

  const loadBookings = useCallback(async () => {
    // Booking history is the signed-in guest's own record, so it is only
    // requested when there is one. Property search above stays open to all.
    if (!user?.public_id) { setBookings([]); setBookingsError(null); setBookingsLoading(false); return; }
    setBookingsLoading(true);
    setBookingsError(null);
    try {
      const result = await accommodationClient.listBookings(20, 0);
      setBookings(result.items ?? []);
    } catch (e) {
      setBookings([]);
      setBookingsError(serviceErrorMessage(e, "Accommodation"));
    } finally {
      setBookingsLoading(false);
    }
  }, [user?.public_id]);

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
      setProperties([]);
      setError(serviceErrorMessage(e, "Accommodation"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProperties();
    void loadBookings();
    void loadWishlist();
  }, [loadProperties, loadBookings, loadWishlist]);

  // Client-side filtering
  const filteredProperties = useMemo(() => {
    let result = properties;
    if (filters.priceMin != null) {
      result = result.filter((p) => Number(p.starting_price) >= filters.priceMin!);
    }
    if (filters.priceMax != null) {
      result = result.filter((p) => Number(p.starting_price) <= filters.priceMax!);
    }
    if (filters.minRating != null) {
      result = result.filter((p) => p.rating >= filters.minRating!);
    }
    if (filters.propertyTypes?.length) {
      result = result.filter((p) => filters.propertyTypes!.includes(p.property_type));
    }
    if (filters.amenities?.length) {
      // Note: API doesn't return amenities yet; this is a placeholder for future
      // result = result.filter((p) => filters.amenities!.every((a) => p.amenities?.includes(a)));
    }
    return result;
  }, [properties, filters]);

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
    // templates/accommodation/guest/detail.html offers "Login to Book" in
    // place of "Proceed to Checkout" to an anonymous visitor. The property
    // page and its nightly rates stay public; the priced booking does not.
    if (!user?.public_id) { router.push("/login" as never); return; }
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
    if (!Number.isInteger(guestCount) || guestCount < 1 || guestCount > 32 || !Number.isInteger(roomCount) || roomCount < 1 || roomCount > 10) {
      setError("Choose 1–32 guests and 1–10 rooms using whole numbers.");
      return;
    }
    if (selectedProperty.max_guests > 0 && guestCount > selectedProperty.max_guests) {
      setError(`This property accommodates up to ${selectedProperty.max_guests} guests.`);
      return;
    }
    const [checkInYear, checkInMonth, checkInDay] = checkIn.split("-").map(Number);
    const [checkOutYear, checkOutMonth, checkOutDay] = checkOut.split("-").map(Number);
    const nights = (Date.UTC(checkOutYear, checkOutMonth - 1, checkOutDay) - Date.UTC(checkInYear, checkInMonth - 1, checkInDay)) / 86400000;
    if (nights > 90) {
      setError("A single accommodation booking cannot exceed 90 nights.");
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
      setError(serviceErrorMessage(e, "Accommodation"));
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
      setError(serviceErrorMessage(e, "Accommodation"));
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
                setError(serviceErrorMessage(e, "Accommodation"));
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

      <ServiceHeroAccent serviceKey="stays" title="Find your stay" subtitle="Search, compare, book & manage" />

      {error ? <Panel><Text style={styles.errorText}>{error}</Text></Panel> : null}
      {notice ? <Panel><Text style={styles.noticeText}>{notice}</Text></Panel> : null}

      <Panel>
        <View style={styles.searchHeader}>
          <SectionTitle>Find accommodation</SectionTitle>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={filtersVisible ? "Close filters" : "Open filters"}
            onPress={() => setFiltersVisible(true)}
            style={styles.filterButton}
          >
            <Text style={styles.filterButtonText}>Filters {Object.keys(filters).length ? `(${Object.keys(filters).length})` : ""}</Text>
          </Pressable>
        </View>
        <Field label="Property, city or destination" value={query} onChangeText={setQuery} placeholder="Search Kampala, Nairobi, hotel…" />
        <ActionButton label={loading ? "Searching stays…" : "Search stays"} disabled={loading || busy} onPress={() => void loadProperties(query)} />
        {loading ? (
          <ActivityIndicator color={palette.green} size="large" style={styles.centered} />
        ) : filteredProperties.length ? (
          <View style={viewMode === "grid" ? styles.grid : styles.list}>
            {viewMode === "grid" ? (
              <ScrollView horizontal={false} contentContainerStyle={styles.gridContent} showsVerticalScrollIndicator={false}>
                {filteredProperties.map((property) => (
                  <PropertyCard
                    key={property.public_id}
                    property={property}
                    selected={selectedProperty?.public_id === property.public_id}
                    onPress={() => chooseProperty(property)}
                    onWishlist={() => toggleWishlist(property)}
                    isWishlisted={isWishlisted(property.public_id)}
                  />
                ))}
              </ScrollView>
            ) : (
              filteredProperties.map((property) => (
                <PropertyCard
                  key={property.public_id}
                  property={property}
                  selected={selectedProperty?.public_id === property.public_id}
                  onPress={() => chooseProperty(property)}
                  onWishlist={() => toggleWishlist(property)}
                  isWishlisted={isWishlisted(property.public_id)}
                />
              ))
            )}
          </View>
        ) : error ? null : (
          <View style={styles.emptyState}>
            <Text style={styles.emptyIcon}>🏨</Text>
            <Text style={styles.emptyTitle}>No properties found</Text>
            <Text style={styles.emptyBody}>
              {query ? "Try a different search term or clear filters." : "No bookable properties available right now."}
            </Text>
            <Pressable onPress={() => { setQuery(""); setFilters({}); void loadProperties(); }} style={styles.emptyButton}>
              <Text style={styles.emptyButtonText}>Clear search & filters</Text>
            </Pressable>
          </View>
        )}
        <View style={styles.viewToggle}>
          <Pressable
            onPress={() => setViewMode("list")}
            style={[styles.viewButton, viewMode === "list" && styles.viewButtonActive]}
          >
            <Text style={{ fontSize: 18 }}>☰</Text>
          </Pressable>
          <Pressable
            onPress={() => setViewMode("grid")}
            style={[styles.viewButton, viewMode === "grid" && styles.viewButtonActive]}
          >
            <Text style={{ fontSize: 18 }}>⊞</Text>
          </Pressable>
        </View>
      </Panel>

      {selectedProperty ? (
        <Panel>
          <SectionTitle>{selectedProperty.title}</SectionTitle>
          {selectedProperty.main_image ? (
            <Image
              source={{ uri: selectedProperty.main_image }}
              style={styles.propertyImage}
              resizeMode="cover"
            />
          ) : null}
          <Text style={styles.description}>{selectedProperty.description || selectedProperty.summary}</Text>
          <Text style={styles.address}>{selectedProperty.address || `${selectedProperty.city}, ${selectedProperty.country}`}</Text>
          {selectedProperty.room_types.length ? (
            <View style={styles.roomTypes}>
              <Text style={styles.roomTypesTitle}>Choose a room</Text>
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
                    borderRadius: 14,
                    padding: 13,
                    backgroundColor: roomTypeToken === room.room_token ? "#EFF6F0" : palette.surface,
                    gap: 4,
                  }}
                >
                  <Text style={styles.roomName}>{room.name}</Text>
                  <Text style={styles.roomDetails}>{room.max_guests} guests · {room.beds} bed(s) · {room.total_units} units</Text>
                  <Text style={styles.roomPrice}>{money(room.base_price_per_night, room.currency)} per night</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
          <Field label="Check-in (YYYY-MM-DD)" value={checkIn} onChangeText={(value) => { setCheckIn(value); setQuote(null); }} placeholder="2026-12-10" />
          <Field label="Check-out (YYYY-MM-DD)" value={checkOut} onChangeText={(value) => { setCheckOut(value); setQuote(null); }} placeholder="2026-12-12" />
          <Field label="Guests" value={guests} onChangeText={(value) => { setGuests(value); setQuote(null); }} placeholder="2" keyboardType="numeric" />
          <Field label="Rooms" value={rooms} onChangeText={(value) => { setRooms(value); setQuote(null); }} placeholder="1" keyboardType="numeric" />
          <ActionButton label={user ? (busy ? "Preparing quote…" : "Check availability and get price") : "Login to Book"} disabled={busy} onPress={() => void requestQuote()} />
        </Panel>
      ) : null}

      {quote ? (
        <Panel>
          <SectionTitle>Review your booking</SectionTitle>
          <Text style={styles.totalPrice}>{money(quote.total, quote.currency)}</Text>
          <Text style={styles.bookingMeta}>{quote.nights} night(s) · {quote.num_guests} guest(s) · {quote.rooms_requested} room(s)</Text>
          <View style={styles.breakdown}>
            <Text style={styles.breakdownRow}><Text style={styles.breakdownLabel}>Nightly rate:</Text> <Text>{money(quote.nightly_rate, quote.currency)}</Text></Text>
            <Text style={styles.breakdownRow}><Text style={styles.breakdownLabel}>Subtotal:</Text> <Text>{money(quote.subtotal, quote.currency)}</Text></Text>
            <Text style={styles.breakdownRow}><Text style={styles.breakdownLabel}>Cleaning fee:</Text> <Text>{money(quote.cleaning_fee, quote.currency)}</Text></Text>
            <Text style={styles.breakdownRow}><Text style={styles.breakdownLabel}>Service fee:</Text> <Text>{money(quote.service_fee, quote.currency)}</Text></Text>
            <Text style={styles.breakdownRow}><Text style={styles.breakdownLabel}>Taxes:</Text> <Text>{money(quote.taxes, quote.currency)}</Text></Text>
            <Text style={styles.walletBalance}>
              Wallet balance: {quote.wallet_available_balance ? money(quote.wallet_available_balance, quote.currency) : "No matching Wallet found"}
            </Text>
            <StatusPill tone={quote.wallet_payment_available ? "green" : "gold"}>
              {quote.wallet_payment_available ? "Wallet can cover this booking" : "Wallet payment unavailable"}
            </StatusPill>
            <Text style={styles.quoteExpiry}>Quote expires {new Date(quote.expires_at).toLocaleTimeString()}.</Text>
          </View>
          <Field label="Transaction PIN" value={pin} onChangeText={setPin} placeholder="Enter your Wallet PIN" keyboardType="numeric" />
          <Field label="Special requests (optional)" value={specialRequests} onChangeText={setSpecialRequests} placeholder="Share arrival or accessibility requests" />
          <ActionButton label={busy ? "Confirming booking…" : "Review and pay from Wallet"} disabled={busy} onPress={confirmBooking} />
          <Text style={styles.disclaimer}>
            AFCON360 rechecks the property, dates and price on the server before charging your Wallet. The app does not calculate the booking total.
          </Text>
        </Panel>
      ) : null}

      {user ? <Panel>
        <SectionTitle>Your accommodation bookings</SectionTitle>
        {bookingsError ? <Text style={styles.errorText}>Booking history is unavailable: {bookingsError}</Text> : null}
        {bookingsLoading ? <ActivityIndicator color={palette.green} /> : null}
        {!bookingsLoading && bookings.length ? bookings.map((booking) => (
          <View key={booking.booking_reference} style={styles.bookingRow}>
            <Text style={styles.bookingTitle}>{booking.property.title || "Accommodation booking"}</Text>
            <Text style={styles.bookingRef}>{booking.booking_reference}</Text>
            <Text style={styles.bookingDates}>{booking.check_in} → {booking.check_out}</Text>
            <Text style={styles.bookingAmount}>{money(booking.amount, booking.currency)}</Text>
            <View style={styles.bookingPills}>
              <StatusPill tone={booking.status === "confirmed" ? "green" : "gold"}>{booking.status}</StatusPill>
              <StatusPill tone={booking.payment_status === "paid" ? "green" : "gold"}>{booking.payment_status}</StatusPill>
            </View>
            {bookingCanCancel(booking) ? <ActionButton label={busy ? "Processing…" : "Request cancellation"} disabled={busy} onPress={() => cancelBooking(booking)} /> : null}
          </View>
        )) : bookingsError || bookingsLoading ? null : (
          <Text style={styles.emptyText}>Your accommodation bookings will appear here.</Text>
        )}
        <ActionButton label={bookingsLoading ? "Refreshing bookings…" : "Refresh bookings"} disabled={bookingsLoading} onPress={() => void loadBookings()} />
      </Panel> : null}

      <StaysFiltersBottomSheet
        visible={filtersVisible}
        onClose={() => setFiltersVisible(false)}
        onApply={setFilters}
        initialFilters={filters}
        properties={properties}
      />
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  field: { gap: 6 },
  fieldLabel: { color: "#122419", fontWeight: "700", fontSize: 13 },
  input: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E6EAE4",
    borderRadius: 13,
    paddingHorizontal: 12,
    paddingVertical: 11,
    color: "#122419",
    fontSize: 15,
  },
  errorText: { color: "#9A342D", lineHeight: 20 },
  noticeText: { color: "#0E5B36", lineHeight: 20, fontWeight: "700" },
  searchHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  filterButton: { backgroundColor: "#E8F4EC", paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10 },
  filterButtonText: { color: "#0E5B36", fontSize: 12, fontWeight: "800" },
  centered: { alignSelf: "center", marginVertical: 16 },
  list: { gap: 12 },
  grid: { gap: 12 },
  gridContent: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  viewToggle: { flexDirection: "row", justifyContent: "flex-end", gap: 8, marginTop: 8 },
  viewButton: { width: 40, height: 40, borderRadius: 10, backgroundColor: "#F5F6F2", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#E6EAE4" },
  viewButtonActive: { backgroundColor: "#0E5B36", borderColor: "#0E5B36" },
  emptyState: { alignItems: "center", padding: 32, gap: 10 },
  emptyIcon: { fontSize: 48 },
  emptyTitle: { color: "#122419", fontSize: 16, fontWeight: "900" },
  emptyBody: { color: "#6C766E", fontSize: 13, lineHeight: 18, textAlign: "center" },
  emptyButton: { marginTop: 8, backgroundColor: "#E8F4EC", paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 },
  emptyButtonText: { color: "#0E5B36", fontWeight: "800" },
  propertyImage: { width: "100%", height: 200, borderRadius: 14, marginBottom: 12 },
  description: { color: "#6C766E", lineHeight: 20, marginBottom: 8 },
  address: { color: "#122419", fontWeight: "700", marginBottom: 12 },
  roomTypes: { gap: 8, marginBottom: 12 },
  roomTypesTitle: { color: "#122419", fontWeight: "800", marginBottom: 4 },
  roomName: { color: "#122419", fontWeight: "800" },
  roomDetails: { color: "#6C766E" },
  roomPrice: { color: "#122419" },
  totalPrice: { color: "#122419", fontSize: 21, fontWeight: "900", marginBottom: 4 },
  bookingMeta: { color: "#6C766E", marginBottom: 12 },
  breakdown: { gap: 4 },
  breakdownRow: { flexDirection: "row", justifyContent: "space-between", color: "#6C766E" },
  breakdownLabel: { fontWeight: "700" },
  walletBalance: { color: "#122419", fontWeight: "800", marginTop: 8 },
  quoteExpiry: { color: "#6C766E", fontSize: 11 },
  disclaimer: { color: "#6C766E", fontSize: 11, lineHeight: 17, marginTop: 8 },
  bookingRow: { borderTopWidth: 1, borderTopColor: "#E6EAE4", paddingTop: 10, gap: 6 },
  bookingTitle: { color: "#122419", fontWeight: "900" },
  bookingRef: { color: "#6C766E" },
  bookingDates: { color: "#6C766E" },
  bookingAmount: { color: "#122419", fontWeight: "700" },
  bookingPills: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  emptyText: { color: "#6C766E" },
});