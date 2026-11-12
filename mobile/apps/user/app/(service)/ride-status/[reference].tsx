import React, { useCallback, useState } from "react";
import { ActivityIndicator, AppState, Pressable, Text } from "react-native";
import { useFocusEffect, useLocalSearchParams } from "expo-router";
import { AppScreen, PageHeader, Panel, SectionTitle, StatusPill, palette } from "@afcon360/mobile-ui";
import { authClient } from "../../../src/services/api";

type VehicleData = {
  make?: string;
  model?: string;
  license_plate?: string;
  vehicle_class?: string;
} | null;

type LocationData = string | {
  address?: string;
  display_name?: string;
  label?: string;
} | null;

type PickupSchedule = {
  local_datetime?: string | null;
  utc_datetime?: string | null;
  timezone_name?: string | null;
} | null;

type RequestData = {
  request_id: string;
  status: string;
  cycle?: { status: string; deadline?: string | null; terminal_reason?: string | null };
  converted?: boolean;
  booking_status?: string;
  booking_mode?: string | null;
  pickup_time?: string | null;
  pickup_schedule?: PickupSchedule;
  pickup_label?: string | null;
  destination_label?: string | null;
  service_type?: string | null;
  fare_estimate?: { amount?: number | string | null; currency?: string | null };
  payment_method?: string;
  created_at?: string | null;
  driver?: { display_name?: string; phone?: string | null; rating?: number | null } | null;
  vehicle?: VehicleData;
  payment?: { method?: string; status?: string; amount?: number | string; currency?: string };
};

type BookingDetailResponse = {
  booking?: {
    booking_reference?: string;
    status?: string;
    service_type?: string;
    pickup_time?: string | null;
    pickup_location?: LocationData;
    dropoff_location?: LocationData;
    pickup_mode?: string | null;
    booking_mode?: string | null;
    booking_metadata?: {
      booking_mode?: string;
      pickup_schedule?: PickupSchedule;
    } | null;
    payment_method?: string;
    payment_status?: string;
    final_price?: number | string | null;
    total_amount?: number | string | null;
    base_price?: number | string | null;
    currency?: string | null;
    created_at?: string | null;
  };
  driver_display?: {
    name?: string;
    phone?: string | null;
    rating?: number | null;
    vehicle?: VehicleData;
  } | null;
  vehicle?: VehicleData;
};

export default function RideStatusScreen() {
  const params = useLocalSearchParams<{ reference: string; kind?: string }>();
  const reference = String(params.reference ?? "");
  const isBooking = String(params.kind ?? "request") === "booking";
  const [data, setData] = useState<RequestData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!reference) {
      setError("This ride reference is missing. Return to your activity and open the booking again.");
      setLoading(false);
      return;
    }
    try {
      if (isBooking) {
        const response = await authClient.request<{
          success: boolean;
          data: BookingDetailResponse;
        }>(
          "/api/mobile/v1/transport/bookings/" + encodeURIComponent(reference)
        );
        const bookingData = response.data?.booking;
        if (!bookingData) {
          throw new Error("AFCON360 did not return the booking details for this reference.");
        }
        const driver = response.data?.driver_display ?? null;
        const vehicle = driver?.vehicle ?? response.data?.vehicle ?? null;
        const amount = bookingData.final_price ??
          bookingData.total_amount ??
          bookingData.base_price ??
          null;
        const bookingStatus = String(bookingData.status ?? "pending");
        const pickupLocation = bookingData.pickup_location;
        const dropoffLocation = bookingData.dropoff_location;
        const locationLabel = (value: LocationData | undefined): string | null => {
          if (typeof value === "string") return value;
          return value?.address ?? value?.display_name ?? value?.label ?? null;
        };
        const pickupSchedule = bookingData.booking_metadata?.pickup_schedule ?? null;
        const bookingMode = bookingData.booking_mode ??
          bookingData.pickup_mode ??
          bookingData.booking_metadata?.booking_mode ??
          null;
        setData({
          request_id: bookingData.booking_reference ?? reference,
          status: bookingStatus,
          booking_status: bookingStatus,
          booking_mode: bookingMode,
          pickup_time: pickupSchedule?.local_datetime ??
            bookingData.pickup_time ?? null,
          pickup_schedule: pickupSchedule,
          pickup_label: locationLabel(pickupLocation),
          destination_label: locationLabel(dropoffLocation),
          service_type: bookingData.service_type ?? null,
          converted: Boolean(driver),
          fare_estimate: {
            amount,
            currency: bookingData.currency ?? null
          },
          payment_method: bookingData.payment_method ?? undefined,
          payment: {
            method: bookingData.payment_method,
            status: bookingData.payment_status,
            amount: amount ?? undefined,
            currency: bookingData.currency ?? undefined
          },
          created_at: bookingData.created_at ?? null,
          driver: driver ? {
            display_name: driver.name ?? "Driver assigned",
            phone: driver.phone ?? null,
            rating: driver.rating ?? null
          } : null,
          vehicle
        });
      } else {
        const response = await authClient.request<{
          success: boolean;
          data: RequestData;
        }>(
          "/api/mobile/v1/transport/ride-requests/" + encodeURIComponent(reference)
        );
        setData(response.data);
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not refresh this ride.");
    } finally {
      setLoading(false);
    }
  }, [reference, isBooking]);

  useFocusEffect(
    useCallback(() => {
      void refresh();

      // Poll only while this status screen is visible and the app is active.
      // Resume with a fresh server state after backgrounding the app.
      const subscription = AppState.addEventListener("change", state => {
        if (state === "active") void refresh();
      });
      const timer = setInterval(() => {
        if (AppState.currentState === "active") void refresh();
      }, 12000);

      return () => {
        clearInterval(timer);
        subscription.remove();
      };
    }, [refresh])
  );

  const requestState = (data?.cycle?.status ?? data?.status ?? "Waiting for status")
    .replace(/_/g, " ");
  const quotedFare = data?.fare_estimate;
  const payment = data?.payment;

  return (
    <AppScreen>
      <PageHeader
        eyebrow={isBooking ? "Ride booking" : "Ride tracking"}
        title={isBooking ? "Your ride booking." : "Your driver journey."}
        description={isBooking
          ? "This is your website-equivalent Transport booking record. AFCON360 reports its booking and driver-assignment status here."
          : "This reference tracks your request through matching and assignment. A ride is not driver-confirmed until Transport commits a driver and vehicle."}
      />
      <Panel>
        <StatusPill tone={data?.converted ? "green" : "gold"}>
          {data?.converted ? "Driver assigned" : requestState}
        </StatusPill>
        <SectionTitle>{isBooking ? "Booking reference" : "Request reference"}</SectionTitle>
        <Text selectable style={{ color: palette.ink, fontSize: 15, fontWeight: "900" }}>
          {reference || "Reference unavailable"}
        </Text>
        {loading ? <ActivityIndicator color={palette.green} /> : null}
        {error ? (
          <Text accessibilityRole="alert" style={{ color: "#9A3A2F", fontSize: 13, lineHeight: 19 }}>
            {error}
          </Text>
        ) : null}
        <Pressable
          onPress={() => { setLoading(true); void refresh(); }}
          accessibilityRole="button"
          accessibilityLabel={isBooking ? "Refresh booking status" : "Refresh ride request status"}
          style={{ paddingVertical: 10 }}
        >
          <Text style={{ color: palette.greenDark, fontWeight: "800" }}>Refresh status</Text>
        </Pressable>
      </Panel>

      {data ? (
        <Panel>
          <SectionTitle>{isBooking ? "Booking details" : "Request details"}</SectionTitle>
          {quotedFare?.amount != null ? (
            <Text style={{ color: palette.ink, fontWeight: "800" }}>
              {isBooking ? "Booking fare: " : "Quoted fare: "}
              {quotedFare.amount} {quotedFare.currency ?? ""}
            </Text>
          ) : null}
          {data.pickup_label ? (
            <Text style={{ color: palette.muted, fontSize: 12 }}>
              Pickup: {data.pickup_label}
            </Text>
          ) : null}
          {data.destination_label ? (
            <Text style={{ color: palette.muted, fontSize: 12 }}>
              Destination: {data.destination_label}
            </Text>
          ) : null}
          {data.booking_mode ? (
            <Text style={{ color: palette.muted, fontSize: 12 }}>
              Booking time: {data.booking_mode === "scheduled" ? "Scheduled" : "Leaving now"}
            </Text>
          ) : null}
          {data.pickup_time ? (
            <Text style={{ color: palette.muted, fontSize: 12 }}>
              Pickup time: {data.pickup_time.replace("T", " ")}
              {data.pickup_schedule?.timezone_name ? ` · ${data.pickup_schedule.timezone_name}` : ""}
            </Text>
          ) : null}
          {data.service_type ? (
            <Text style={{ color: palette.muted, fontSize: 12 }}>
              Service: {data.service_type.replace(/_/g, " ")}
            </Text>
          ) : null}
          <Text style={{ color: palette.muted, fontSize: 12 }}>
            Payment choice: {data.payment_method ?? payment?.method ?? "Not available"}
          </Text>
          {payment ? (
            <Text style={{ color: palette.muted, fontSize: 12 }}>
              Payment status: {payment.status ?? "Not available"}
              {payment.amount != null ? ` · ${payment.amount} ${payment.currency ?? ""}` : ""}
            </Text>
          ) : null}
          {!data.converted ? (
            <Text style={{ color: palette.muted, fontSize: 13, lineHeight: 19 }}>
              {isBooking
                ? data.booking_mode === "scheduled"
                  ? "Your scheduled booking is saved. Transport releases it for driver matching inside the scheduled pickup window."
                  : data.payment_method === "cash"
                    ? "Your booking has been submitted to Transport matching. This screen refreshes with the latest server status."
                    : "Your booking is saved. Driver matching follows the selected payment method's settlement lifecycle."
                : `This request has not yet been converted into an assigned booking. The status above is the latest state reported by AFCON360 Transport.${data.cycle?.terminal_reason ? ` ${data.cycle.terminal_reason}` : ""}`}
            </Text>
          ) : null}
        </Panel>
      ) : null}

      {data?.converted ? (
        <Panel>
          <SectionTitle>Your assigned driver</SectionTitle>
          <Text style={{ color: palette.ink, fontWeight: "800" }}>
            {data.driver?.display_name ?? "Driver assigned"}
          </Text>
          {data.driver?.phone ? (
            <Text style={{ color: palette.ink }}>{data.driver.phone}</Text>
          ) : null}
          {data.driver?.rating != null ? (
            <Text style={{ color: palette.muted }}>Rating {data.driver.rating.toFixed(1)}</Text>
          ) : null}
          <SectionTitle>Vehicle</SectionTitle>
          <Text style={{ color: palette.ink }}>
            {[data.vehicle?.make, data.vehicle?.model].filter(Boolean).join(" ") || "Vehicle assigned"}
          </Text>
          {data.vehicle?.license_plate ? (
            <Text style={{ color: palette.ink, fontWeight: "800" }}>{data.vehicle.license_plate}</Text>
          ) : null}
          {data.booking_status ? (
            <Text style={{ color: palette.muted }}>Trip status: {data.booking_status}</Text>
          ) : null}
        </Panel>
      ) : null}
    </AppScreen>
  );
}
